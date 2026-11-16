"""POST /dispositivos/{id}/reverter (administração) e o ciclo retirar -> atualizar -> ok."""
import asyncio
import json
import threading
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app import limite, mqtt_client
from app.agenda.regras import MOTIVO_INCERTO
from app.ai import responder
from app.config import settings
from app.ota import repositorio, servico
from app.routes import dispositivos as rota_disp
from app.routes import firmware as rota_fw
from tests.falso_firestore import FIRESTORE_FALSO, DbFalso
from tests.falsos import leitura_ok

URL_BOA = "https://github.com/o/r/releases/download/v1/fw.bin"
URL_RUIM = "https://github.com/o/r/releases/download/v2/fw.bin"
HASH_BOA, HASH_RUIM = "ab" * 32, "cd" * 32
ADMIN = {"X-Admin-Key": "admin-secreta"}
APP = {"X-API-Key": "chave-do-app"}


def agora():
    return datetime.now(timezone.utc)


class Montagem:
    """Registro com a versão BOA (1.0.0) como atual; o vaso roda a ruim (2.0.0)."""

    def __init__(self):
        self.db = DbFalso()
        self.publicados = []
        self.leitura = leitura_ok()
        self.erro_publicacao = None
        boa = {"versao": "1.0.0", "url": URL_BOA, "sha256": HASH_BOA, "notas": None,
               "publicado_em": agora(), "anterior": None, "bloqueadas": ["2.0.0"]}
        self.db.store["firmware"] = {"wroom": dict(boa), "s3": {**boa, "versao": "1.1.0"}}
        self.db.store["devices"] = {"vaso-01": {"status": "online", "fw": "2.0.0", "fw_s3": "2.0.0"}}

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
    # Um Lock fica preso ao loop em que foi disputado; cada teste usa o seu para não depender da ordem.
    monkeypatch.setattr(servico, "trava", asyncio.Lock())

    async def leitura_da_rota(device_id):
        return m.leitura

    monkeypatch.setattr(rota_disp, "ler_leitura_segura", leitura_da_rota)
    monkeypatch.setattr(settings, "api_key", "chave-do-app")
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")

    def proibido(*a, **kw):
        raise AssertionError("esta rota não pode chamar o Gemini nem o limite de perguntas")

    for nome in ("responder", "responder_audio", "get_client"):
        monkeypatch.setattr(responder, nome, proibido)
    monkeypatch.setattr(limite, "verificar_limite", proibido)

    app = FastAPI()
    app.include_router(rota_disp.router)
    app.include_router(rota_fw.router)
    m.app = app
    m.client = TestClient(app)
    return m


def reverter(m, alvo="wroom", device="vaso-01", cab=ADMIN, corpo=None):
    return m.client.post(f"/dispositivos/{device}/reverter", headers=cab,
                         json={"alvo": alvo} if corpo is None else corpo)


# ---------- sucesso ----------

@pytest.mark.parametrize("alvo,versao", [("wroom", "1.0.0"), ("s3", "1.1.0")])
def test_sucesso_publica_o_comando_exato_e_grava_o_tipo(m, alvo, versao):
    r = reverter(m, alvo=alvo)
    assert r.status_code == 200
    j = r.json()
    assert j["resultado"] == "solicitada" and j["motivo"] is None and j["versao"] == versao
    assert m.publicados == [("vaso-01", {"acao": "reverter", "alvo": alvo, "id": j["id"], "versao": versao})]
    assert m.ota["tipo"] == "reverter" and m.ota["estado"] == "solicitada"
    assert (m.ota["id"], m.ota["alvo"], m.ota["versao"]) == (j["id"], alvo, versao)


def test_o_comando_de_reverter_nao_leva_url_nem_hash(m):
    reverter(m)
    assert set(m.publicados[0][1]) == {"acao", "alvo", "id", "versao"}


def test_atualizar_passa_a_gravar_o_tipo_atualizar(m):
    m.db.store["firmware"]["wroom"]["versao"] = "3.0.0"
    r = m.client.post("/dispositivos/vaso-01/atualizar", headers=APP, json={"alvo": "wroom"})
    assert r.json()["resultado"] == "solicitada"
    assert m.ota["tipo"] == "atualizar"
    assert m.publicados[0][1]["acao"] == "atualizar" and "url" in m.publicados[0][1]


# ---------- autenticação ----------

