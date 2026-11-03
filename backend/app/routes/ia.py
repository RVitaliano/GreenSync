"""Rota de texto do assistente (ADR-018, camada 1: testável sem hardware)."""
import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from app.ai.responder import IAError, responder
from app.ai.tela import decidir_tela
from app.config import settings
from app.firebase_client import ler_leitura_atual
from app.limite import verificar_limite

log = logging.getLogger("greensync.ia")
router = APIRouter()


class PerguntaIn(BaseModel):
    # O device_id vira nome de documento no Firestore, então só aceitamos
    # letras, números, "-" e "_" (sem "/", que abriria outros caminhos).
    device_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    pergunta: str = Field(min_length=1, max_length=500)


def _chave_valida(recebida: str) -> bool:
    """Compara a X-API-Key em tempo constante. Vazia no .env = rota aberta (dev)."""
    if not settings.api_key:
        return True
    # .encode() porque compare_digest com str não aceita acento.
    return secrets.compare_digest(recebida.encode(), settings.api_key.encode())


@router.post("/perguntar")
async def perguntar(body: PerguntaIn, x_api_key: str = Header(default="")):
    if not _chave_valida(x_api_key):
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

    return {
        "texto": r["texto"],
        "estado": r["estado"],
        "tela": decidir_tela(body.pergunta),
        "modelo": r["modelo"],
    }