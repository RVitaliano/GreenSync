import asyncio
import logging
import time
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


# Relógio do ESP fora destes limites (sem NTP, contador desde o boot, lixo) não é confiável.
TIMESTAMP_MINIMO = int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
TIMESTAMP_FUTURO_MAX_S = 3600   # mais que 1 h à frente da hora do servidor


def timestamp_confiavel(ts: int | None, agora: float | None = None) -> datetime | None:
    """Data do `timestamp` do ESP, ou None se faltar ou for absurdo (aí vale a hora do servidor)."""
    if ts is None:
        return None
    agora = time.time() if agora is None else agora
    if ts < TIMESTAMP_MINIMO or ts > agora + TIMESTAMP_FUTURO_MAX_S:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _save_reading_sync(device_id: str, reading: SensorReading) -> None:
    db = init_firebase()
    device_ref = db.collection("devices").document(device_id)

    data = reading.model_dump(exclude={"timestamp"})
    ts = timestamp_confiavel(reading.timestamp)
    if ts is None:
        ts = firestore.SERVER_TIMESTAMP  # ESP sem relógio ou com relógio absurdo: hora do servidor
        if reading.timestamp is not None:
            logger.warning("[%s] timestamp %s fora do razoável, usando a hora do servidor",
                           device_id, reading.timestamp)

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


def _read_current_sync(device_id: str) -> dict | None:
    """Campo `leitura_atual` do dispositivo, ou None se ele ainda não existe.

    Junta a ele o `status` do documento (online/offline, vindo do Last Will)
    como `status_vaso`, para o assistente saber se o dado ainda vale como "agora".
    `leitura_atual` já traz `updated_at`, gravado a cada leitura.
    """
    db = init_firebase()
    doc = db.collection("devices").document(device_id).get()
    if not doc.exists:
        return None
    dados = doc.to_dict() or {}
    leitura = dados.get("leitura_atual")
    if not leitura:
        return None
    return {**leitura, "status_vaso": dados.get("status")}


# O SDK do Firestore é síncrono; to_thread evita travar o loop do MQTT/FastAPI.
async def save_reading(device_id: str, reading: SensorReading) -> None:
    await asyncio.to_thread(_save_reading_sync, device_id, reading)
    logger.info("[%s] leitura gravada no Firestore", device_id)


async def save_status(device_id: str, status: str) -> None:
    await asyncio.to_thread(_save_status_sync, device_id, status)
    logger.info("[%s] status '%s' gravado no Firestore", device_id, status)


async def ler_leitura_atual(device_id: str) -> dict | None:
    """Leitura atual do vaso, com prazo (`firestore_timeout_s`). Levanta erro/TimeoutError.

    Versão usada pelo agendador, que precisa saber que a leitura falhou.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(_read_current_sync, device_id),
        timeout=settings.firestore_timeout_s,
    )


async def ler_leitura_segura(device_id: str) -> dict | None:
    """Usada pelas rotas: Firestore lento ou fora vira "sem dados" (None), nunca erro."""
    try:
        return await ler_leitura_atual(device_id)
    except Exception as e:
        logger.error("[%s] não consegui ler a leitura atual (%s); seguindo sem dados",
                     device_id, type(e).__name__)
        return None