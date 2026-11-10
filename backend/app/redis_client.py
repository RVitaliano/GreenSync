"""Conexão única com o Redis (ADR-015).

Serve ao limite de perguntas (app/limite.py) e ao contexto curto da conversa
de cada dispositivo (app/contexto.py).
"""
import redis.asyncio as redis

from app.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis | None:
    """Devolve o cliente, criando na primeira vez. None se não houver REDIS_URL."""
    global _client
    if not settings.redis_url:
        return None
    if _client is None:
        _client = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            # Redis fora do ar não pode travar a pergunta: desiste em 1 segundo.
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


async def close_redis() -> None:
    """Fecha a conexão ao desligar o backend."""
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None