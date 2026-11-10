"""Entrada MQTT: id do vaso, timestamp do ESP e resistência do laço de reconexão."""
import asyncio
import logging
from datetime import datetime, timezone
from types import SimpleNamespace

import aiomqtt
import pytest

from app import firebase_client, mqtt_client
from app.models import SensorReading

pytestmark = pytest.mark.anyio

PAYLOAD = b'{"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1, "bomba_ligada": false}'


def mensagem(topico, payload=PAYLOAD):
    return SimpleNamespace(topic=SimpleNamespace(value=topico), payload=payload)


# ---------- device_id vindo do tópico ----------

@pytest.mark.parametrize("topico", [
    "greensync//sensores",         # id vazio: o Firestore recusaria o documento
    "greensync/../sensores",
    "greensync/./sensores",
    "greensync/vaso 01/sensores",
    "greensync/vaso.01/sensores",
    "greensync/" + "a" * 65 + "/sensores",
])
async def test_device_id_invalido_no_topico_nao_grava(monkeypatch, topico):
    gravados = []

    async def salvar(device_id, reading):
        gravados.append(device_id)

    monkeypatch.setattr(mqtt_client, "save_reading", salvar)
    await mqtt_client.handle_message(mensagem(topico))
    assert gravados == []


async def test_device_id_valido_grava(monkeypatch):
    gravados = []

    async def salvar(device_id, reading):
        gravados.append(device_id)

    monkeypatch.setattr(mqtt_client, "save_reading", salvar)
    await mqtt_client.handle_message(mensagem("greensync/vaso-01/sensores"))
    assert gravados == ["vaso-01"]


async def test_status_com_id_invalido_nao_grava(monkeypatch):
    gravados = []

    async def salvar(device_id, status):
        gravados.append(device_id)

    monkeypatch.setattr(mqtt_client, "save_status", salvar)
    await mqtt_client.handle_message(mensagem("greensync/../status", b'{"status": "offline"}'))
    assert gravados == []


# ---------- timestamp do ESP ----------

AGORA = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc).timestamp()


def test_timestamp_razoavel_e_mantido():
    ts = int(AGORA) - 30
    assert firebase_client.timestamp_confiavel(ts, AGORA) == datetime.fromtimestamp(ts, tz=timezone.utc)


@pytest.mark.parametrize("ts", [
    0,                                        # relógio sem acerto (1970)
    123456,                                   # contador desde o boot
    1_500_000_000,                            # 2017: antes de 2020
    int(AGORA) + 2 * 3600,                    # 2 h no futuro
    4_102_444_800,                            # ano 2100
    10**15,                                   # estoura datetime.fromtimestamp
])
def test_timestamp_absurdo_vira_none_e_usa_hora_do_servidor(ts):
    assert firebase_client.timestamp_confiavel(ts, AGORA) is None


def test_sem_timestamp_vira_none():
    assert firebase_client.timestamp_confiavel(None, AGORA) is None


class DocFalso:
    def __init__(self, gravados, caminho):
        self.gravados, self.caminho = gravados, caminho

    def collection(self, nome):
        return DocFalso(self.gravados, self.caminho + [nome])

    def document(self, nome=None):
        return DocFalso(self.gravados, self.caminho + [nome or "auto"])


class DbFalso:
    def __init__(self):
        self.gravados = []

    def collection(self, nome):
        return DocFalso(self.gravados, [nome])

    def batch(self):
        gravados = self.gravados

        class Lote:
            def set(self, ref, dados, merge=False):
                gravados.append((tuple(ref.caminho), dados))

            def commit(self):
                pass

        return Lote()


@pytest.mark.parametrize("ts", [0, 10**15, 4_102_444_800])
def test_historico_nao_grava_timestamp_absurdo(monkeypatch, ts):
    db = DbFalso()
    monkeypatch.setattr(firebase_client, "init_firebase", lambda: db)
    leitura = SensorReading(ph=6.4, umidade_solo=42, temperatura_ar=24, bomba_ligada=False, timestamp=ts)
    firebase_client._save_reading_sync("vaso-01", leitura)
    historico = [d for caminho, d in db.gravados if "historico" in caminho][0]
    assert historico["timestamp"] is firebase_client.firestore.SERVER_TIMESTAMP


def test_historico_mantem_timestamp_razoavel(monkeypatch):
    db = DbFalso()
    monkeypatch.setattr(firebase_client, "init_firebase", lambda: db)
    ts = int(datetime.now(timezone.utc).timestamp()) - 10
    leitura = SensorReading(ph=6.4, umidade_solo=42, temperatura_ar=24, bomba_ligada=False, timestamp=ts)
    firebase_client._save_reading_sync("vaso-01", leitura)
    historico = [d for caminho, d in db.gravados if "historico" in caminho][0]
    assert historico["timestamp"] == datetime.fromtimestamp(ts, tz=timezone.utc)


# ---------- laço de reconexão ----------

async def test_erro_inesperado_nao_mata_o_assinante(monkeypatch, caplog):
    """Um erro que não seja MqttError (ex.: bug, falha de DNS crua) deve ser logado e tentado de novo."""
    tentativas = []
    esperas = []

    class ClienteQueQuebra:
        def __init__(self, **kw):
            tentativas.append(1)

        async def __aenter__(self):
            if len(tentativas) == 1:
                raise RuntimeError("falha qualquer")
            raise asyncio.CancelledError    # 2ª volta: só para sair do laço no teste

        async def __aexit__(self, *a):
            return False

    async def sem_espera(s):
        esperas.append(s)

    monkeypatch.setattr(mqtt_client.aiomqtt, "Client", ClienteQueQuebra)
    monkeypatch.setattr(mqtt_client.asyncio, "sleep", sem_espera)
    with caplog.at_level(logging.ERROR, logger="greensync.mqtt"):
        with pytest.raises(asyncio.CancelledError):
            await mqtt_client.run_mqtt_subscriber()
    assert len(tentativas) == 2          # voltou a tentar depois do erro
    assert esperas == [5]
    assert "Erro inesperado" in caplog.text
    assert mqtt_client._cliente is None


async def test_erro_de_conexao_continua_tratado(monkeypatch):
    tentativas = []

    class ClienteSemBroker:
        def __init__(self, **kw):
            tentativas.append(1)

        async def __aenter__(self):
            if len(tentativas) == 1:
                raise aiomqtt.MqttError("sem broker")
            raise asyncio.CancelledError

        async def __aexit__(self, *a):
            return False

    async def sem_espera(s):
        pass

    monkeypatch.setattr(mqtt_client.aiomqtt, "Client", ClienteSemBroker)
    monkeypatch.setattr(mqtt_client.asyncio, "sleep", sem_espera)
    with pytest.raises(asyncio.CancelledError):
        await mqtt_client.run_mqtt_subscriber()
    assert len(tentativas) == 2
