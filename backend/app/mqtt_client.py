import asyncio
import json
import logging
import re
import ssl

import aiomqtt
from pydantic import ValidationError

from app.config import settings
from app.firebase_client import save_reading, save_status
from app.models import DeviceStatus, SensorReading
from app.seguranca import DEVICE_ID_PADRAO

logger = logging.getLogger("greensync.mqtt")

# Conexão ativa com o broker (a mesma que escuta os sensores). Fica None enquanto
# estiver desconectado; publicar_comando usa isto para enviar comandos ao vaso.
_cliente: aiomqtt.Client | None = None


class MqttIndisponivel(Exception):
    """Sem conexão com o broker no momento de publicar."""


async def publicar_comando(device_id: str, payload: dict) -> None:
    """Publica um comando em greensync/{device_id}/comandos (QoS 1, sem retain).

    Sem retain de propósito: um comando de rega guardado no broker seria entregue
    de novo a quem se reconectasse depois, e a bomba ligaria sem ninguém pedir.
    """
    cliente = _cliente
    if cliente is None:
        raise MqttIndisponivel("sem conexão com o broker MQTT")
    topico = settings.mqtt_topic_comandos.format(device_id=device_id)
    try:
        await cliente.publish(topico, json.dumps(payload), qos=1, retain=False, timeout=5)
    except aiomqtt.MqttError as exc:
        raise MqttIndisponivel(str(exc)) from exc
    logger.info("[%s] comando publicado em %s: %s", device_id, topico, payload)


def parse_topic(topic: str) -> tuple[str, str] | None:
    """greensync/{deviceId}/{tipo} -> (deviceId, tipo). None se fora do padrão."""
    parts = topic.split("/")
    if len(parts) != 3 or parts[0] != "greensync":
        return None
    return parts[1], parts[2]


async def handle_message(message: aiomqtt.Message) -> None:
    """Valida uma mensagem recebida. Mensagem inválida é logada e descartada."""
    topic = message.topic.value
    parsed = parse_topic(topic)
    if parsed is None:
        logger.warning("Tópico fora do padrão, ignorado: %s", topic)
        return
    device_id, kind = parsed
    # Mesma regra das rotas HTTP: o id vira nome de documento no Firestore (vazio, "." e ".."
    # não são nomes válidos) e um id que a API recusa não teria como ser consultado.
    if not re.fullmatch(DEVICE_ID_PADRAO, device_id):
        logger.warning("device_id inválido no tópico, ignorado: %r", topic)
        return

    try:
        if kind == "sensores":
            reading = SensorReading.model_validate_json(message.payload)
            logger.info("[%s] leitura válida: %s", device_id, reading)
            await save_reading(device_id, reading)
        elif kind == "status":
            status = DeviceStatus.model_validate_json(message.payload)
            logger.info("[%s] status: %s", device_id, status.status)
            await save_status(device_id, status.status)
        else:
            logger.warning("[%s] tipo de tópico desconhecido: %s", device_id, kind)
    except ValidationError as exc:
        logger.warning(
            "[%s] payload inválido em %s, descartado: %s",
            device_id, topic, exc.errors(include_url=False),
        )


async def run_mqtt_subscriber() -> None:
    """Conecta no broker e reconecta automaticamente se cair."""
    global _cliente
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password or None,
                tls_context=ssl.create_default_context() if settings.mqtt_use_tls else None,
            ) as client:
                logger.info(
                    "Conectado ao broker MQTT em %s:%s",
                    settings.mqtt_host, settings.mqtt_port,
                )
                await client.subscribe(settings.mqtt_topic_sensores, qos=1)
                await client.subscribe(settings.mqtt_topic_status, qos=1)
                _cliente = client

                async for message in client.messages:
                    try:
                        await handle_message(message)
                    except Exception:
                        logger.exception("Erro inesperado ao processar mensagem; seguindo")

        except aiomqtt.MqttError as exc:
            logger.warning("Sem conexão com o broker (%s). Tentando de novo em 5s...", exc)
            await asyncio.sleep(5)
        except Exception:
            # Qualquer outro erro não pode matar a tarefa em silêncio: sem ela o backend
            # para de receber sensores e de publicar comandos, mas segue "no ar".
            logger.exception("Erro inesperado no assinante MQTT. Tentando de novo em 5s...")
            await asyncio.sleep(5)
        finally:
            _cliente = None