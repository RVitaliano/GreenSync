"""Progresso do OTA informado pelo vaso (greensync/{id}/ota) -> devices/{id}.ota."""
import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import aiomqtt
import pytest
from pydantic import ValidationError

from app import mqtt_client
from app.ai.estado import avaliar_estado
from app.config import settings
from app.models import OtaProgresso
from app.ota import repositorio, servico
from tests.falso_firestore import FIRESTORE_FALSO, DbFalso
from tests.falsos import leitura_ok

pytestmark = pytest.mark.anyio

OTA_ID = "a1b2c3d4e5f60718293a4b5c6d7e8f90"
ANTES = datetime(2026, 1, 1, tzinfo=timezone.utc)


def progresso(estado="baixando", **kw):
    return {"alvo": "wroom", "id": OTA_ID, "estado": estado, "versao": "2.0.0", **kw}


def mensagem(payload, device="vaso-01"):
    bruto = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    return SimpleNamespace(topic=SimpleNamespace(value=f"greensync/{device}/ota"), payload=bruto)


@pytest.fixture
def db(monkeypatch):
    db = DbFalso()
    db.store["devices"] = {"vaso-01": {"status": "online", "fw": "1.0.0", "fw_s3": "1.0.0",
                                        "ota": {"alvo": "wroom", "id": OTA_ID, "versao": "2.0.0",
                                                "estado": "solicitada", "atualizado_em": ANTES}}}
    monkeypatch.setattr(repositorio, "init_firebase", lambda: db)
    monkeypatch.setattr(repositorio, "firestore", FIRESTORE_FALSO)
    return db


def ota(db):
    return db.doc("devices", "vaso-01")["ota"]


# ---------- tópico e modelo ----------

def test_parse_topic_reconhece_ota():
    assert mqtt_client.parse_topic("greensync/vaso-01/ota") == ("vaso-01", "ota")


def test_topico_padrao_da_configuracao():
    assert settings.mqtt_topic_ota == "greensync/+/ota"


def test_modelo_valido_e_campos_extras_ignorados():
    p = OtaProgresso.model_validate({**progresso("ok"), "lixo": 1, "url": "https://x"})
    assert (p.alvo, p.id, p.estado, p.versao, p.erro) == ("wroom", OTA_ID, "ok", "2.0.0", None)


@pytest.mark.parametrize("campo,valor", [
    ("alvo", "esp32"), ("alvo", None),
    ("id", ""), ("id", "a" * 65), ("id", "a b"), ("id", "abc\n"), ("id", "a/b"), ("id", 5),
    ("estado", "solicitada"), ("estado", "x"), ("estado", None),
    ("versao", "1.0"), ("versao", "v1.0.0"), ("versao", 3), ("versao", "SEGREDO"),
])
def test_modelo_recusa_campos_invalidos(campo, valor):
    with pytest.raises(ValidationError):
        OtaProgresso.model_validate({**progresso("falhou"), campo: valor})


@pytest.mark.parametrize("campo", ["alvo", "id", "estado", "versao"])
def test_modelo_recusa_campo_faltando(campo):
    dados = progresso()
    del dados[campo]
    with pytest.raises(ValidationError):
        OtaProgresso.model_validate(dados)


@pytest.mark.parametrize("erro", ["hash", "download", "bomba_ligada", "versao_igual", "espaco", "a" * 32, "e1"])
def test_codigo_de_erro_valido_e_mantido(erro):
    assert OtaProgresso.model_validate(progresso("falhou", erro=erro)).erro == erro


@pytest.mark.parametrize("erro", ["Hash", "erro de hash", "a" * 33, "", "hash!", "ação", 5, ["x"], "x\n"])
def test_codigo_de_erro_invalido_vira_desconhecido(erro):
    assert OtaProgresso.model_validate(progresso("falhou", erro=erro)).erro == "desconhecido"


@pytest.mark.parametrize("estado", ["baixando", "aplicando", "ok"])
def test_erro_e_ignorado_fora_de_falhou_e_revertido(estado):
    assert OtaProgresso.model_validate(progresso(estado, erro="hash")).erro is None


def test_erro_vale_em_revertido():
    assert OtaProgresso.model_validate(progresso("revertido", erro="boot")).erro == "boot"


# ---------- aplicar o progresso ----------

@pytest.mark.parametrize("estado", ["baixando", "aplicando", "ok", "falhou", "revertido"])
async def test_cada_estado_valido_atualiza(db, estado):
    await mqtt_client.handle_message(mensagem(progresso(estado)))
    o = ota(db)
    assert o["estado"] == estado
    assert o["atualizado_em"] > ANTES
    assert (o["id"], o["alvo"], o["versao"]) == (OTA_ID, "wroom", "2.0.0")


