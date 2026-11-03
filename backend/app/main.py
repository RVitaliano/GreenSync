import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.firebase_client import init_firebase
from app.mqtt_client import run_mqtt_subscriber
from app.routes.ia import router as ia_router

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_firebase()
    task = asyncio.create_task(run_mqtt_subscriber())
    yield
    task.cancel()


app = FastAPI(title="GreenSync Backend", lifespan=lifespan)
app.include_router(ia_router)


@app.get("/")
def health_check():
    return {"status": "ok"}