def test_chave_de_admin_vazia_a_rota_esta_desligada_403(m, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    for cab in ({}, ADMIN, APP, {"X-Admin-Key": ""}):
        assert reverter(m, cab=cab).status_code == 403
    assert m.publicados == []


@pytest.mark.parametrize("cab", [{}, {"X-Admin-Key": ""}, {"X-Admin-Key": "errada"}])
def test_chave_errada_ou_ausente_da_401(m, cab):
    assert reverter(m, cab=cab).status_code == 401
    assert m.publicados == [] and m.ota is None


def test_api_key_comum_nao_abre_a_rota_de_reversao(m):
    assert reverter(m, cab=APP).status_code == 401
    assert reverter(m, cab={"X-Admin-Key": "chave-do-app"}).status_code == 401
    assert m.publicados == []


def test_chave_de_admin_nao_abre_a_rota_de_atualizar(m):
    r = m.client.post("/dispositivos/vaso-01/atualizar", headers=ADMIN, json={"alvo": "wroom"})
    assert r.status_code == 401


def test_sem_chave_nao_revela_validacao_do_corpo(m):
    assert reverter(m, cab={"X-Admin-Key": "errada"}, corpo={"alvo": "lixo"}).status_code == 401


# ---------- recusas (nada é publicado) ----------

def _sem_registro(m):
    del m.db.store["firmware"]["wroom"]


def _sem_dados(m):
    m.leitura = None


def _offline(m):
    m.leitura = leitura_ok(status_vaso="offline")


def _bomba(m):
    m.leitura = leitura_ok(bomba_ligada=True)


def _versao_igual(m):
    m.db.store["devices"]["vaso-01"]["fw"] = "1.0.0"


def _em_curso(m):
    m.db.store["devices"]["vaso-01"]["ota"] = {"alvo": "s3", "id": "x", "versao": "1.1.0", "tipo": "atualizar",
                                                "estado": "baixando", "atualizado_em": agora()}


@pytest.mark.parametrize("prepara,motivo", [
    (_sem_registro, "sem_firmware"), (_sem_dados, "sem_dados"), (_offline, "offline"),
    (_bomba, "bomba_ligada"), (_versao_igual, "versao_igual"), (_em_curso, "ota_em_curso"),
])
def test_recusas_nao_publicam_nada(m, prepara, motivo):
    prepara(m)
    antes = json.dumps(m.db.store.get("devices"), default=str, sort_keys=True)
    r = reverter(m)
    assert r.status_code == 200
    assert r.json() == {"resultado": "recusada", "id": None, "motivo": motivo, "versao": None}
    assert m.publicados == []
    assert json.dumps(m.db.store.get("devices"), default=str, sort_keys=True) == antes


def test_versao_instalada_desconhecida_e_permitida(m):
    del m.db.store["devices"]["vaso-01"]["fw"]
    assert reverter(m).json()["resultado"] == "solicitada"


def test_ota_travada_mais_antiga_que_o_prazo_permite(m):
    m.db.store["devices"]["vaso-01"]["ota"] = {
        "alvo": "wroom", "id": "x", "versao": "2.0.0", "estado": "aplicando",
        "atualizado_em": agora() - timedelta(seconds=settings.ota_timeout_s + 5)}
    assert reverter(m).json()["resultado"] == "solicitada"


def test_reverter_com_atualizar_em_curso_e_recusado(m):
    m.db.store["firmware"]["wroom"]["versao"] = "3.0.0"
    assert m.client.post("/dispositivos/vaso-01/atualizar", headers=APP, json={"alvo": "wroom"}
                         ).json()["resultado"] == "solicitada"
    assert reverter(m).json()["motivo"] == "ota_em_curso"
    assert len(m.publicados) == 1


# ---------- entrada ----------

@pytest.mark.parametrize("corpo", [{"alvo": "esp32"}, {"alvo": None}, {}, {"versao": "1.0.0"}])
def test_alvo_invalido_da_422(m, corpo):
    assert reverter(m, corpo=corpo).status_code == 422


@pytest.mark.parametrize("device", ["vaso.01", "vaso%20x", "a" * 65])
def test_device_id_invalido_da_422(m, device):
    assert reverter(m, device=device).status_code == 422


def test_campos_extras_no_corpo_nao_mudam_o_comando(m):
    r = reverter(m, corpo={"alvo": "wroom", "versao": "9.9.9", "url": "https://evil.com/x"})
    assert m.publicados[0][1] == {"acao": "reverter", "alvo": "wroom", "id": r.json()["id"], "versao": "1.0.0"}


# ---------- falhas ----------

def test_falha_na_publicacao_marca_falhou_sem_500(m):
    m.erro_publicacao = ConnectionError("broker fora")
    j = reverter(m).json()
    assert (j["resultado"], j["motivo"], j["versao"]) == ("falhou", "não consegui falar com o broker", "1.0.0")
    assert m.ota["estado"] == "falhou" and m.ota["id"] == j["id"] and m.ota["tipo"] == "reverter"


def test_falha_incerta_grava_o_motivo_de_incerteza(m):
    class Incerta(Exception):
        incerta = True

    m.erro_publicacao = Incerta("caiu no meio")
    j = reverter(m).json()
    assert j["motivo"] == MOTIVO_INCERTO and m.ota["motivo"] == MOTIVO_INCERTO


def test_erro_inesperado_vira_502_sem_vazar_detalhes(m, monkeypatch, caplog):
    async def quebra(device_id):
        raise RuntimeError("segredo-interno do firestore")

    monkeypatch.setattr(repositorio, "ler_dispositivo", quebra)
    with caplog.at_level("ERROR", logger="greensync.dispositivos"):
        r = reverter(m)
    assert r.status_code == 502 and "segredo-interno" not in r.text and "firestore" not in r.text.lower()
    assert "pedido de reversão" in caplog.text and m.publicados == []


@pytest.mark.anyio
async def test_duas_chamadas_simultaneas_so_uma_publica(m):
    m.db.barreira = threading.Barrier(3)      # força as 3 leituras da transação a acontecerem juntas
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=m.app), base_url="http://t") as c:
        resp = await asyncio.gather(*[
            c.post("/dispositivos/vaso-01/reverter", headers=ADMIN, json={"alvo": "wroom"}) for _ in range(3)])
    resultados = sorted(f'{r.json()["resultado"]}:{r.json()["motivo"]}' for r in resp)
    assert resultados == ["recusada:ota_em_curso", "recusada:ota_em_curso", "solicitada:None"]
    assert len(m.publicados) == 1


