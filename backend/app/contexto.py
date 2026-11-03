"""Contexto curto da conversa por dispositivo, guardado no Redis (REQ-FUNC-008, ADR-015).

Serve para a planta entender "e a umidade?" depois de uma pergunta sobre a
temperatura. Guardamos só as últimas trocas (pergunta + resposta, em texto),
com prazo de validade: depois de alguns minutos sem conversa, tudo é esquecido.

- Nunca guarda áudio e nunca escreve o conteúdo no log (é a fala da pessoa).
- Se o Redis não estiver configurado ou cair, a conversa segue sem contexto
  (e o erro é logado), igual ao limite de perguntas: o assistente não cai por isso.
"""
import json
import logging

from redis.exceptions import RedisError

from app import redis_client
from app.config import settings

log = logging.getLogger("greensync.contexto")


def _chave(device_id: str) -> str:
    # device_id já foi validado nas rotas (só letras, números, "-" e "_").
    return f"ctx:{device_id}"


def _cortar(texto: str, limite: int) -> str:
    """Tira quebras de linha/espaços repetidos e corta no limite, com reticências."""
    texto = " ".join((texto or "").split())
    if len(texto) <= limite:
        return texto
    return texto[: max(limite - 1, 0)].rstrip() + "…"


async def ler_contexto(device_id: str) -> list[dict]:
    """Últimas trocas do dispositivo, da mais antiga para a mais nova.

    Cada item é {"pergunta": str, "resposta": str}. Lista vazia se não houver
    contexto, se o recurso estiver desligado ou se o Redis falhar.
    """
    if settings.contexto_turnos <= 0:
        return []
    r = redis_client.get_redis()
    if r is None:
        return []
    try:
        brutos = await r.lrange(_chave(device_id), 0, -1)
    except (RedisError, OSError) as e:
        log.error("Redis indisponível, conversa segue sem contexto: %s", e)
        return []

    turnos = []
    for bruto in brutos:
        try:
            t = json.loads(bruto)
        except ValueError:
            continue    # lixo no Redis nunca derruba a pergunta
        if isinstance(t, dict) and isinstance(t.get("pergunta"), str) and isinstance(t.get("resposta"), str):
            turnos.append({"pergunta": t["pergunta"], "resposta": t["resposta"]})
    return turnos[-settings.contexto_turnos:]


async def salvar_turno(device_id: str, pergunta: str, resposta: str) -> None:
    """Guarda mais uma troca, mantém só as últimas `contexto_turnos` e renova o prazo."""
    if settings.contexto_turnos <= 0:
        return
    pergunta = _cortar(pergunta, settings.contexto_max_chars)
    resposta = _cortar(resposta, settings.contexto_max_chars)
    if not pergunta or not resposta:     # ex.: silêncio, sem transcrição: nada a lembrar
        return
    r = redis_client.get_redis()
    if r is None:
        return

    chave = _chave(device_id)
    turno = json.dumps({"pergunta": pergunta, "resposta": resposta}, ensure_ascii=False)
    try:
        # MULTI/EXEC: adicionar, aparar e renovar o prazo andam juntos.
        async with r.pipeline(transaction=True) as pipe:
            pipe.rpush(chave, turno)
            pipe.ltrim(chave, -settings.contexto_turnos, -1)
            pipe.expire(chave, settings.contexto_ttl_s)
            await pipe.execute()
    except (RedisError, OSError) as e:
        log.error("Redis indisponível, troca não guardada no contexto: %s", e)