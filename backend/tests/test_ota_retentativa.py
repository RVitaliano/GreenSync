"""OTA automático: retentativa em memória (sem_dados/bomba_ligada) e ota_auto por alvo."""
import asyncio
import json
from types import SimpleNamespace

import pytest

from app import mqtt_client
from app.config import settings
from app.ota import automatico, repositorio
from tests.falsos import leitura_ok
from tests.test_ota_automatico import (  # noqa: F401  (m é um fixture reaproveitado)
    URL, Montagem, agora, chega_status, m,
)

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def estado_limpo(m, monkeypatch):
    """A lista de pendentes é global do módulo: cada teste começa e termina com ela vazia."""
    automatico._pendentes.clear()

    async def salvar_leitura(device_id, reading):       # no lugar do Firestore real
        pass

    monkeypatch.setattr(mqtt_client, "save_reading", salvar_leitura)
    yield
    automatico._pendentes.clear()


def leitura_msg(device_id):
    payload = {"ph": 6.4, "umidade_solo": 40, "temperatura_ar": 24, "bomba_ligada": False}
    return SimpleNamespace(topic=SimpleNamespace(value=f"greensync/{device_id}/sensores"),
                           payload=json.dumps(payload).encode())


async def chega_leitura(device_id):
    await mqtt_client.handle_message(leitura_msg(device_id))
    await automatico.aguardar_pendentes()


def espiar(monkeypatch):
    """Conta as leituras do Firestore feitas pelo OTA automático."""
    chamadas = {"dispositivo": 0, "registro": 0}
    ler_dispositivo, ler = repositorio.ler_dispositivo, repositorio.ler

    async def espia_dispositivo(device_id):
        chamadas["dispositivo"] += 1
        return await ler_dispositivo(device_id)

    async def espia_registro(alvo):
        chamadas["registro"] += 1
        return await ler(alvo)

    monkeypatch.setattr(repositorio, "ler_dispositivo", espia_dispositivo)
    monkeypatch.setattr(repositorio, "ler", espia_registro)
    return chamadas


# ------------------------------------------------------------ reagenda ----

@pytest.mark.parametrize("problema", ["bomba_ligada", "sem_dados"])
async def test_recusa_temporaria_reagenda_na_proxima_leitura(m, problema):
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True) if problema == "bomba_ligada" else None
    await chega_status(m, "v1", fw="1.0.0")
    assert m.publicados == [] and "v1" in automatico._pendentes       # recusado, ficou pendente

    m.leituras["v1"] = leitura_ok()                                   # o problema passou
    await chega_leitura("v1")
    assert len(m.publicados) == 1 and m.para("v1")[0]["acao"] == "atualizar"
    assert "v1" not in automatico._pendentes                          # resolvido: sai da lista


async def test_continua_pendente_enquanto_o_problema_durar_e_para_no_limite(m, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto_retentativas", 3)
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)                  # nunca resolve
    verificacoes = []
    original = automatico.verificar_vaso_online

    async def espia(device_id):
        verificacoes.append(device_id)
        await original(device_id)

    monkeypatch.setattr(automatico, "verificar_vaso_online", espia)
    await chega_status(m, "v1", fw="1.0.0")                           # 1ª recusa (não é retentativa)
    verificacoes.clear()
    for _ in range(8):
        await chega_leitura("v1")
    assert len(verificacoes) == 3                                     # OTA_AUTO_RETENTATIVAS = 3
    assert m.publicados == [] and "v1" not in automatico._pendentes   # desistiu


