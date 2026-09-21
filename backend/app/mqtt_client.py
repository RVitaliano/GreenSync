import asyncio
import logging

import aiomqtt
from pydantic import ValidationError

from app.config import settings
from app.models import DeviceStatus, SensorReading

logger = logging.getLogger("greensync.mqtt")


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

    try:
        if kind == "sensores":
            reading = SensorReading.model_validate_json(message.payload)
            logger.info("[%s] leitura válida: %s", device_id, reading)
            # próximo passo: gravar no Firestore
        elif kind == "status":
            status = DeviceStatus.model_validate_json(message.payload)
            logger.info("[%s] status: %s", device_id, status.status)
            # próximo passo: atualizar status no Firestore
        else:
            logger.warning("[%s] tipo de tópico desconhecido: %s", device_id, kind)
    except ValidationError as exc:
        logger.warning(
            "[%s] payload inválido em %s, descartado: %s",
            device_id, topic, exc.errors(include_url=False),
        )


async def run_mqtt_subscriber() -> None:
    """Conecta no broker e reconecta automaticamente se cair."""
    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password or None,
            ) as client:
                logger.info(
                    "Conectado ao broker MQTT em %s:%s",
                    settings.mqtt_host, settings.mqtt_port,
                )
                await client.subscribe(settings.mqtt_topic_sensores, qos=1)
                await client.subscribe(settings.mqtt_topic_status, qos=1)

                async for message in client.messages:
                    try:
                        await handle_message(message)
                    except Exception:
                        logger.exception("Erro inesperado ao processar mensagem; seguindo")

        except aiomqtt.MqttError as exc:
            logger.warning("Sem conexão com o broker (%s). Tentando de novo em 5s...", exc)
            await asyncio.sleep(5)