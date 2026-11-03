"""Voz da planta: transforma o texto da resposta em áudio (TTS do Gemini).

Usa a API "Interactions" (a documentada hoje para os modelos de TTS 3.8).
Devolve sempre um WAV pronto para o alto-falante do S3.
"""
import base64
import logging
import warnings

from app.ai.audio import wav_de_pcm
from app.ai.resiliencia import IAError, tentar_modelos
from app.ai.responder import get_client
from app.config import settings

log = logging.getLogger("greensync.voz")

# A API Interactions avisa que é "experimental" a cada uso; o aviso só polui o log.
warnings.filterwarnings("ignore", message="Interactions usage is experimental")

SAMPLE_RATE_PADRAO = 24000  # taxa que o modelo usa quando não pedimos outra


def _modelos() -> list[str]:
    modelos = [settings.tts_model]
    reserva = settings.tts_model_fallback
    if reserva and reserva != settings.tts_model:
        modelos.append(reserva)
    return modelos


def _montar_entrada(texto: str) -> list[dict]:
    """Texto a ser falado (literal) + estilo opcional de entrega."""
    conteudo: dict = {"type": "text", "text": texto}
    if settings.tts_estilo:
        conteudo["annotations"] = [
            {"type": "speech_metadata", "style": settings.tts_estilo}
        ]
    return [{"type": "user_input", "content": [conteudo]}]


def _formato_resposta() -> dict:
    formato: dict = {"type": "audio"}
    if settings.tts_sample_rate:
        formato["sample_rate"] = settings.tts_sample_rate
    return formato


def _extrair_wav(interacao) -> bytes:
    """Tira o áudio da resposta e garante que é um WAV completo."""
    audio = getattr(interacao, "output_audio", None)
    if audio is None or not getattr(audio, "data", None):
        return b""
    bruto = base64.b64decode(audio.data)
    if bruto[:4] == b"RIFF":      # já veio com cabeçalho WAV
        return bruto
    # PCM cru (16 bits, mono): coloca o cabeçalho.
    taxa = getattr(audio, "sample_rate", None) or settings.tts_sample_rate or SAMPLE_RATE_PADRAO
    return wav_de_pcm(bruto, sample_rate=taxa)


async def sintetizar(texto: str) -> tuple[bytes, str]:
    """Texto -> (WAV, modelo_usado). Levanta IAError se nenhum modelo funcionar."""
    texto = texto.strip()
    if not texto:
        raise IAError("texto vazio para sintetizar")

    client = get_client()  # levanta IAError se faltar a chave
    entrada = _montar_entrada(texto)
    formato = _formato_resposta()
    config = {"speech_config": [{"voice": settings.tts_voice}]}

    def chamar(modelo: str):
        return client.aio.interactions.create(
            model=modelo,
            input=entrada,
            response_format=formato,
            generation_config=config,
        )

    return await tentar_modelos(_modelos(), chamar, _extrair_wav, settings.tts_timeout_s, "TTS")