async def test_novo_status_online_recomeca_depois_de_desistir(m, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto_retentativas", 1)
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    await chega_leitura("v1")
    await chega_leitura("v1")
    assert "v1" not in automatico._pendentes
    m.leituras["v1"] = leitura_ok()
    await chega_status(m, "v1", fw="1.0.0")                           # o vaso reconectou
    assert len(m.publicados) == 1


async def test_cada_leitura_dispara_uma_verificacao_so(m, monkeypatch):
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    chamadas = espiar(monkeypatch)
    await chega_leitura("v1")
    assert chamadas["dispositivo"] >= 1
    lidas = chamadas["dispositivo"]
    await chega_leitura("v1")
    assert chamadas["dispositivo"] == 2 * lidas                      # uma verificação por leitura, não mais


async def test_leituras_seguidas_nao_rodam_duas_verificacoes_ao_mesmo_tempo(m, monkeypatch):
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    rodando, maximo = 0, 0
    original = automatico.verificar_vaso_online

    async def lenta(device_id):
        nonlocal rodando, maximo
        rodando += 1
        maximo = max(maximo, rodando)
        await asyncio.sleep(0.05)
        await original(device_id)
        rodando -= 1

    monkeypatch.setattr(automatico, "verificar_vaso_online", lenta)
    for _ in range(4):
        await mqtt_client.handle_message(leitura_msg("v1"))           # sem esperar a verificação
    await automatico.aguardar_pendentes()
    assert maximo == 1


async def test_o_pedido_do_put_tambem_marca_pendente(m):
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await automatico.despachar_para_vasos_online("wroom")
    assert "v1" in automatico._pendentes
    assert automatico._pendentes["v1"]["alvos"] == {"wroom"}


# ------------------------------------------- o que NÃO deve ficar pendente ----

@pytest.mark.parametrize("cenario", ["offline", "versao_igual", "ota_em_curso", "limite", "maior", "bloqueada"])
async def test_outras_recusas_nao_ficam_pendentes(m, cenario):
    m.vaso("v1", fw="1.0.0")
    if cenario == "offline":
        m.leituras["v1"] = leitura_ok(status_vaso="offline")
    elif cenario == "versao_igual":
        m.db.store["devices"]["v1"]["fw"] = "2.0.0"
    elif cenario == "ota_em_curso":
        m.db.store["devices"]["v1"]["ota"] = {"alvo": "wroom", "id": "x", "versao": "2.0.0", "tipo": "atualizar",
                                              "estado": "baixando", "atualizado_em": agora()}
    elif cenario == "limite":
        m.db.store["devices"]["v1"]["ota_auto"] = {"wroom": {"versao": "2.0.0", "tentativas": 2, "ultimo_erro": None}}
    elif cenario == "maior":
        m.db.store["devices"]["v1"]["fw"] = "9.0.0"
    elif cenario == "bloqueada":
        m.db.store["firmware"]["wroom"]["bloqueadas"] = ["2.0.0"]
    await chega_status(m, "v1", fw=m.db.store["devices"]["v1"]["fw"])
    assert "v1" not in automatico._pendentes
    assert m.publicados == []


async def test_retentativas_zero_nunca_marca(m, monkeypatch):
    monkeypatch.setattr(settings, "ota_auto_retentativas", 0)
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    assert automatico._pendentes == {}


# ------------------------------------------------ sem custo para os demais ----

async def test_leitura_de_vaso_nao_pendente_nao_le_o_firestore(m, monkeypatch):
    m.vaso("v9", fw="1.0.0")
    chamadas = espiar(monkeypatch)
    for _ in range(10):
        await chega_leitura("v9")
    assert chamadas == {"dispositivo": 0, "registro": 0}
    assert automatico.retentar_se_pendente("v9") is False and m.publicados == []


async def test_leitura_de_um_vaso_nao_verifica_outro_pendente(m, monkeypatch):
    m.vaso("v1", fw="1.0.0")
    m.vaso("v2", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    chamadas = espiar(monkeypatch)
    await chega_leitura("v2")                                        # v2 não está pendente
    assert chamadas == {"dispositivo": 0, "registro": 0}
    assert "v1" in automatico._pendentes


async def test_com_ota_auto_desligado_a_leitura_nao_faz_nada(m, monkeypatch):
    m.vaso("v1", fw="1.0.0")
    m.leituras["v1"] = leitura_ok(bomba_ligada=True)
    await chega_status(m, "v1", fw="1.0.0")
    monkeypatch.setattr(settings, "ota_auto", False)
    chamadas = espiar(monkeypatch)
    m.leituras["v1"] = leitura_ok()
    await chega_leitura("v1")
    assert chamadas == {"dispositivo": 0, "registro": 0} and m.publicados == []


# ----------------------------------------------------- ota_auto por alvo ----

async def test_formato_antigo_do_ota_auto_e_ignorado_e_limpo_na_gravacao(m):
    m.vaso("v1", fw="1.0.0",
           ota_auto={"alvo": "wroom", "versao": "2.0.0", "tentativas": 5, "ultimo_erro": "hash"})   # antigo
    await chega_status(m, "v1", fw="1.0.0")
    assert len(m.publicados) == 1                                     # as 5 tentativas antigas não contam
    assert m.doc("v1")["ota_auto"] == {"wroom": {"versao": "2.0.0", "tentativas": 1, "ultimo_erro": None}}


async def test_cada_alvo_tem_a_sua_contagem(m):
    m.vaso("v1", fw="1.0.0", fw_s3="1.0.0",
           ota_auto={"wroom": {"versao": "2.0.0", "tentativas": 2, "ultimo_erro": "hash"}})
    await chega_status(m, "v1", fw="1.0.0", fw_s3="1.0.0")
    assert [p["alvo"] for _, p in m.publicados] == ["s3"]            # wroom esgotou; s3 tem a própria contagem
    auto = m.doc("v1")["ota_auto"]
    assert auto["wroom"]["tentativas"] == 2 and auto["s3"]["tentativas"] == 1


async def test_gravar_um_alvo_nao_apaga_o_outro(m):
    m.vaso("v1", fw="1.0.0", fw_s3="1.0.0",
           ota_auto={"wroom": {"versao": "1.9.0", "tentativas": 1, "ultimo_erro": "download"}})
    await repositorio.registrar_tentativa_auto("v1", "s3", "2.0.0")
    assert m.doc("v1")["ota_auto"] == {
        "wroom": {"versao": "1.9.0", "tentativas": 1, "ultimo_erro": "download"},
        "s3": {"versao": "2.0.0", "tentativas": 1, "ultimo_erro": None},
    }


async def test_zerar_um_alvo_so_mexe_nele(m):
    m.vaso("v1", fw="2.0.0", ota_auto={
        "wroom": {"versao": "2.0.0", "tentativas": 2, "ultimo_erro": "hash"},
        "s3": {"versao": "2.0.0", "tentativas": 1, "ultimo_erro": None}})
    assert await repositorio.zerar_tentativas_auto("v1", "wroom", "2.0.0") is True
    assert m.doc("v1")["ota_auto"]["wroom"] == {"versao": "2.0.0", "tentativas": 0, "ultimo_erro": None}
    assert m.doc("v1")["ota_auto"]["s3"]["tentativas"] == 1
    assert await repositorio.zerar_tentativas_auto("v1", "wroom", "2.0.0") is False      # já zerado
