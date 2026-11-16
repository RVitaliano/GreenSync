"""Administração do firmware (OTA): registra qual versão cada placa deve rodar.

Só registra; nenhum comando é enviado ao vaso por aqui. Protegida por X-Admin-Key
(ADMIN_API_KEY), que é DIFERENTE da API_KEY do app: a chave do app não abre esta rota.
"""
import logging
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.config import settings
from app.ota import repositorio, validacao
from app.seguranca import admin_chave_valida

log = logging.getLogger("greensync.firmware")
router = APIRouter()


async def exigir_admin(x_admin_key: str = Header(default="")) -> None:
    # Roda antes da validação do corpo: quem não tem a chave não descobre o formato.
    if not settings.admin_api_key:
        raise HTTPException(status_code=403, detail="rota de firmware desligada")
    if not admin_chave_valida(x_admin_key):
        raise HTTPException(status_code=401, detail="X-Admin-Key inválida")


class FirmwareIn(BaseModel):
    versao: str
    url: str
    sha256: str
    notas: Optional[str] = None


def _json(registro: dict) -> dict:
    """Datas do Firestore viram texto ISO; o resto segue igual."""
    return {k: (v.isoformat() if isinstance(v, datetime) else v) for k, v in registro.items()}


@router.put("/firmware/{alvo}", dependencies=[Depends(exigir_admin)])
async def registrar_firmware(alvo: str, body: FirmwareIn):
    if alvo not in validacao.ALVOS:
        raise HTTPException(status_code=404, detail="alvo desconhecido")

    try:
        versao = validacao.validar_versao(body.versao)
    except validacao.ErroValidacao as e:
        raise HTTPException(status_code=422, detail=f"versao: {e}")
    try:
        url = validacao.validar_url(body.url)
    except validacao.ErroValidacao as e:
        raise HTTPException(status_code=422, detail=f"url: {e}")
    try:
        sha256 = validacao.validar_sha256(body.sha256)
    except validacao.ErroValidacao as e:
        raise HTTPException(status_code=422, detail=f"sha256: {e}")
    try:
        notas = validacao.validar_notas(body.notas)
    except validacao.ErroValidacao as e:
        raise HTTPException(status_code=422, detail=f"notas: {e}")

    try:
        registro = await repositorio.registrar(alvo, versao, url, sha256, notas)
    except repositorio.VersaoJaRegistrada:
        raise HTTPException(status_code=409, detail="esta versão já é a atual deste alvo")
    except repositorio.VersaoBloqueada:
        raise HTTPException(status_code=409, detail="versao_bloqueada: esta versão foi retirada e não pode ser registrada de novo")
    except Exception:
        log.exception("[%s] erro ao registrar firmware", alvo)
        raise HTTPException(status_code=502, detail="não foi possível registrar o firmware agora")

    log.info("[%s] firmware %s registrado", alvo, versao)
    return _json(registro)


@router.post("/firmware/{alvo}/retirar", dependencies=[Depends(exigir_admin)])
async def retirar_firmware(alvo: str):
    """Retira a versão atual (ela fica bloqueada) e volta o registro para a anterior."""
    if alvo not in validacao.ALVOS:
        raise HTTPException(status_code=404, detail="alvo desconhecido")
    try:
        registro = await repositorio.retirar(alvo)
    except repositorio.SemVersaoAnterior:
        raise HTTPException(status_code=409, detail="sem_versao_anterior: não há versão anterior para voltar")
    except Exception:
        log.exception("[%s] erro ao retirar firmware", alvo)
        raise HTTPException(status_code=502, detail="não foi possível retirar o firmware agora")
    log.info("[%s] firmware retirado; registro volta para %s", alvo, registro["versao"])
    return _json(registro)
