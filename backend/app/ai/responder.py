"""Única porta de entrada para o LLM (ADR-018).

Todo o resto do backend chama `responder(...)`. Se um dia trocarmos
Gemini por Groq, só o INTERIOR desta função muda.

Resiliência (o plano gratuito sofre picos e lentidão):
- erro 503: tenta de novo uma vez no mesmo modelo;
- timeout (lento demais): vai direto para o modelo reserva;
- erro 4xx (modelo errado, cota, chave): vai direto para o reserva.
"""
import asyncio
import logging

from google import genai
from google.genai import errors, types

from app.ai.estado import calcular_estado
from app.ai.prompt import montar_system_prompt
from app.config import settings

log = logging.getLogger(__name__)

_client: genai.Client | None = None

TENTATIVAS_POR_MODELO = 2   # 1 tentativa + 1 nova tentativa (só para 503)
ESPERA_ENTRE_TENTATIVAS_S = 0.5


class IAError(Exception):
    """Falha ao gerar resposta (chave ausente, API fora, resposta vazia)."""


def _get_client() -> genai.Client:
    """Cria o cliente uma vez só e reaproveita."""
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


async def responder(pergunta: str, leitura: dict | None) -> dict:
    """Responde `pergunta` como a planta, com base na `leitura` atual.

    Devolve {"texto": str, "estado": {...}, "modelo": str}.
    Levanta IAError se todos os modelos falharem.
    """
    estado = calcular_estado(leitura)
    system = montar_system_prompt(leitura, estado)
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.7,
        # Sem max_output_tokens de propósito: em modelos com "thinking",
        # um limite baixo pode consumir tudo no raciocínio e vir vazio.
    )
    client = _get_client()  # levanta IAError se faltar a chave
    ultimo_erro = "desconhecido"

    for modelo in _modelos():
        for tentativa in range(1, TENTATIVAS_POR_MODELO + 1):
            try:
                resp = await asyncio.wait_for(
                    client.aio.models.generate_content(
                        model=modelo, contents=pergunta, config=config
                    ),
                    timeout=settings.gemini_timeout_s,
                )
            except asyncio.TimeoutError:
                # Lento demais: repetir no mesmo modelo só atrasaria mais.
                ultimo_erro = f"{modelo}: timeout de {settings.gemini_timeout_s}s"
                log.warning("Gemini %s estourou o tempo (%ss)",
                            modelo, settings.gemini_timeout_s)
                break
            except errors.ServerError as e:
                # 5xx (ex.: 503 "high demand"): temporário, vale tentar de novo.
                ultimo_erro = f"{modelo}: {e}"
                log.warning("Gemini %s indisponível (tentativa %d): %s",
                            modelo, tentativa, e.code)
                if tentativa < TENTATIVAS_POR_MODELO:
                    await asyncio.sleep(ESPERA_ENTRE_TENTATIVAS_S)
                continue
            except errors.ClientError as e:
                # 4xx (404 modelo errado, 429 cota, 401/403 chave): repetir
                # não adianta; passa direto para o próximo modelo.
                ultimo_erro = f"{modelo}: {e}"
                log.error("Gemini %s recusou a chamada: %s", modelo, e.code)
                break
            except Exception as e:
                ultimo_erro = f"{modelo}: {e}"
                log.error("Erro inesperado no Gemini %s: %s", modelo, e)
                break

            texto = (resp.text or "").strip()
            if texto:
                if modelo != settings.gemini_model:
                    log.warning("Resposta veio do modelo reserva: %s", modelo)
                return {"texto": texto, "estado": estado, "modelo": modelo}

            ultimo_erro = f"{modelo}: resposta vazia"
            log.warning("Gemini %s devolveu resposta vazia", modelo)
            break

    raise IAError(f"nenhum modelo respondeu ({ultimo_erro})")