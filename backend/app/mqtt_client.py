import asyncio
import logging
import aiomqtt

from app.config import settings

logger = logging.getLogger("greensync.mqtt")

async def run_mqtt_subscriber() -> None:
    #conecta no broker e reconecta automaticamente se cair

    while True:
        try:
            async with aiomqtt.Client(
                hostname=settings.mqtt_host,
                port=settings.mqtt_port,
                username=settings.mqtt_username or None,
                password=settings.mqtt_password or None,
            ) as client:
                logger.info("Conectado ao broker MQTT em %s:%s", settings.mqtt_host, settings.mqtt_port)
                await client.subscribe(settings.mqtt_topic_sensores, qos=1)
                await client.subscribe(settings.mqtt_topic_status, qos=1)

                async for message in client.messages:
                    print(message.topic, message.payload)

                    
        except aiomqtt.MqttError as exc:
            logger.warning("Conexão MQTT perdida (%s). Reconectanto em 5s...", exc)
            await asyncio.sleep(5)