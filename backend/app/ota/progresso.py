"""Progresso da atualização (OTA) informado pelo vaso em greensync/{deviceId}/ota.

Só reflete o estado em devices/{id}.ota. Nunca mexe em devices/{id}.fw / fw_s3: quem informa
a versão instalada é o status do vaso. Progresso de outra atualização (id ou alvo diferente),
repetido fora de ordem ou posterior a um estado final é ignorado.
"""
import logging

from app.models import OtaProgresso
from app.ota import repositorio

log = logging.getLogger("greensync.ota")


async def tratar_progresso(device_id: str, p: OtaProgresso) -> str:
    """Aplica o progresso. Devolve "aplicar" ou o motivo de ter ignorado (para log e testes)."""
    resultado = await repositorio.aplicar_progresso(device_id, p.id, p.alvo, p.estado, p.erro)
    if resultado != "aplicar":
        log.warning("[%s] progresso de OTA ignorado (%s): alvo=%s estado=%s", device_id, resultado, p.alvo, p.estado)
        return resultado
    if p.estado == "ok":
        log.info("[%s] atualização %s concluída: %s %s", device_id, p.id, p.alvo, p.versao)
    elif p.estado in ("falhou", "revertido"):
        log.warning("[%s] atualização %s %s (%s): %s", device_id, p.id, p.estado, p.alvo, p.erro or "sem código")
    else:
        log.info("[%s] atualização %s: %s (%s)", device_id, p.id, p.estado, p.alvo)
    return resultado
