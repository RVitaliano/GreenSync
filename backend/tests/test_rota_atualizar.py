"""POST /dispositivos/{device_id}/atualizar (pedido de OTA), com Firestore e MQTT falsos."""
import asyncio
import threading
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import limite
from app.agenda.regras import MOTIVO_INCERTO
from app.ai import responder
from app.config import settings
from app.ota import repositorio, servico
from app.routes import dispositivos as rota
from tests.falso_firestore import FIRESTORE_FALSO, DbFalso
from tests.falsos import leitura_ok

URL = "https://github.com/o/r/releases/download/v2/fw.bin"
HASH = "ab" * 32


def agora():
    return datetime.now(timezone.utc)


class Montagem:
    def __init__(self):
        self.db = DbFalso()
        self.publicados = []
        self.leitura = leitura_ok()
        self.erro_publicacao = None
        self.db.store["firmware"] = {
            "wroom": {"versao": "2.0.0", "url": URL, "sha256": HASH, "notas": None, "anterior": None},
            "s3": {"versao": "3.0.0", "url": URL.replace("v2", "v3"), "sha256": "cd" * 32,
                   "notas": None, "anterior": None},
        }
        self.db.store["devices"] = {"vaso-01": {"status": "online", "fw": "1.0.0", "fw_s3": "1.0.0"}}

    async def publicar(self, device_id, payload):
        if self.erro_publicacao:
            raise self.erro_publicacao
        self.publicados.append((device_id, payload))

    @property
    def ota(self):
        return self.db.doc("devices", "vaso-01").get("ota")


@pytest.fixture
def m(monkeypatch):
    m = Montagem()
    monkeypatch.setattr(repositorio, "init_firebase", lambda: m.db)
    monkeypatch.setattr(repositorio, "firestore", FIRESTORE_FALSO)
    monkeypatch.setattr(servico, "publicar_comando", m.publicar)

    async def leitura_da_rota(device_id):
        return m.leitura

    monkeypatch.setattr(rota, "ler_leitura_segura", leitura_da_rota)
    monkeypatch.setattr(settings, "api_key", "segredo")

    def proibido(*a, **kw):
        raise AssertionError("esta rota não pode chamar o Gemini nem o limite de perguntas")

    for nome in ("responder", "responder_audio", "get_client"):
        monkeypatch.setattr(responder, nome, proibido)
    monkeypatch.setattr(limite, "verificar_limite", proibido)

    app = FastAPI()
    app.include_router(rota.router)
    m.app = app
    m.client = TestClient(app)
    return m


def pedir(m, alvo="wroom", device="vaso-01", chave="segredo", corpo=None):
    cab = {"X-API-Key": chave} if chave is not None else {}
    return m.client.post(f"/dispositivos/{device}/atualizar", headers=cab,
                         json={"alvo": alvo} if corpo is None else corpo)


# ---------- sucesso ----------

@pytest.mark.parametrize("alvo,versao,url,sha", [
    ("wroom", "2.0.0", URL, HASH),
    ("s3", "3.0.0", URL.replace("v2", "v3"), "cd" * 32),
])
def test_sucesso_publica_o_comando_e_grava_solicitada(m, alvo, versao, url, sha):
    r = pedir(m, alvo=alvo)
    assert r.status_code == 200
    j = r.json()
    assert j["resultado"] == "solicitada" and j["motivo"] is None
    assert j["versao"] == versao and j["id"] and len(j["id"]) == 32
    assert m.publicados == [("vaso-01", {"acao": "atualizar", "alvo": alvo, "id": j["id"],
                                          "versao": versao, "url": url, "sha256": sha})]
    assert m.ota["estado"] == "solicitada" and m.ota["id"] == j["id"]
    assert (m.ota["alvo"], m.ota["versao"]) == (alvo, versao)
    assert isinstance(m.ota["atualizado_em"], datetime)
    assert m.db.doc("devices", "vaso-01")["fw"] == "1.0.0"      # o resto do documento fica


# ---------- recusas (nada é publicado) ----------

def _sem_registro(m):
    del m.db.store["firmware"]["wroom"]


def _offline(m):
    m.leitura = leitura_ok(status_vaso="offline")


def _sem_dados(m):
    m.leitura = None


def _bomba(m):
    m.leitura = leitura_ok(bomba_ligada=True)


def _versao_igual(m):
    m.db.store["devices"]["vaso-01"]["fw"] = "2.0.0"


