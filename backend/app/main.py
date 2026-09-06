import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.mqtt_client import run_mqtt_subscriber

logging.basicConfig(level=logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_mqtt_subscriber())
    yield
    task.cancel()
app = FastAPI(title="GreenSync Backend", lifespan=lifespan)
@app.get("/")
def health_check():
    return {"status": "ok"}