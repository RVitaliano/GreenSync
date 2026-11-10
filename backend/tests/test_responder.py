"""Testa responder() e responder_audio() com um Gemini falso."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.ai import resiliencia, responder as mod
from app.ai.resiliencia import IAError
from app.ai.responder import ler_saida, responder, responder_audio
from app.config import settings

pytestmark = pytest.mark.anyio

LEITURA = {"umidade_solo": 20, "temperatura_ar": 24.1, "bomba_ligada": False}

NENHUMA = {"tipo": "nenhuma", "daqui_a_s": None, "as_hora": None, "duracao_s": None}


def texto_json(resposta="Estou com sede.", acao=None, ouviu=None):
    d = {"resposta": resposta, "acao": acao or NENHUMA}
    if ouviu is not None:
        d["pergunta_ouvida"] = ouviu
    return json.dumps(d)


class GeminiFalso:
    """Imita client.aio.models.generate_content e guarda o que recebeu."""

    def __init__(self, *textos):
        self.textos = list(textos)
        self.chamadas = []
        self.aio = SimpleNamespace(models=SimpleNamespace(generate_content=self._gerar))

    async def _gerar(self, model, contents, config):
        self.chamadas.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(text=self.textos.pop(0))


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setattr(resiliencia, "ESPERA_ENTRE_TENTATIVAS_S", 0)
    monkeypatch.setattr(settings, "gemini_model", "principal")
    monkeypatch.setattr(settings, "gemini_model_fallback", "reserva")


def usar(monkeypatch, falso):
    monkeypatch.setattr(mod, "get_client", lambda: falso)
    return falso


# ---------- texto ----------

async def test_responder_texto(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(texto_json("Estou com sede.")))
    r = await responder("Como você está?", LEITURA)
    assert r["texto"] == "Estou com sede."
    assert r["acao"] is None
    assert r["modelo"] == "principal"
    assert r["estado"]["problemas"] == ["solo_seco"]
    assert g.chamadas[0]["contents"] == "Como você está?"
    assert "umidade do solo: 20%" in g.chamadas[0]["config"].system_instruction


async def test_responder_texto_pede_json_com_acao(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(texto_json()))
    await responder("Oi?", LEITURA)
    config = g.chamadas[0]["config"]
    assert config.response_mime_type == "application/json"
    assert "PEDIDOS DE REGA" in config.system_instruction
    assert "pergunta_ouvida" not in config.system_instruction   # isso é só do áudio


async def test_responder_texto_devolve_o_pedido_de_rega(monkeypatch):
    pedido = {"tipo": "regar", "daqui_a_s": 60, "as_hora": None, "duracao_s": 5}
    usar(monkeypatch, GeminiFalso(texto_json("Claro!", pedido)))
    r = await responder("Rega daqui a 1 minuto por 5 segundos", LEITURA)
    assert r["acao"] == pedido


async def test_responder_texto_resposta_vazia_levanta_erro(monkeypatch):
    usar(monkeypatch, GeminiFalso(texto_json(""), texto_json("")))
    with pytest.raises(IAError):
        await responder("Oi?", LEITURA)


# ---------- áudio ----------

SAIDA = texto_json("Estou com sede.", ouviu="Como você está?")


async def test_responder_audio_manda_o_audio_e_pede_json(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(SAIDA))
    r = await responder_audio(b"RIFF....audio", "audio/wav", LEITURA)

    assert r["texto"] == "Estou com sede."
    assert r["pergunta_ouvida"] == "Como você está?"
    assert r["acao"] is None
    assert r["estado"]["problemas"] == ["solo_seco"]

    parte_audio = g.chamadas[0]["contents"][0]
    assert parte_audio.inline_data.data == b"RIFF....audio"
    assert parte_audio.inline_data.mime_type == "audio/wav"

    config = g.chamadas[0]["config"]
    assert config.response_mime_type == "application/json"
    assert "pergunta_ouvida" in config.system_instruction      # instruções de áudio entraram
    assert "PEDIDOS DE REGA" in config.system_instruction      # e as da rega também
    assert "umidade do solo: 20%" in config.system_instruction  # e os dados reais também


async def test_responder_audio_usa_o_prazo_de_audio(monkeypatch):
    prazos = []

    async def falso(contents, config, timeout_s):
        prazos.append(timeout_s)
        return SAIDA, "principal"

    monkeypatch.setattr(mod, "_gerar", falso)
    monkeypatch.setattr(settings, "gemini_timeout_audio_s", 12.0)
    await responder_audio(b"x", "audio/wav", LEITURA)
    assert prazos == [12.0]


async def test_responder_audio_dado_velho_entra_no_prompt(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(SAIDA))
    velha = {**LEITURA, "updated_at": datetime.now(timezone.utc) - timedelta(minutes=10)}
    r = await responder_audio(b"x", "audio/wav", velha)
    assert r["estado"]["dados"] == "desatualizados"
    assert "DESATUALIZADOS" in g.chamadas[0]["config"].system_instruction


async def test_responder_audio_resposta_vazia_levanta_erro(monkeypatch):
    usar(monkeypatch, GeminiFalso(texto_json("", ouviu="")))
    with pytest.raises(IAError):
        await responder_audio(b"x", "audio/wav", LEITURA)


async def test_responder_audio_devolve_o_pedido_de_rega(monkeypatch):
    pedido = {"tipo": "regar", "daqui_a_s": 60, "as_hora": None, "duracao_s": None}
    usar(monkeypatch, GeminiFalso(texto_json("Claro!", pedido, ouviu="Regue daqui a um minuto")))
    r = await responder_audio(b"x", "audio/wav", LEITURA)
    assert r["acao"] == pedido


async def test_responder_audio_sem_fala_descarta_o_pedido(monkeypatch):
    # Silêncio/ruído: mesmo que o modelo invente uma rega, sem transcrição não há pedido.
    pedido = {"tipo": "regar", "daqui_a_s": 0, "as_hora": None, "duracao_s": None}
    usar(monkeypatch, GeminiFalso(texto_json("Pode repetir?", pedido, ouviu="")))
    r = await responder_audio(b"x", "audio/wav", LEITURA)
    assert r["acao"] is None


# ---------- conversa recente (REQ-FUNC-008) ----------

HISTORICO = [{"pergunta": "Qual a temperatura?", "resposta": "Uns 24 graus."}]


async def test_historico_chega_ao_prompt_de_texto(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(texto_json()))
    await responder("E a umidade?", LEITURA, historico=HISTORICO)
    assert "Qual a temperatura?" in g.chamadas[0]["config"].system_instruction
    assert g.chamadas[0]["contents"] == "E a umidade?"      # a pergunta nova segue separada


async def test_historico_chega_ao_prompt_de_audio(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(SAIDA))
    await responder_audio(b"x", "audio/wav", LEITURA, historico=HISTORICO)
    assert "Uns 24 graus." in g.chamadas[0]["config"].system_instruction


async def test_sem_historico_o_prompt_nao_muda(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(texto_json()))
    await responder("Oi?", LEITURA)
    assert "CONVERSA RECENTE" not in g.chamadas[0]["config"].system_instruction


# ---------- leitura do JSON devolvido ----------

def test_ler_saida_json_normal():
    assert ler_saida(SAIDA) == ("Como você está?", "Estou com sede.", None)


def test_ler_saida_com_cerca_de_markdown():
    assert ler_saida(f"```json\n{SAIDA}\n```") == ("Como você está?", "Estou com sede.", None)


def test_ler_saida_texto_puro_vira_resposta_sem_acao():
    assert ler_saida("Estou com sede.") == ("", "Estou com sede.", None)


def test_ler_saida_json_que_nao_e_objeto():
    assert ler_saida('["a", "b"]') == ("", '["a", "b"]', None)


def test_ler_saida_silencio_pede_para_repetir():
    s = texto_json("Não entendi, pode repetir?", ouviu="")
    assert ler_saida(s) == ("", "Não entendi, pode repetir?", None)


def test_ler_saida_campos_nulos():
    assert ler_saida('{"pergunta_ouvida": null, "resposta": "Oi.", "acao": null}') == ("", "Oi.", None)


def test_ler_saida_sem_o_campo_acao():
    assert ler_saida('{"resposta": "Oi."}') == ("", "Oi.", None)


def test_ler_acao_regar_completa():
    s = texto_json("Ok", {"tipo": "regar", "daqui_a_s": 600, "as_hora": None, "duracao_s": 8})
    assert ler_saida(s)[2] == {"tipo": "regar", "daqui_a_s": 600, "as_hora": None, "duracao_s": 8}


def test_ler_acao_com_hora():
    s = texto_json("Ok", {"tipo": "regar", "daqui_a_s": None, "as_hora": " 15:30 ", "duracao_s": None})
    assert ler_saida(s)[2]["as_hora"] == "15:30"


def test_ler_acao_cancelar():
    s = texto_json("Ok", {"tipo": "cancelar", "daqui_a_s": None, "as_hora": None, "duracao_s": None})
    assert ler_saida(s)[2]["tipo"] == "cancelar"


@pytest.mark.parametrize("acao", [
    "regar",                                      # texto solto
    {"tipo": "ligar_bomba"},                      # tipo desconhecido
    {"tipo": "nenhuma", "daqui_a_s": 60},         # "nenhuma" nunca vira pedido
    {"daqui_a_s": 60},                            # sem tipo
    ["regar"],
])
def test_ler_acao_torta_ou_desconhecida_vira_none(acao):
    assert ler_saida(json.dumps({"resposta": "Oi.", "acao": acao}))[2] is None


@pytest.mark.parametrize("campo, valor", [
    ("daqui_a_s", "60"),      # texto no lugar de número
    ("daqui_a_s", True),      # bool não é número
    ("daqui_a_s", 1.5),       # decimal quebrado
    ("duracao_s", "cinco"),
])
def test_ler_acao_campo_invalido_vira_none_mas_mantem_o_pedido(campo, valor):
    acao = {"tipo": "regar", "daqui_a_s": 0, "as_hora": None, "duracao_s": None, campo: valor}
    lida = ler_saida(json.dumps({"resposta": "Oi.", "acao": acao}))[2]
    assert lida is not None and lida[campo] is None


def test_ler_acao_float_inteiro_vira_int():
    acao = {"tipo": "regar", "daqui_a_s": 60.0, "as_hora": None, "duracao_s": None}
    assert ler_saida(json.dumps({"resposta": "Oi.", "acao": acao}))[2]["daqui_a_s"] == 60