# ---------- progresso do tipo reverter ----------

def _msg(estado, ota_id, alvo="wroom", versao="1.0.0", **kw):
    payload = {"alvo": alvo, "id": ota_id, "estado": estado, "versao": versao, **kw}
    return SimpleNamespace(topic=SimpleNamespace(value="greensync/vaso-01/ota"),
                           payload=json.dumps(payload).encode())


@pytest.mark.anyio
async def test_ciclo_solicitada_aplicando_revertido_e_libera_nova_tentativa(m):
    ota_id = reverter(m).json()["id"]
    await mqtt_client.handle_message(_msg("aplicando", ota_id))
    assert m.ota["estado"] == "aplicando" and m.ota["tipo"] == "reverter"
    await mqtt_client.handle_message(_msg("revertido", ota_id, erro="hash"))
    assert (m.ota["estado"], m.ota["motivo"]) == ("revertido", "hash")
    await mqtt_client.handle_message(_msg("aplicando", ota_id))             # depois do final nada muda
    assert m.ota["estado"] == "revertido"
    m.db.store["devices"]["vaso-01"]["fw"] = "2.0.0"
    nova = reverter(m).json()
    assert nova["resultado"] == "solicitada" and nova["id"] != ota_id


# ---------- ciclo completo: retirar -> atualizar (para a versão boa) -> ok ----------

@pytest.mark.anyio
async def test_ciclo_retirar_atualizar_ok(m):
    # Registro: 2.0.0 (ruim) atual, 1.0.0 (boa) anterior. O vaso instalou a 2.0.0.
    m.db.store["firmware"]["wroom"] = {
        "versao": "2.0.0", "url": URL_RUIM, "sha256": HASH_RUIM, "notas": None, "publicado_em": agora(),
        "anterior": {"versao": "1.0.0", "url": URL_BOA, "sha256": HASH_BOA}, "bloqueadas": []}
    r = m.client.post("/firmware/wroom/retirar", headers=ADMIN)
    assert r.status_code == 200 and r.json()["versao"] == "1.0.0" and r.json()["bloqueadas"] == ["2.0.0"]

    r = m.client.post("/dispositivos/vaso-01/atualizar", headers=APP, json={"alvo": "wroom"})
    j = r.json()
    assert j["resultado"] == "solicitada" and j["versao"] == "1.0.0"
    assert m.publicados[0][1] == {"acao": "atualizar", "alvo": "wroom", "id": j["id"], "versao": "1.0.0",
                                  "url": URL_BOA, "sha256": HASH_BOA}

    for estado in ("baixando", "aplicando", "ok"):
        await mqtt_client.handle_message(_msg(estado, j["id"]))
    assert m.ota["estado"] == "ok"

    # O status do vaso informa a versão nova; aí a mesma atualização passa a ser "versao_igual".
    m.db.store["devices"]["vaso-01"]["fw"] = "1.0.0"
    assert m.client.post("/dispositivos/vaso-01/atualizar", headers=APP, json={"alvo": "wroom"}
                         ).json()["motivo"] == "versao_igual"
    # E a versão ruim não pode ser cadastrada de novo.
    r = m.client.put("/firmware/wroom", headers=ADMIN,
                     json={"versao": "2.0.0", "url": URL_RUIM, "sha256": HASH_RUIM})
    assert r.status_code == 409
