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
    """Pede ao vaso que instale a versão do registro. Devolve {"resultado", "id", "motivo", "versao"}.

    Erros inesperados (Firestore fora do ar etc.) sobem para a rota responder 502.
    """
    return await _solicitar("atualizar", device_id, alvo, leitura, estado)


async def solicitar_reversao(device_id: str, alvo: str, leitura: dict | None, estado: dict) -> dict:
    """Pede ao vaso que volte para a cópia anterior; `versao` é a versão BOA do registro.

    As regras e o fluxo são os da atualização; só o comando muda (sem url nem sha256: o vaso usa
    a cópia que já tem e confere que é a versão esperada).
    """
    return await _solicitar("reverter", device_id, alvo, leitura, estado)


async def _solicitar(tipo: str, device_id: str, alvo: str, leitura: dict | None, estado: dict) -> dict:
    registro = await repositorio.ler(alvo)
    if not registro:
        return _recusa("sem_firmware")
    try:
        versao = validacao.validar_versao(registro.get("versao"))
        if tipo == "atualizar":
            url = validacao.validar_url(registro.get("url"))
            sha256 = validacao.validar_sha256(registro.get("sha256"))
    except validacao.ErroValidacao as e:
        # Registro antigo/torto, ou host que saiu da lista permitida: nunca manda ao vaso.
        log.warning("[%s] registro de firmware inválido, %s recusada: %s", alvo, tipo, e)
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
            {"alvo": alvo, "id": ota_id, "versao": versao, "tipo": tipo, "estado": "solicitada",
             "atualizado_em": agora},
            settings.ota_timeout_s,
        )
        if not ganhou:
            return _recusa("ota_em_curso")

        if tipo == "atualizar":
            comando = {"acao": "atualizar", "alvo": alvo, "id": ota_id, "versao": versao, "url": url, "sha256": sha256}
        else:
            comando = {"acao": "reverter", "alvo": alvo, "id": ota_id, "versao": versao}
        try:
            await publicar_comando(device_id, comando)
        except Exception as e:
            motivo = MOTIVO_INCERTO if getattr(e, "incerta", False) else "não consegui falar com o broker"
            log.error("[%s] %s %s: publicação falhou: %s", device_id, tipo, ota_id, type(e).__name__)
            try:
                await repositorio.marcar_ota(device_id, ota_id, "falhou", motivo)
            except Exception:
                log.exception("[%s] %s %s: não consegui marcar como falhou", device_id, tipo, ota_id)
            return {"resultado": "falhou", "id": ota_id, "motivo": motivo, "versao": versao}

    if tipo == "reverter" and isinstance(instalada, str) and instalada:
        # A versão que está sendo revertida não pode ser reinstalada nem registrada de novo
        # (o OTA automático também a ignora). Nunca bloqueia a versão atual do registro.
        try:
            if await repositorio.bloquear_versao(alvo, instalada):
                log.info("[%s] versão %s bloqueada no registro de %s", device_id, instalada, alvo)
        except Exception:
            log.exception("[%s] não consegui bloquear a versão %s de %s", device_id, instalada, alvo)

    log.info("[%s] %s %s (%s %s) solicitada", device_id, tipo, ota_id, alvo, versao)
    return {"resultado": "solicitada", "id": ota_id, "motivo": None, "versao": versao}
