import asyncio
import logging
from datetime import datetime, timezone

import firebase_admin
from firebase_admin import credentials, firestore

from app.config import settings
from app.models import SensorReading

logger = logging.getLogger("greensync.firebase")

_db = None


def init_firebase():
    """Inicializa o Admin SDK uma vez e devolve o cliente do Firestore."""
    global _db
    if _db is None:
        cred = credentials.Certificate(settings.firebase_credentials_path)
        firebase_admin.initialize_app(cred)
        _db = firestore.client()
        logger.info("Firebase inicializado")
    return _db


def _save_reading_sync(device_id: str, reading: SensorReading) -> None:
    db = init_firebase()
    device_ref = db.collection("devices").document(device_id)

    data = reading.model_dump(exclude={"timestamp"})
    if reading.timestamp is not None:
        ts = datetime.fromtimestamp(reading.timestamp, tz=timezone.utc)
    else:
        ts = firestore.SERVER_TIMESTAMP  # ESP sem relógio: usa a hora do servidor

    batch = db.batch()
    batch.set(
        device_ref,
        {
            "status": "online",
            "last_seen": firestore.SERVER_TIMESTAMP,
            "leitura_atual": {**data, "updated_at": firestore.SERVER_TIMESTAMP},
        },
        merge=True,
    )
    batch.set(device_ref.collection("historico").document(), {**data, "timestamp": ts})
    batch.commit()


def _save_status_sync(device_id: str, status: str) -> None:
    db = init_firebase()
    db.collection("devices").document(device_id).set({"status": status}, merge=True)


# O SDK do Firestore é síncrono; to_thread evita travar o loop do MQTT/FastAPI.
async def save_reading(device_id: str, reading: SensorReading) -> None:
    await asyncio.to_thread(_save_reading_sync, device_id, reading)
    logger.info("[%s] leitura gravada no Firestore", device_id)


async def save_status(device_id: str, status: str) -> None:
    await asyncio.to_thread(_save_status_sync, device_id, status)
    logger.info("[%s] status '%s' gravado no Firestore", device_id, status)