def _em_curso(m):
    m.db.store["devices"]["vaso-01"]["ota"] = {"alvo": "s3", "id": "x", "versao": "3.0.0",
                                                "estado": "baixando", "atualizado_em": agora()}


def _registro_torto(m):
    m.db.store["firmware"]["wroom"]["url"] = "https://evil.com/fw.bin"


@pytest.mark.parametrize("prepara,motivo", [
    (_sem_registro, "sem_firmware"),
    (_sem_dados, "sem_dados"),
    (_offline, "offline"),
    (_bomba, "bomba_ligada"),
    (_versao_igual, "versao_igual"),
    (_em_curso, "ota_em_curso"),
    (_registro_torto, "firmware_invalido"),
])
def test_recusas_nao_publicam_nada(m, prepara, motivo):
    prepara(m)
    antes = m.db.doc("devices", "vaso-01").get("ota")
    r = pedir(m)
    assert r.status_code == 200
    assert r.json() == {"resultado": "recusada", "id": None, "motivo": motivo, "versao": None}
    assert m.publicados == []
    assert m.db.doc("devices", "vaso-01").get("ota") == antes


def test_versao_igual_para_o_s3_olha_o_campo_fw_s3(m):
    m.db.store["devices"]["vaso-01"]["fw_s3"] = "3.0.0"
    assert pedir(m, alvo="s3").json()["motivo"] == "versao_igual"
    m.db.store["devices"]["vaso-01"]["fw_s3"] = "1.0.0"
    m.db.store["devices"]["vaso-01"]["fw"] = "3.0.0"        # fw do WROOM igual não impede o S3
    assert pedir(m, alvo="s3").json()["resultado"] == "solicitada"


def test_versao_instalada_desconhecida_e_permitida(m):
    del m.db.store["devices"]["vaso-01"]["fw"]
    assert pedir(m).json()["resultado"] == "solicitada"


def test_dispositivo_sem_documento_de_status_ainda_atualiza_com_leitura(m):
    del m.db.store["devices"]["vaso-01"]
    r = pedir(m)
    assert r.json()["resultado"] == "solicitada" and m.ota["estado"] == "solicitada"


# ---------- ota em curso x travada ----------

@pytest.mark.parametrize("estado", ["solicitada", "baixando", "aplicando"])
def test_ota_em_curso_recusa(m, estado):
    m.db.store["devices"]["vaso-01"]["ota"] = {"alvo": "wroom", "id": "x", "versao": "2.0.0",
                                                "estado": estado, "atualizado_em": agora() - timedelta(seconds=30)}
    assert pedir(m).json()["motivo"] == "ota_em_curso"
    assert m.publicados == []


@pytest.mark.parametrize("estado", ["solicitada", "baixando", "aplicando"])
def test_ota_travada_mais_antiga_que_o_prazo_permite(m, estado):
    antiga = agora() - timedelta(seconds=settings.ota_timeout_s + 5)
    m.db.store["devices"]["vaso-01"]["ota"] = {"alvo": "wroom", "id": "x", "versao": "2.0.0",
                                                "estado": estado, "atualizado_em": antiga}
    j = pedir(m).json()
    assert j["resultado"] == "solicitada" and j["id"] != "x"
    assert m.ota["id"] == j["id"] and len(m.publicados) == 1


@pytest.mark.parametrize("estado", ["ok", "falhou", "revertido"])
def test_estados_finais_nao_bloqueiam(m, estado):
    m.db.store["devices"]["vaso-01"]["ota"] = {"alvo": "wroom", "id": "x", "versao": "2.0.0",
                                                "estado": estado, "atualizado_em": agora()}
    assert pedir(m).json()["resultado"] == "solicitada"


def test_segunda_chamada_seguida_e_recusada_por_ota_em_curso(m):
    assert pedir(m).json()["resultado"] == "solicitada"
    assert pedir(m, alvo="s3").json()["motivo"] == "ota_em_curso"      # qualquer alvo
    assert len(m.publicados) == 1


