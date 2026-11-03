import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.firebase_client import init_firebase
from app.mqtt_client import run_mqtt_subscriber
from app.redis_client import close_redis
from app.routes.audio import router as audio_router
from app.routes.ia import router as ia_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("greensync")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_firebase()
    if not settings.redis_url:
        logger.warning("REDIS_URL vazia: o limite de perguntas está DESLIGADO")
    task = asyncio.create_task(run_mqtt_subscriber())
    yield
    task.cancel()
    await close_redis()


app = FastAPI(title="GreenSync Backend", lifespan=lifespan)
app.include_router(ia_router)
app.include_router(audio_router)


@app.get("/")
def health_check():
    return {"status": "ok"}