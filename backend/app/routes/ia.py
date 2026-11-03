"""Rota de texto do assistente (ADR-018, camada 1: testável sem hardware)."""
import logging

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.agenda.servico import tratar_acao
from app.ai.responder import IAError, responder
from app.ai.tela import decidir_tela
from app.firebase_client import ler_leitura_atual
from app.limite import verificar_limite
from app.seguranca import DEVICE_ID_PADRAO, chave_valida

log = logging.getLogger("greensync.ia")
router = APIRouter()


class PerguntaIn(BaseModel):
    device_id: str = Field(pattern=DEVICE_ID_PADRAO)
    pergunta: str = Field(min_length=1, max_length=500)


@router.post("/perguntar")
async def perguntar(body: PerguntaIn, x_api_key: str = Header(default="")):
    if not chave_valida(x_api_key):
        raise HTTPException(status_code=401, detail="X-API-Key inválida")

    # Só chega aqui quem tem chave válida, então chave errada não gasta o limite.
    espera = await verificar_limite(x_api_key)
    if espera is not None:
        raise HTTPException(
            status_code=429,
            detail="limite de perguntas atingido, tente de novo em instantes",
            headers={"Retry-After": str(espera)},
        )

    leitura = await ler_leitura_atual(body.device_id)

    try:
        r = await responder(body.pergunta, leitura)
    except IAError as e:
        log.error("IA falhou: %s", e)
        raise HTTPException(status_code=502, detail="assistente indisponível")

    # Pedido de rega/cancelamento: o backend valida e responde com a frase oficial.
    rega = await tratar_acao(r.get("acao"), body.pergunta, body.device_id, leitura, r["estado"], "texto")

    return {
        "texto": rega["fala"] if rega else r["texto"],
        "estado": r["estado"],
        "tela": decidir_tela(body.pergunta),
        "modelo": r["modelo"],
        # None = não houve pedido de rega. Senão: resultado (agendada, recusada, cancelada...) e id.
        "rega": {"resultado": rega["resultado"], "id": rega["id"]} if rega else None,
    }