"""Pedido de atualização (OTA) a um vaso: valida, reivindica no Firestore e só então publica.

Mesma ordem da rega: gravar `devices/{id}.ota = solicitada` ANTES de publicar o comando, para duas
chamadas ao mesmo tempo nunca publicarem duas vezes. Versão, URL e hash vêm SEMPRE do registro
`firmware/{alvo}` cadastrado pelo administrador; o app só escolhe o alvo.

Aqui só existem os estados "solicitada" e "falhou"; o vaso informar baixando/aplicando/ok vem depois.
"""
import asyncio
import logging
import uuid

from app.agenda.regras import MOTIVO_INCERTO
from app.config import settings
from app.mqtt_client import publicar_comando
from app.ota import repositorio, validacao

log = logging.getLogger("greensync.ota")

# Complementa a transação do Firestore dentro deste processo (instância única).
trava = asyncio.Lock()

CAMPO_VERSAO = {"wroom": "fw", "s3": "fw_s3"}


def _recusa(motivo: str) -> dict:
    return {"resultado": "recusada", "id": None, "motivo": motivo, "versao": None}


async def solicitar_atualizacao(device_id: str, alvo: str, leitura: dict | None, estado: dict) -> dict:
    """Devolve {"resultado": "solicitada"|"recusada"|"falhou", "id", "motivo", "versao"}.

    Erros inesperados (Firestore fora do ar etc.) sobem para a rota responder 502.
    """
    registro = await repositorio.ler(alvo)
    if not registro:
        return _recusa("sem_firmware")
    try:
        versao = validacao.validar_versao(registro.get("versao"))
        url = validacao.validar_url(registro.get("url"))
        sha256 = validacao.validar_sha256(registro.get("sha256"))
    except validacao.ErroValidacao as e:
        # Registro antigo/torto, ou host que saiu da lista permitida: nunca manda ao vaso.
        log.warning("[%s] registro de firmware inválido, atualização recusada: %s", alvo, e)
        return _recusa("firmware_invalido")

    # Mesmo critério da rega. Para o S3 o "online" é o WROOM, que é quem fala MQTT.
    if leitura is None or estado.get("dados") == "sem_dados":
        return _recusa("sem_dados")
    if estado.get("offline"):
        return _recusa("offline")
    if leitura.get("bomba_ligada") is True:
        return _recusa("bomba_ligada")

    dispositivo = await repositorio.ler_dispositivo(device_id) or {}
    instalada = dispositivo.get(CAMPO_VERSAO[alvo])
    if instalada and instalada == versao:          # versão desconhecida (campo ausente) é permitida
        return _recusa("versao_igual")

    agora = repositorio._agora()
    if repositorio.ota_em_curso(dispositivo.get("ota"), agora, settings.ota_timeout_s):
        return _recusa("ota_em_curso")

    ota_id = uuid.uuid4().hex
    async with trava:
        ganhou = await repositorio.reivindicar_ota(
            device_id,
            {"alvo": alvo, "id": ota_id, "versao": versao, "estado": "solicitada", "atualizado_em": agora},
            settings.ota_timeout_s,
        )
        if not ganhou:
            return _recusa("ota_em_curso")

        comando = {"acao": "atualizar", "alvo": alvo, "id": ota_id, "versao": versao, "url": url, "sha256": sha256}
        try:
            await publicar_comando(device_id, comando)
        except Exception as e:
            motivo = MOTIVO_INCERTO if getattr(e, "incerta", False) else "não consegui falar com o broker"
            log.error("[%s] atualização %s: publicação falhou: %s", device_id, ota_id, type(e).__name__)
            try:
                await repositorio.marcar_ota(device_id, ota_id, "falhou", motivo)
            except Exception:
                log.exception("[%s] atualização %s: não consegui marcar como falhou", device_id, ota_id)
            return {"resultado": "falhou", "id": ota_id, "motivo": motivo, "versao": versao}

    log.info("[%s] atualização %s (%s %s) solicitada", device_id, ota_id, alvo, versao)
    return {"resultado": "solicitada", "id": ota_id, "motivo": None, "versao": versao}
