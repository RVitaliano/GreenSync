"""Rotas por dispositivo, usadas pelo app. Por enquanto: rega manual ("Regar agora")."""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Path
from pydantic import BaseModel, Field, StrictInt

from app.agenda.servico import regar_agora
from app.ai.estado import avaliar_estado
from app.firebase_client import ler_leitura_segura
from app.seguranca import DEVICE_ID_PADRAO, chave_valida

log = logging.getLogger("greensync.dispositivos")
router = APIRouter()


class RegaIn(BaseModel):
    # Sem o campo, vale REGA_DURACAO_PADRAO_S. Acima do máximo NÃO é 422: a regra da rega recusa.
    duracao_s: Optional[StrictInt] = Field(default=None, ge=1)


@router.post("/dispositivos/{device_id}/regar")
async def regar(
    body: Optional[RegaIn] = None,
    device_id: str = Path(pattern=DEVICE_ID_PADRAO),
    x_api_key: str = Header(default=""),
):
    if not chave_valida(x_api_key):
        raise HTTPException(status_code=401, detail="X-API-Key inválida")

    # Sem Gemini, Redis nem limite de perguntas: o intervalo mínimo e a trava do
    # agendador já protegem a bomba.
    try:
        leitura = await ler_leitura_segura(device_id)
        estado = avaliar_estado(leitura)
        return await regar_agora(device_id, body.duracao_s if body else None, leitura, estado, origem="app")
    except Exception:
        log.exception("[%s] erro ao processar a rega manual", device_id)
        raise HTTPException(status_code=502, detail="não foi possível processar a rega agora")
