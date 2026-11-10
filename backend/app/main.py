import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agenda.servico import agendador
from app.config import settings
from app.firebase_client import init_firebase
from app.mqtt_client import run_mqtt_subscriber
from app.redis_client import close_redis
from app.routes.audio import router as audio_router
from app.routes.ia import router as ia_router


def nivel_de_log(nome: str) -> int:
    """LOG_LEVEL em número do logging. Nome desconhecido não derruba o backend: vale INFO."""
    nivel = logging.getLevelName((nome or "").strip().upper())
    return nivel if isinstance(nivel, int) else logging.INFO


logging.basicConfig(level=nivel_de_log(settings.log_level))
logger = logging.getLogger("greensync")


def avisar_configuracao() -> None:
    """Avisos de inicialização para configurações que deixam o backend menos protegido."""
    if not settings.redis_url:
        logger.warning("REDIS_URL vazia: o limite de perguntas está DESLIGADO")
    if not settings.api_key:
        logger.warning("API_KEY vazia: /perguntar e /audio estão ABERTAS, sem autenticação "
                       "(só para desenvolvimento)")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_firebase()
    avisar_configuracao()
    task = asyncio.create_task(run_mqtt_subscriber())
    try:
        await agendador.iniciar()   # recarrega as regas pendentes (REQ-FUNC-012)
    except Exception:
        # Sem Firestore agora, o backend sobe mesmo assim (sensores e perguntas seguem).
        logger.exception("Não consegui recarregar os agendamentos de rega")
    yield
    await agendador.parar()
    task.cancel()
    await close_redis()


app = FastAPI(title="GreenSync Backend", lifespan=lifespan)
app.include_router(ia_router)
app.include_router(audio_router)


@app.get("/")
def health_check():
    return {"status": "ok"}
