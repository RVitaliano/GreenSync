"""Testa responder() e responder_audio() com um Gemini falso."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from app.ai import resiliencia, responder as mod
from app.ai.resiliencia import IAError
from app.ai.responder import ler_saida_audio, responder, responder_audio
from app.config import settings

pytestmark = pytest.mark.anyio

LEITURA = {"umidade_solo": 20, "temperatura_ar": 24.1, "bomba_ligada": False}


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
    g = usar(monkeypatch, GeminiFalso("Estou com sede."))
    r = await responder("Como você está?", LEITURA)
    assert r["texto"] == "Estou com sede."
    assert r["modelo"] == "principal"
    assert r["estado"]["problemas"] == ["solo_seco"]
    assert g.chamadas[0]["contents"] == "Como você está?"
    assert "umidade do solo: 20%" in g.chamadas[0]["config"].system_instruction


async def test_responder_texto_nao_pede_json(monkeypatch):
    g = usar(monkeypatch, GeminiFalso("Oi."))
    await responder("Oi?", LEITURA)
    assert g.chamadas[0]["config"].response_mime_type is None
    assert "pergunta_ouvida" not in g.chamadas[0]["config"].system_instruction


# ---------- áudio ----------

SAIDA = json.dumps({"pergunta_ouvida": "Como você está?", "resposta": "Estou com sede."})


async def test_responder_audio_manda_o_audio_e_pede_json(monkeypatch):
    g = usar(monkeypatch, GeminiFalso(SAIDA))
    r = await responder_audio(b"RIFF....audio", "audio/wav", LEITURA)

    assert r["texto"] == "Estou com sede."
    assert r["pergunta_ouvida"] == "Como você está?"
    assert r["estado"]["problemas"] == ["solo_seco"]

    parte_audio = g.chamadas[0]["contents"][0]
    assert parte_audio.inline_data.data == b"RIFF....audio"
    assert parte_audio.inline_data.mime_type == "audio/wav"

    config = g.chamadas[0]["config"]
    assert config.response_mime_type == "application/json"
    assert "pergunta_ouvida" in config.system_instruction      # instruções de áudio entraram
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
    vazio = json.dumps({"pergunta_ouvida": "", "resposta": ""})
    usar(monkeypatch, GeminiFalso(vazio))
    with pytest.raises(IAError):
        await responder_audio(b"x", "audio/wav", LEITURA)


# ---------- leitura do JSON devolvido ----------

def test_ler_saida_json_normal():
    assert ler_saida_audio(SAIDA) == ("Como você está?", "Estou com sede.")


def test_ler_saida_com_cerca_de_markdown():
    assert ler_saida_audio(f"```json\n{SAIDA}\n```") == ("Como você está?", "Estou com sede.")


def test_ler_saida_texto_puro_vira_resposta():
    assert ler_saida_audio("Estou com sede.") == ("", "Estou com sede.")


def test_ler_saida_json_que_nao_e_objeto():
    assert ler_saida_audio('["a", "b"]') == ("", '["a", "b"]')


def test_ler_saida_silencio_pede_para_repetir():
    s = json.dumps({"pergunta_ouvida": "", "resposta": "Não entendi, pode repetir?"})
    assert ler_saida_audio(s) == ("", "Não entendi, pode repetir?")


def test_ler_saida_campos_nulos():
    assert ler_saida_audio('{"pergunta_ouvida": null, "resposta": "Oi."}') == ("", "Oi.")