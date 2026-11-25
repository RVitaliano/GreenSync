"""Status do vaso com versão de firmware (fw, fw_s3)."""
import logging
from types import SimpleNamespace

import pytest

from app import firebase_client, mqtt_client
from app.models import DeviceStatus

pytestmark = pytest.mark.anyio


# ---------- modelo ----------

def test_payload_antigo_continua_valido():
    s = DeviceStatus.model_validate_json('{"status": "online"}')
    assert (s.status, s.fw, s.fw_s3) == ("online", None, None)


def test_last_will_continua_valido():
    s = DeviceStatus.model_validate_json('{"status": "offline"}')
    assert (s.status, s.fw, s.fw_s3) == ("offline", None, None)


def test_status_com_as_duas_versoes():
    s = DeviceStatus.model_validate_json('{"status": "online", "fw": "1.0.0", "fw_s3": "1.2.0-rc1"}')
    assert (s.fw, s.fw_s3) == ("1.0.0", "1.2.0-rc1")


@pytest.mark.parametrize("bruto", ['"lixo"', '"v1.0"', '""', "42", "true", '"1.0.0-' + "a" * 40 + '"'])
def test_versao_invalida_vira_none_e_o_status_continua_valido(bruto, caplog):
    with caplog.at_level(logging.WARNING, logger="greensync.models"):
        s = DeviceStatus.model_validate_json('{"status": "online", "fw": %s, "fw_s3": "1.0.0"}' % bruto)
    assert s.status == "online" and s.fw is None and s.fw_s3 == "1.0.0"
    assert "fw" in caplog.text


def test_status_invalido_continua_recusado():
    with pytest.raises(Exception):
        DeviceStatus.model_validate_json('{"status": "talvez", "fw": "1.0.0"}')


# ---------- handle_message repassa ----------

def mensagem(payload):
    return SimpleNamespace(topic=SimpleNamespace(value="greensync/vaso-01/status"), payload=payload)


async def test_handle_message_repassa_as_versoes(monkeypatch):
    chamadas = []

    async def salvar(device_id, status, fw=None, fw_s3=None):
        chamadas.append((device_id, status, fw, fw_s3))

    monkeypatch.setattr(mqtt_client, "save_status", salvar)
    await mqtt_client.handle_message(mensagem(b'{"status": "online", "fw": "1.0.0", "fw_s3": "2.0.0"}'))
    await mqtt_client.handle_message(mensagem(b'{"status": "offline"}'))
    assert chamadas == [("vaso-01", "online", "1.0.0", "2.0.0"), ("vaso-01", "offline", None, None)]


async def test_handle_message_com_fw_torta_ainda_grava_o_status(monkeypatch):
    chamadas = []

    async def salvar(device_id, status, fw=None, fw_s3=None):
        chamadas.append((status, fw))

    monkeypatch.setattr(mqtt_client, "save_status", salvar)
    await mqtt_client.handle_message(mensagem(b'{"status": "online", "fw": "banana"}'))
    assert chamadas == [("online", None)]


# ---------- gravação no Firestore ----------

class DocFalso:
    def __init__(self, gravados):
        self.gravados = gravados

    def collection(self, nome):
        return self

    def document(self, nome):
        return self

    def set(self, dados, merge=False):
        self.gravados.append((dados, merge))


def _gravado(monkeypatch, **kw):
    gravados = []
    monkeypatch.setattr(firebase_client, "init_firebase", lambda: DocFalso(gravados))
    firebase_client._save_status_sync("vaso-01", "online", **kw)
    return gravados[0]


def test_grava_fw_e_fw_s3_quando_vem(monkeypatch):
    assert _gravado(monkeypatch, fw="1.0.0", fw_s3="2.0.0") == ({"status": "online", "fw": "1.0.0", "fw_s3": "2.0.0"}, True)


def test_grava_so_o_que_veio(monkeypatch):
    dados, merge = _gravado(monkeypatch, fw_s3="2.0.0")
    assert dados == {"status": "online", "fw_s3": "2.0.0"} and merge


def test_last_will_nao_apaga_a_versao_conhecida(monkeypatch):
    gravados = []
    monkeypatch.setattr(firebase_client, "init_firebase", lambda: DocFalso(gravados))
    firebase_client._save_status_sync("vaso-01", "offline")          # assinatura antiga
    dados, merge = gravados[0]
    assert dados == {"status": "offline"} and merge is True            # sem "fw": o merge preserva o antigo
    assert "fw" not in dados and "fw_s3" not in dados


async def test_save_status_com_assinatura_antiga_funciona(monkeypatch):
    gravados = []
    monkeypatch.setattr(firebase_client, "init_firebase", lambda: DocFalso(gravados))
    await firebase_client.save_status("vaso-01", "online")
    assert gravados[0][0] == {"status": "online"}
