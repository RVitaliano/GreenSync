"""Retry, timeout e modelo reserva para qualquer chamada ao Gemini.

Usado pelo texto/áudio (responder.py) e pela voz (voz.py), para o
comportamento ser o mesmo nos dois (o plano gratuito sofre picos e lentidão):
- erro 5xx (ex.: 503): tenta de novo uma vez no mesmo modelo;
- timeout (lento demais): vai direto para o modelo reserva;
- erro 4xx (modelo errado, cota, chave): vai direto para o reserva;
- resposta vazia: vai para o reserva.
"""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from google.genai import errors

log = logging.getLogger("greensync.ia")

TENTATIVAS_POR_MODELO = 2   # 1 tentativa + 1 nova tentativa (só para 5xx)
ESPERA_ENTRE_TENTATIVAS_S = 0.5


class IAError(Exception):
    """Falha ao gerar resposta (chave ausente, API fora, resposta vazia)."""


async def tentar_modelos(
    modelos: list[str],
    chamar: Callable[[str], Awaitable[Any]],
    extrair: Callable[[Any], Any],
    timeout_s: float,
    rotulo: str = "Gemini",
) -> tuple[Any, str]:
    """Tenta cada modelo, na ordem, até um responder.

    - `chamar(modelo)`: devolve a chamada à API para aquele modelo;
    - `extrair(resposta)`: tira o que interessa da resposta (texto, bytes de
      áudio...). Se devolver algo "vazio" (None, "", b""), conta como falha.

    Devolve (valor, modelo_que_respondeu). Levanta IAError se todos falharem.
    """
    ultimo_erro = "desconhecido"

    for posicao, modelo in enumerate(modelos):
        for tentativa in range(1, TENTATIVAS_POR_MODELO + 1):
            try:
                resp = await asyncio.wait_for(chamar(modelo), timeout=timeout_s)
            except asyncio.TimeoutError:
                # Lento demais: repetir no mesmo modelo só atrasaria mais.
                ultimo_erro = f"{modelo}: timeout de {timeout_s}s"
                log.warning("%s %s estourou o tempo (%ss)", rotulo, modelo, timeout_s)
                break
            except errors.ServerError as e:
                # 5xx (ex.: 503 "high demand"): temporário, vale tentar de novo.
                ultimo_erro = f"{modelo}: {e}"
                log.warning("%s %s indisponível (tentativa %d): %s",
                            rotulo, modelo, tentativa, e.code)
                if tentativa < TENTATIVAS_POR_MODELO:
                    await asyncio.sleep(ESPERA_ENTRE_TENTATIVAS_S)
                continue
            except errors.ClientError as e:
                # 4xx (404 modelo errado, 429 cota, 401/403 chave): repetir
                # não adianta; passa direto para o próximo modelo.
                ultimo_erro = f"{modelo}: {e}"
                log.error("%s %s recusou a chamada: %s", rotulo, modelo, e.code)
                break
            except Exception as e:
                ultimo_erro = f"{modelo}: {e}"
                log.error("Erro inesperado no %s %s: %s", rotulo, modelo, e)
                break

            valor = extrair(resp)
            if valor:
                if posicao > 0:
                    log.warning("Resposta veio do modelo reserva: %s", modelo)
                return valor, modelo

            ultimo_erro = f"{modelo}: resposta vazia"
            log.warning("%s %s devolveu resposta vazia", rotulo, modelo)
            break

    raise IAError(f"nenhum modelo respondeu ({ultimo_erro})")