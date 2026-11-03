"""Única porta de entrada para o LLM (ADR-018).

Todo o resto do backend chama `responder(...)` (texto) ou `responder_audio(...)`
(pergunta falada). Se um dia trocarmos Gemini por Groq, só o INTERIOR destas
funções muda. Retry, timeout e modelo reserva ficam em `resiliencia.py`.
"""
import json
import logging

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.ai.estado import avaliar_estado
from app.ai.prompt import montar_system_prompt
from app.ai.resiliencia import IAError, tentar_modelos  # IAError é re-exportado daqui
from app.config import settings

log = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Cria o cliente uma vez só e reaproveita (também usado por voz.py)."""
    global _client
    if not settings.gemini_api_key:
        raise IAError("GEMINI_API_KEY não configurada no .env")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _modelos() -> list[str]:
    """Principal primeiro, reserva depois (sem repetir)."""
    modelos = [settings.gemini_model]
    reserva = settings.gemini_model_fallback
    if reserva and reserva != settings.gemini_model:
        modelos.append(reserva)
    return modelos


async def _gerar(contents, config, timeout_s: float) -> tuple[str, str]:
    """Chama o Gemini (com retry/reserva) e devolve (texto, modelo)."""
    client = get_client()  # levanta IAError se faltar a chave

    def chamar(modelo: str):
        return client.aio.models.generate_content(
            model=modelo, contents=contents, config=config
        )

    def extrair(resp) -> str:
        return (resp.text or "").strip()

    return await tentar_modelos(_modelos(), chamar, extrair, timeout_s, "Gemini")


async def responder(pergunta: str, leitura: dict | None) -> dict:
    """Responde `pergunta` (texto) como a planta, com base na `leitura` atual.

    Devolve {"texto": str, "estado": {...}, "modelo": str}.
    Levanta IAError se todos os modelos falharem.
    """
    # Estado da planta + se o dado ainda vale como "agora" (vaso offline / leitura velha).
    estado = avaliar_estado(leitura)
    config = types.GenerateContentConfig(
        system_instruction=montar_system_prompt(leitura, estado),
        temperature=0.7,
        # Sem max_output_tokens de propósito: em modelos com "thinking",
        # um limite baixo pode consumir tudo no raciocínio e vir vazio.
    )
    texto, modelo = await _gerar(pergunta, config, settings.gemini_timeout_s)
    return {"texto": texto, "estado": estado, "modelo": modelo}


# ---------------------------------------------------------------- áudio ----

class SaidaAudio(BaseModel):
    """Formato que pedimos ao Gemini quando a pergunta chega em áudio."""
    pergunta_ouvida: str
    resposta: str


def ler_saida_audio(bruto: str) -> tuple[str, str]:
    """Extrai (pergunta_ouvida, resposta) do JSON devolvido pelo Gemini.

    Tolera cerca de markdown (```json) e, se o modelo ignorar o JSON e devolver
    só texto, usa esse texto como resposta (sem pergunta ouvida).
    """
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    try:
        dados = json.loads(texto)
    except ValueError:
        return "", bruto.strip()
    if not isinstance(dados, dict):
        return "", bruto.strip()
    pergunta = str(dados.get("pergunta_ouvida") or "").strip()
    resposta = str(dados.get("resposta") or "").strip()
    return pergunta, resposta


async def responder_audio(audio: bytes, mime: str, leitura: dict | None) -> dict:
    """Entende uma pergunta FALADA e responde como a planta (ADR-018, camada 2).

    O Gemini ouve o áudio direto (sem STT separado) e devolve dois campos:
    o que ouviu (usado para decidir a tela e para o log) e a resposta.

    Devolve {"texto", "pergunta_ouvida", "estado", "modelo"}.
    Levanta IAError se todos os modelos falharem ou se a resposta vier vazia.
    """
    estado = avaliar_estado(leitura)
    config = types.GenerateContentConfig(
        system_instruction=montar_system_prompt(leitura, estado, audio=True),
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=SaidaAudio,
    )
    contents = [
        types.Part.from_bytes(data=audio, mime_type=mime),
        "Responda à pergunta falada neste áudio.",
    ]
    bruto, modelo = await _gerar(contents, config, settings.gemini_timeout_audio_s)

    pergunta, texto = ler_saida_audio(bruto)
    if not texto:
        raise IAError(f"{modelo}: resposta vazia")
    return {"texto": texto, "pergunta_ouvida": pergunta, "estado": estado, "modelo": modelo}