async def test_erro_vira_motivo(db):
    await mqtt_client.handle_message(mensagem(progresso("falhou", erro="hash")))
    assert ota(db)["estado"] == "falhou" and ota(db)["motivo"] == "hash"


async def test_erro_invalido_grava_desconhecido_como_motivo(db):
    await mqtt_client.handle_message(mensagem(progresso("revertido", erro="Texto livre qualquer")))
    assert ota(db)["motivo"] == "desconhecido"


async def test_sem_erro_nao_grava_motivo(db):
    await mqtt_client.handle_message(mensagem(progresso("aplicando", erro="hash")))
    assert "motivo" not in ota(db)


# ---------- o que deve ser ignorado ----------

def _copia(db):
    return json.dumps(db.store, default=str, sort_keys=True)


@pytest.mark.parametrize("alteracao", [{"id": "outra-atualizacao"}, {"alvo": "s3"}])
async def test_id_ou_alvo_diferente_e_ignorado(db, alteracao, caplog):
    antes = _copia(db)
    with caplog.at_level(logging.WARNING, logger="greensync.ota"):
        await mqtt_client.handle_message(mensagem({**progresso("ok"), **alteracao}))
    assert _copia(db) == antes
    assert "ignorado" in caplog.text


async def test_vaso_sem_ota_e_ignorado(db):
    del db.store["devices"]["vaso-01"]["ota"]
    antes = _copia(db)
    await mqtt_client.handle_message(mensagem(progresso("ok")))
    assert _copia(db) == antes


async def test_vaso_sem_documento_e_ignorado(db):
    await mqtt_client.handle_message(mensagem(progresso("ok"), device="vaso-99"))
    assert db.doc("devices", "vaso-99") is None


async def test_regressao_e_ignorada(db):
    await mqtt_client.handle_message(mensagem(progresso("aplicando")))
    antes = _copia(db)
    await mqtt_client.handle_message(mensagem(progresso("baixando")))
    assert _copia(db) == antes and ota(db)["estado"] == "aplicando"


@pytest.mark.parametrize("final", ["ok", "falhou", "revertido"])
@pytest.mark.parametrize("depois", ["baixando", "aplicando", "ok", "falhou", "revertido"])
async def test_depois_de_estado_final_nada_muda(db, final, depois):
    await mqtt_client.handle_message(mensagem(progresso(final)))
    antes = _copia(db)
    await mqtt_client.handle_message(mensagem(progresso(depois, erro="hash")))
    assert _copia(db) == antes
    assert ota(db)["estado"] == final


async def test_mensagem_repetida_e_aceita_e_so_renova_atualizado_em(db):
    await mqtt_client.handle_message(mensagem(progresso("baixando")))
    db.store["devices"]["vaso-01"]["ota"]["atualizado_em"] = ANTES          # "envelhece" o registro
    await mqtt_client.handle_message(mensagem(progresso("baixando")))      # QoS 1 duplicou
    o = ota(db)
    assert o["estado"] == "baixando" and o["atualizado_em"] > ANTES


async def test_pular_etapas_para_frente_e_aceito(db):
    await mqtt_client.handle_message(mensagem(progresso("ok")))            # perdeu "baixando"/"aplicando"
    assert ota(db)["estado"] == "ok"


# ---------- ok não mexe na versão instalada ----------

async def test_ok_nao_altera_fw_nem_fw_s3(db):
    await mqtt_client.handle_message(mensagem(progresso("ok")))
    d = db.doc("devices", "vaso-01")
    assert (d["fw"], d["fw_s3"], d["status"]) == ("1.0.0", "1.0.0", "online")


# ---------- payload inválido ----------

@pytest.mark.parametrize("payload", [
    b"isso nao e json", b"[]", b"null", b"{}",
    json.dumps({**progresso(), "estado": "talvez"}).encode(),
    json.dumps({**progresso(), "versao": "SEGREDO-NO-PAYLOAD"}).encode(),
])
async def test_payload_invalido_e_descartado_sem_excecao_e_sem_vazar(db, payload, caplog):
    antes = _copia(db)
    with caplog.at_level(logging.DEBUG):
        await mqtt_client.handle_message(mensagem(payload))
    assert _copia(db) == antes
    assert "SEGREDO-NO-PAYLOAD" not in caplog.text and "isso nao e json" not in caplog.text
    assert "inválido" in caplog.text


# ---------- ciclo completo com o pedido (P3) ----------

