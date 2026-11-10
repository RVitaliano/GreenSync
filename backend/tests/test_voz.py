"""Testa a voz (TTS) com um cliente falso: nada de internet nem de cota."""
import base64
from types import SimpleNamespace

import pytest
from google.genai import errors

from app.ai import resiliencia, voz
from app.ai.audio import info_wav, wav_de_pcm
from app.ai.resiliencia import IAError
from app.config import settings

pytestmark = pytest.mark.anyio

PCM = b"\x01\x00" * 24000            # 1 s a 24 kHz
WAV_24K = wav_de_pcm(PCM, sample_rate=24000)


def interacao(dados: bytes, sample_rate=24000, mime="audio/wav"):
    b64 = base64.b64encode(dados).decode()
    return SimpleNamespace(output_audio=SimpleNamespace(data=b64, sample_rate=sample_rate, mime_type=mime))


class ClienteFalso:
    """Imita client.aio.interactions.create, seguindo um roteiro por chamada."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []
        self.aio = SimpleNamespace(interactions=SimpleNamespace(create=self._create))

    async def _create(self, **kwargs):
        self.chamadas.append(kwargs)
        item = self.respostas.pop(0)
        if isinstance(item, BaseException):
            raise item
        return item


@pytest.fixture(autouse=True)
def ambiente(monkeypatch):
    monkeypatch.setattr(resiliencia, "ESPERA_ENTRE_TENTATIVAS_S", 0)
    monkeypatch.setattr(settings, "tts_model", "tts-principal")
    monkeypatch.setattr(settings, "tts_model_fallback", "tts-reserva")
    monkeypatch.setattr(settings, "tts_voice", "Kore")
    monkeypatch.setattr(settings, "tts_estilo", "")
    monkeypatch.setattr(settings, "tts_sample_rate", 0)


def usar(monkeypatch, cliente):
    monkeypatch.setattr(voz, "get_client", lambda: cliente)
    return cliente


async def test_devolve_wav_pronto(monkeypatch):
    c = usar(monkeypatch, ClienteFalso(interacao(WAV_24K)))
    wav, modelo = await voz.sintetizar("Estou com sede.")
    assert modelo == "tts-principal"
    assert wav == WAV_24K
    assert info_wav(wav)[0] == 24000


async def test_monta_a_chamada_como_a_documentacao(monkeypatch):
    c = usar(monkeypatch, ClienteFalso(interacao(WAV_24K)))
    await voz.sintetizar("Oi!")
    pedido = c.chamadas[0]
    assert pedido["model"] == "tts-principal"
    assert pedido["input"] == [
        {"type": "user_input", "content": [{"type": "text", "text": "Oi!"}]}
    ]
    assert pedido["response_format"] == {"type": "audio"}
    assert pedido["generation_config"] == {"speech_config": [{"voice": "Kore"}]}


async def test_estilo_e_taxa_so_entram_se_configurados(monkeypatch):
    monkeypatch.setattr(settings, "tts_estilo", "carinhosa")
    monkeypatch.setattr(settings, "tts_sample_rate", 16000)
    c = usar(monkeypatch, ClienteFalso(interacao(WAV_24K)))
    await voz.sintetizar("Oi!")
    pedido = c.chamadas[0]
    assert pedido["input"][0]["content"][0]["annotations"] == [
        {"type": "speech_metadata", "style": "carinhosa"}
    ]
    assert pedido["response_format"] == {"type": "audio", "sample_rate": 16000}


async def test_pcm_cru_ganha_cabecalho_wav(monkeypatch):
    usar(monkeypatch, ClienteFalso(interacao(PCM, sample_rate=24000, mime="audio/l16")))
    wav, _ = await voz.sintetizar("Oi!")
    assert wav[:4] == b"RIFF"
    taxa, canais, duracao = info_wav(wav)
    assert (taxa, canais) == (24000, 1)
    assert duracao == pytest.approx(1.0)


async def test_503_repete_e_depois_usa_o_reserva(monkeypatch):
    erro = errors.ServerError(503, {"error": {"message": "x"}})
    c = usar(monkeypatch, ClienteFalso(erro, erro, interacao(WAV_24K)))
    _, modelo = await voz.sintetizar("Oi!")
    assert modelo == "tts-reserva"
    assert [p["model"] for p in c.chamadas] == ["tts-principal", "tts-principal", "tts-reserva"]


async def test_resposta_sem_audio_conta_como_falha(monkeypatch):
    vazia = SimpleNamespace(output_audio=None)
    usar(monkeypatch, ClienteFalso(vazia, vazia))
    with pytest.raises(IAError):
        await voz.sintetizar("Oi!")


async def test_texto_vazio_nem_chama_a_api(monkeypatch):
    c = usar(monkeypatch, ClienteFalso())
    with pytest.raises(IAError):
        await voz.sintetizar("   ")
    assert c.chamadas == []