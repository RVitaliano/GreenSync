"""Une tudo: pega o pedido que o LLM entendeu, valida e agenda (ou cancela).

O LLM nunca aciona a bomba (ADR-021). Ele devolve um pedido estruturado; aqui o
backend confere os limites e só então grava o agendamento, que o Agendador
executa. Qualquer problema vira uma frase falada, nunca uma exceção: a resposta
de voz sempre sai.
"""
import logging

from app.agenda import fala
from app.agenda.agendador import Agendador
from app.agenda.regras import (Recusa, checar_regras, pessoa_pediu_cancelar,
                                 pessoa_pediu_rega, resolver_pedido)
from app.agenda import repositorio
from app.config import settings
from app.firebase_client import ler_leitura_atual
from app.mqtt_client import publicar_comando

log = logging.getLogger("greensync.agenda")

# Instância única do processo (o backend roda em uma instância só, ADR-015/019).
agendador = Agendador(repo=repositorio, publicar=publicar_comando, ler_leitura=ler_leitura_atual)


async def tratar_acao(acao: dict | None, fala_usuario: str, device_id: str,
                      leitura: dict | None, estado: dict, origem: str) -> dict | None:
    """Devolve {"fala", "resultado", "id"} ou None se a pessoa não pediu nada.

    `fala_usuario` é o que a pessoa disse/escreveu (transcrição no caso de áudio);
    serve só para a trava "a pessoa realmente pediu rega" e não é registrada em log.
    """
    tipo = (acao or {}).get("tipo")
    if tipo not in ("regar", "cancelar"):
        return None

    try:
        if tipo == "cancelar":
            return await _cancelar(fala_usuario, device_id)
        return await _regar(acao, fala_usuario, device_id, leitura, estado, origem)
    except Exception:
        log.exception("[%s] erro ao tratar pedido de rega", device_id)
        return {"fala": fala.ERRO, "resultado": "erro", "id": None}


async def _regar(acao, fala_usuario, device_id, leitura, estado, origem) -> dict:
    # Trava independente do LLM: sem palavra de rega na fala da pessoa, não aciona nada.
    if not pessoa_pediu_rega(fala_usuario):
        log.warning("[%s] o modelo propôs uma rega que a pessoa não pediu: ignorada", device_id)
        return {"fala": fala.NAO_ENTENDI, "resultado": "ignorada", "id": None}

    resposta, _ = await _agendar_rega(acao, device_id, leitura, estado, origem)
    return resposta


async def regar_agora(device_id: str, duracao_s: int | None, leitura: dict | None,
                      estado: dict, origem: str = "app") -> dict:
    """Rega manual (botão do app): mesmas regras e travas da rega por voz, sem a trava de palavra.

    Devolve {"resultado": "agendada" | "recusada" | "falhou", "id", "motivo"}. `motivo` é o
    código da recusa, o texto da falha ou None. Erros inesperados (Firestore, MQTT) sobem
    para quem chamou decidir o que responder.
    """
    acao = {"daqui_a_s": None, "as_hora": None, "duracao_s": duracao_s}
    resposta, motivo_falha = await _agendar_rega(acao, device_id, leitura, estado, origem)
    resultado = resposta["resultado"]
    if resultado == "recusada":
        motivo = resposta.get("motivo")
    elif resultado == "falhou":
        motivo = motivo_falha or "erro interno"
    else:
        motivo = None
    return {"resultado": resultado, "id": resposta["id"], "motivo": motivo}


async def _agendar_rega(acao, device_id, leitura, estado, origem) -> tuple[dict, str | None]:
    """Valida, agenda e (se for "agora") espera o resultado. Devolve (resposta, motivo_da_falha).

    `resposta` tem o formato público de tratar_acao; o motivo da falha (segundo valor) só é
    preenchido quando a rega de agora falhou na hora de executar.
    """
    async with agendador.trava:
        try:
            pedido = resolver_pedido(acao, agendador.agora())
            vizinhos = await agendador.repo.vizinhos(device_id, pedido.quando, settings.rega_intervalo_min_s)
            checar_regras(pedido, leitura, estado, vizinhos)
        except Recusa as r:
            log.info("[%s] rega recusada: %s", device_id, r.codigo)
            return {"fala": r.fala, "resultado": "recusada", "motivo": r.codigo, "id": None}, None
        ag_id = await agendador.agendar(device_id, pedido, origem)

    texto = fala.confirmacao(pedido.quando, pedido.atraso_s, pedido.duracao_s)
    resultado = "agendada"
    motivo_falha = None
    if pedido.atraso_s == 0:
        # Rega "de agora": espera o resultado real para não prometer o que não aconteceu.
        final = await agendador.aguardar(device_id, ag_id)
        if final and final[0] == "falhou":
            motivo_falha = final[1] or "erro interno"
            texto, resultado = fala.falha_na_hora(motivo_falha), "falhou"
    return {"fala": texto, "resultado": resultado, "id": ag_id}, motivo_falha


async def _cancelar(fala_usuario: str, device_id: str) -> dict:
    # Mesma trava da rega: sem palavra de cancelamento na fala da pessoa, não cancela nada.
    if not pessoa_pediu_cancelar(fala_usuario):
        log.warning("[%s] o modelo propôs um cancelamento que a pessoa não pediu: ignorado", device_id)
        return {"fala": fala.NAO_ENTENDI_CANCELAR, "resultado": "ignorada", "id": None}
    achou = await agendador.cancelar_proxima(device_id)
    if achou is None:
        return {"fala": fala.NADA_A_CANCELAR, "resultado": "nada_a_cancelar", "id": None}
    alvo, restantes = achou
    return {"fala": fala.cancelamento(alvo["quando"], restantes), "resultado": "cancelada", "id": alvo["id"]}