@pytest.fixture
def pedido(db, monkeypatch):
    db.store["firmware"] = {"wroom": {"versao": "2.0.0", "url": "https://github.com/o/r/fw.bin",
                                      "sha256": "ab" * 32, "notas": None, "anterior": None}}
    db.store["devices"]["vaso-01"].pop("ota")
    publicados = []

    async def publicar(device_id, payload):
        publicados.append(payload)

    monkeypatch.setattr(servico, "publicar_comando", publicar)

    async def solicitar(alvo="wroom"):
        leitura = leitura_ok()
        return await servico.solicitar_atualizacao("vaso-01", alvo, leitura, avaliar_estado(leitura))

    solicitar.publicados = publicados
    return solicitar


async def test_ciclo_completo_solicitada_baixando_aplicando_ok(db, pedido):
    r = await pedido()
    assert r["resultado"] == "solicitada" and ota(db)["estado"] == "solicitada"
    ota_id = r["id"]
    for estado in ("baixando", "aplicando", "ok"):
        await mqtt_client.handle_message(mensagem({**progresso(estado), "id": ota_id}))
        assert ota(db)["estado"] == estado
    assert db.doc("devices", "vaso-01")["fw"] == "1.0.0"                       # só o status muda a versão
    # terminou: pode pedir outra (a mesma versão só é recusada quando o status informar 2.0.0)
    assert (await pedido())["resultado"] == "solicitada"


@pytest.mark.parametrize("final,erro", [("falhou", "hash"), ("revertido", "boot")])
async def test_ciclo_com_falha_ou_reversao_libera_nova_tentativa(db, pedido, final, erro):
    ota_id = (await pedido())["id"]
    await mqtt_client.handle_message(mensagem({**progresso("baixando"), "id": ota_id}))
    await mqtt_client.handle_message(mensagem({**progresso(final, erro=erro), "id": ota_id}))
    assert (ota(db)["estado"], ota(db)["motivo"]) == (final, erro)
    nova = await pedido()
    assert nova["resultado"] == "solicitada" and nova["id"] != ota_id


async def test_andamento_renova_o_prazo_de_ota_em_curso(db, pedido):
    ota_id = (await pedido())["id"]
    db.store["devices"]["vaso-01"]["ota"]["atualizado_em"] = (
        datetime.now(timezone.utc) - timedelta(seconds=settings.ota_timeout_s + 60))     # estava travada
    await mqtt_client.handle_message(mensagem({**progresso("baixando"), "id": ota_id}))
    assert (await pedido())["motivo"] == "ota_em_curso"                                    # voltou a andar


# ---------- assinante MQTT ----------

class ClienteFalso:
    instancias = []
    roteiros = []          # um roteiro por conexão: lista de mensagens, ou exceção para levantar no fim

    def __init__(self, **kw):
        self.assinaturas = []
        self.roteiro = ClienteFalso.roteiros[len(ClienteFalso.instancias)]
        ClienteFalso.instancias.append(self)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def subscribe(self, topico, qos=0):
        self.assinaturas.append((topico, qos))

    @property
    def messages(self):
        async def gerar():
            for item in self.roteiro:
                if isinstance(item, BaseException):
                    raise item
                yield item
        return gerar()


@pytest.fixture
def broker(monkeypatch):
    ClienteFalso.instancias, ClienteFalso.roteiros = [], []

    async def sem_espera(s):
        pass

    monkeypatch.setattr(mqtt_client.aiomqtt, "Client", ClienteFalso)
    monkeypatch.setattr(mqtt_client.asyncio, "sleep", sem_espera)
    return ClienteFalso


async def test_falha_no_firestore_nao_derruba_o_assinante(broker, monkeypatch, caplog):
    chamadas = []

    async def tratar(device_id, p):
        chamadas.append(p.estado)
        if len(chamadas) == 1:
            raise RuntimeError("firestore fora do ar")

    monkeypatch.setattr(mqtt_client, "tratar_progresso", tratar)
    broker.roteiros = [[mensagem(progresso("baixando")), mensagem(progresso("aplicando")), asyncio.CancelledError()]]
    with caplog.at_level(logging.ERROR, logger="greensync.mqtt"):
        with pytest.raises(asyncio.CancelledError):
            await mqtt_client.run_mqtt_subscriber()
    assert chamadas == ["baixando", "aplicando"]            # a 2ª mensagem ainda foi tratada
    assert "Erro inesperado ao processar mensagem" in caplog.text


async def test_reassinatura_a_cada_reconexao_inclui_o_topico_ota(broker):
    broker.roteiros = [[aiomqtt.MqttError("caiu")], [asyncio.CancelledError()]]
    with pytest.raises(asyncio.CancelledError):
        await mqtt_client.run_mqtt_subscriber()
    assert len(broker.instancias) == 2
    esperado = [(settings.mqtt_topic_sensores, 1), (settings.mqtt_topic_status, 1), (settings.mqtt_topic_ota, 1)]
    for c in broker.instancias:
        assert c.assinaturas == esperado
    assert ("greensync/+/ota", 1) in broker.instancias[1].assinaturas
