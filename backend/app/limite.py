"""Limite de perguntas por chave de API (REQ-FUNC-015, SRS 3.6.3).

Contador por janela fixa no Redis: cada chave de API tem um contador por
janela de tempo (ex.: 10 perguntas por minuto). Passou do limite, a rota
responde 429. Protege a cota do Gemini.

Se o Redis não estiver configurado ou cair, a pergunta passa (e o erro é
logado): preferimos o assistente no ar a derrubá-lo por causa do contador.
"""
import hashlib
import logging
import math
import time

from redis.exceptions import RedisError

from app import redis_client
from app.config import settings

log = logging.getLogger("greensync.limite")


def _agora() -> float:
    """Isolado numa função para os testes poderem controlar o relógio."""
    return time.time()


def _chave_redis(x_api_key: str, janela: int) -> str:
    # Só o hash vai para o Redis: a chave de API nunca fica guardada em texto.
    h = hashlib.sha256(x_api_key.encode()).hexdigest()[:16]
    return f"rl:{h}:{janela}"


async def verificar_limite(x_api_key: str) -> int | None:
    """Conta uma pergunta para esta chave.

    Devolve None se pode seguir, ou os segundos até a próxima janela se o
    limite estourou (vira o cabeçalho Retry-After).
    """
    r = redis_client.get_redis()
    if r is None:
        return None

    agora = _agora()
    janela_s = settings.janela_limite_s
    janela = int(agora // janela_s)
    chave = _chave_redis(x_api_key, janela)

    try:
        # MULTI/EXEC: o contador e a expiração andam juntos, então nunca
        # sobra uma chave sem prazo de validade.
        async with r.pipeline(transaction=True) as pipe:
            pipe.incr(chave)
            pipe.expire(chave, janela_s * 2)
            contagem, _ = await pipe.execute()
    except (RedisError, OSError) as e:
        log.error("Redis indisponível, limite ignorado nesta pergunta: %s", e)
        return None

    if contagem > settings.limite_perguntas:
        return max(1, math.ceil((janela + 1) * janela_s - agora))
    return None