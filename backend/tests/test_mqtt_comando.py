"""publicar_comando: tópico, QoS, retain e comportamento sem conexão (cliente MQTT falso)."""
import json

import aiomqtt
import pytest

from app import mqtt_client
from app.config import settings

pytestmark = pytest.mark.anyio


class ClienteFalso:
    def __init__(self, erro=None):
        self.publicacoes = []
        self.erro = erro

    async def publish(self, topic, payload, qos=0, retain=False, timeout=None):
        if self.erro:
            raise self.erro
        self.publicacoes.append({"topic": topic, "payload": payload, "qos": qos,
                                 "retain": retain, "timeout": timeout})


async def test_publica_no_topico_do_vaso_com_qos1_e_sem_retain(monkeypatch):
    c = ClienteFalso()
    monkeypatch.setattr(mqtt_client, "_cliente", c)
    await mqtt_client.publicar_comando("vaso-01", {"acao": "regar", "duracao_s": 5, "id": "ag1"})
    p = c.publicacoes[0]
    assert p["topic"] == "greensync/vaso-01/comandos"
    assert json.loads(p["payload"]) == {"acao": "regar", "duracao_s": 5, "id": "ag1"}
    assert p["qos"] == 1
    assert p["retain"] is False       # retain reentregaria o comando a quem reconectasse depois
    assert p["timeout"] is not None   # nunca fica esperando o broker para sempre


async def test_topico_vem_da_configuracao(monkeypatch):
    c = ClienteFalso()
    monkeypatch.setattr(mqtt_client, "_cliente", c)
    monkeypatch.setattr(settings, "mqtt_topic_comandos", "gs/{device_id}/cmd")
    await mqtt_client.publicar_comando("vaso-02", {"acao": "regar"})
    assert c.publicacoes[0]["topic"] == "gs/vaso-02/cmd"


async def test_sem_conexao_levanta_erro_proprio(monkeypatch):
    monkeypatch.setattr(mqtt_client, "_cliente", None)
    with pytest.raises(mqtt_client.MqttIndisponivel):
        await mqtt_client.publicar_comando("vaso-01", {"acao": "regar"})


async def test_erro_do_broker_vira_erro_proprio(monkeypatch):
    monkeypatch.setattr(mqtt_client, "_cliente", ClienteFalso(erro=aiomqtt.MqttError("caiu")))
    with pytest.raises(mqtt_client.MqttIndisponivel):
        await mqtt_client.publicar_comando("vaso-01", {"acao": "regar"})