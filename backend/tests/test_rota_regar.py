"""POST /dispositivos/{device_id}/regar (rega manual do app), com Firestore e MQTT falsos."""
from datetime import timedelta

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import limite
from app.agenda import servico
from app.agenda.agendador import Agendador
from app.ai import responder
from app.config import settings
from app.routes import dispositivos as rota
from tests.falsos import RepoFalso, agora_utc, leitura_ok


class Montagem:
    def __init__(self):
        self.repo = RepoFalso()
        self.publicados = []
        self.leitura = leitura_ok()       # o que a rota lê do Firestore
        self.mqtt_cai = False
        self.ag = Agendador(self.repo, self.publicar, self.ler_leitura)

    async def publicar(self, device_id, payload):
        if self.mqtt_cai:
            raise ConnectionError("broker fora")
        self.publicados.append((device_id, payload))

    async def ler_leitura(self, device_id):
        return self.leitura


@pytest.fixture
def m(monkeypatch):
    m = Montagem()
    monkeypatch.setattr(servico, "agendador", m.ag)

    async def leitura_da_rota(device_id):
        return m.leitura

    monkeypatch.setattr(rota, "ler_leitura_segura", leitura_da_rota)
    monkeypatch.setattr(settings, "api_key", "segredo")

    # O Gemini e o limite de perguntas NÃO podem ser tocados por esta rota.
    def proibido(*a, **kw):
        raise AssertionError("esta rota não pode chamar o Gemini nem o limite de perguntas")

    for nome in ("responder", "responder_audio", "get_client"):
        monkeypatch.setattr(responder, nome, proibido)
    monkeypatch.setattr(limite, "verificar_limite", proibido)

    app = FastAPI()
    app.include_router(rota.router)
    m.client = TestClient(app)
    return m


def regar(m, device="vaso-01", corpo=None, chave="segredo", **kw):
    cab = {"X-API-Key": chave} if chave is not None else {}
    return m.client.post(f"/dispositivos/{device}/regar", headers=cab, json=corpo, **kw) if corpo is not None \
        else m.client.post(f"/dispositivos/{device}/regar", headers=cab)


# ---------- sucesso ----------

def test_rega_agendada_publica_o_comando_com_a_duracao_pedida(m):
    r = regar(m, corpo={"duracao_s": 7})
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resultado"] == "agendada" and corpo["motivo"] is None and corpo["id"]
    assert m.publicados == [("vaso-01", {"acao": "regar", "duracao_s": 7, "id": corpo["id"]})]
    assert m.repo.docs[("vaso-01", corpo["id"])]["origem"] == "app"


@pytest.mark.parametrize("corpo", [None, {}, {"duracao_s": None}])
def test_sem_duracao_usa_o_padrao(m, corpo):
    r = regar(m, corpo=corpo)
    assert r.status_code == 200 and r.json()["resultado"] == "agendada"
    assert m.publicados[0][1]["duracao_s"] == settings.rega_duracao_padrao_s


# ---------- recusas (nada é publicado) ----------

@pytest.mark.parametrize("leitura,motivo", [
    (None, "sem_dados"),
    (leitura_ok(status_vaso="offline"), "offline"),
    (leitura_ok(umidade_solo=90), "solo_encharcado"),
    (leitura_ok(bomba_ligada=True), "bomba_ligada"),
])
def test_recusas_do_estado_do_vaso(m, leitura, motivo):
    m.leitura = leitura
    r = regar(m)
    assert r.status_code == 200
    assert r.json() == {"resultado": "recusada", "id": None, "motivo": motivo}
    assert m.publicados == [] and m.repo.docs == {}


def test_recusa_por_intervalo_com_rega_vizinha(m):
    m.repo.inserir("ag-perto", agora_utc() + timedelta(seconds=120))
    r = regar(m)
    assert r.json() == {"resultado": "recusada", "id": None, "motivo": "intervalo"}
    assert m.publicados == []


def test_segunda_chamada_dentro_do_intervalo_e_recusada(m):
    assert regar(m).json()["resultado"] == "agendada"
    r = regar(m)
    assert r.json() == {"resultado": "recusada", "id": None, "motivo": "intervalo"}
    assert len(m.publicados) == 1


def test_duracao_acima_do_maximo_e_recusada_e_nao_422(m):
    r = regar(m, corpo={"duracao_s": settings.rega_duracao_max_s + 1})
    assert r.status_code == 200
    assert r.json() == {"resultado": "recusada", "id": None, "motivo": "duracao_grande"}
    assert m.publicados == []


def test_duracao_no_maximo_passa(m):
    r = regar(m, corpo={"duracao_s": settings.rega_duracao_max_s})
    assert r.json()["resultado"] == "agendada"


# ---------- entrada inválida ----------

@pytest.mark.parametrize("duracao", [0, -3, "abc", "5", 5.5, True])
def test_duracao_invalida_da_422(m, duracao):
    r = regar(m, corpo={"duracao_s": duracao})
    assert r.status_code == 422
    assert m.publicados == [] and m.repo.docs == {}


@pytest.mark.parametrize("chave", [None, "errada", ""])
def test_chave_ausente_ou_errada_da_401(m, chave):
    assert regar(m, chave=chave).status_code == 401
    assert m.publicados == [] and m.repo.docs == {}


@pytest.mark.parametrize("device", ["vaso.01", "vaso%20x", "a" * 65])
def test_device_id_invalido_da_422(m, device):
    assert regar(m, device=device).status_code == 422
    assert m.publicados == []


# ---------- falhas ----------

def test_falha_na_publicacao_vira_falhou_com_motivo_sem_500(m):
    m.mqtt_cai = True
    r = regar(m)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["resultado"] == "falhou"
    assert corpo["motivo"] == "não consegui falar com o broker"
    assert corpo["id"]


def test_erro_inesperado_vira_502_sem_vazar_detalhes(m, caplog):
    m.repo.falhar_ao_criar = True        # "firestore fora" dentro do repositório
    with caplog.at_level("ERROR", logger="greensync.dispositivos"):
        r = regar(m)
    assert r.status_code == 502
    assert "firestore" not in r.text.lower()
    assert "erro ao processar a rega manual" in caplog.text
    assert m.publicados == []


# ---------- regressão: voz/texto não mudaram ----------

@pytest.mark.anyio
async def test_tratar_acao_continua_com_o_mesmo_formato(m):
    from app.ai.estado import avaliar_estado

    leitura = leitura_ok()
    r = await servico.tratar_acao(
        {"tipo": "regar", "daqui_a_s": None, "as_hora": None, "duracao_s": None},
        "Rega a planta", "vaso-01", leitura, avaliar_estado(leitura), "voz")
    assert set(r) == {"fala", "resultado", "id"}
    assert r["resultado"] == "agendada" and r["fala"].startswith("Pode deixar, vou me regar agora")