@pytest.mark.anyio
async def test_duas_chamadas_simultaneas_so_uma_publica(m):
    # As 3 leituras dentro da transação são forçadas a acontecer juntas: sem a trava do serviço,
    # todas veriam "nada em curso" e as 3 publicariam.
    m.db.barreira = threading.Barrier(3)
    transporte = httpx.ASGITransport(app=m.app)
    async with httpx.AsyncClient(transport=transporte, base_url="http://t") as c:
        resp = await asyncio.gather(*[
            c.post("/dispositivos/vaso-01/atualizar", headers={"X-API-Key": "segredo"}, json={"alvo": "wroom"})
            for _ in range(3)
        ])
    resultados = sorted(r.json()["resultado"] + ":" + str(r.json()["motivo"]) for r in resp)
    assert resultados == ["recusada:ota_em_curso", "recusada:ota_em_curso", "solicitada:None"]
    assert len(m.publicados) == 1


# ---------- falha na publicação ----------

def test_falha_na_publicacao_marca_falhou_sem_500(m):
    m.erro_publicacao = ConnectionError("broker fora")
    r = pedir(m)
    assert r.status_code == 200
    j = r.json()
    assert (j["resultado"], j["motivo"], j["versao"]) == ("falhou", "não consegui falar com o broker", "2.0.0")
    assert j["id"] == m.ota["id"]
    assert m.ota["estado"] == "falhou" and m.ota["motivo"] == "não consegui falar com o broker"


def test_falha_incerta_grava_o_motivo_de_incerteza(m):
    class Incerta(Exception):
        incerta = True

    m.erro_publicacao = Incerta("caiu no meio")
    j = pedir(m).json()
    assert j["resultado"] == "falhou" and j["motivo"] == MOTIVO_INCERTO
    assert m.ota["motivo"] == MOTIVO_INCERTO


def test_depois_de_falhar_uma_nova_tentativa_e_permitida(m):
    m.erro_publicacao = ConnectionError("broker fora")
    assert pedir(m).json()["resultado"] == "falhou"
    m.erro_publicacao = None
    assert pedir(m).json()["resultado"] == "solicitada"
    assert "motivo" not in m.ota                               # não herda o motivo da falha


# ---------- entrada ----------

@pytest.mark.parametrize("corpo", [{"alvo": "esp32"}, {"alvo": "WROOM"}, {"alvo": ""}, {"alvo": None},
                                   {}, {"alvo": 3}, {"versao": "2.0.0"}])
def test_alvo_invalido_da_422(m, corpo):
    assert pedir(m, corpo=corpo).status_code == 422
    assert m.publicados == []


def test_sem_corpo_da_422(m):
    r = m.client.post("/dispositivos/vaso-01/atualizar", headers={"X-API-Key": "segredo"})
    assert r.status_code == 422


@pytest.mark.parametrize("chave", [None, "", "errada"])
def test_chave_ausente_ou_errada_da_401(m, chave):
    assert pedir(m, chave=chave).status_code == 401
    assert m.publicados == [] and m.ota is None


def test_chave_de_administracao_nao_vale_aqui(m, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    r = m.client.post("/dispositivos/vaso-01/atualizar", headers={"X-Admin-Key": "admin-secreta"},
                      json={"alvo": "wroom"})
    assert r.status_code == 401


@pytest.mark.parametrize("device", ["vaso.01", "vaso%20x", "a" * 65])
def test_device_id_invalido_da_422(m, device):
    assert pedir(m, device=device).status_code == 422


def test_url_e_hash_vem_do_registro_e_o_app_nao_sobrescreve(m):
    corpo = {"alvo": "wroom", "versao": "9.9.9", "url": "https://evil.com/mal.bin",
             "sha256": "0" * 64, "id": "forjado", "acao": "regar"}
    r = pedir(m, corpo=corpo)
    assert r.status_code == 200
    _, payload = m.publicados[0]
    assert payload == {"acao": "atualizar", "alvo": "wroom", "id": r.json()["id"],
                       "versao": "2.0.0", "url": URL, "sha256": HASH}
    assert r.json()["id"] != "forjado"


# ---------- erros inesperados ----------

def test_erro_inesperado_vira_502_sem_vazar_detalhes(m, monkeypatch, caplog):
    async def quebra(device_id):
        raise RuntimeError("segredo-interno do firestore")

    monkeypatch.setattr(repositorio, "ler_dispositivo", quebra)
    with caplog.at_level("ERROR", logger="greensync.dispositivos"):
        r = pedir(m)
    assert r.status_code == 502
    assert "segredo-interno" not in r.text and "firestore" not in r.text.lower()
    assert "pedido de atualização" in caplog.text
    assert m.publicados == []
