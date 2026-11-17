import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.agenda.servico import agendador
from app.config import settings
from app.firebase_client import init_firebase
from app.mqtt_client import run_mqtt_subscriber
from app.redis_client import close_redis
from app.routes.audio import router as audio_router
from app.routes.dispositivos import router as dispositivos_router
from app.routes.firmware import router as firmware_router
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


# Chaves que ninguém deveria usar em produção (comparação sem diferenciar maiúsculas).
CHAVES_FRACAS = {"1234", "12345", "123456", "12345678", "senha", "password", "admin", "secret",
                 "segredo", "teste", "test", "changeme", "trocar", "sua_chave_aqui"}
CHAVE_TAMANHO_MIN = 12


def em_producao() -> bool:
    """O Render define RENDER=true em todo serviço dele. Local e testes não têm essa variável."""
    return os.environ.get("RENDER", "").strip().lower() in ("true", "1")


def _chave_fraca(chave: str) -> bool:
    return len(chave) < CHAVE_TAMANHO_MIN or chave.lower() in CHAVES_FRACAS


def problemas_de_producao() -> list[str]:
    """Configurações perigosas em produção. Só os NOMES das variáveis, nunca os valores."""
    problemas = []
    if not settings.api_key:
        problemas.append("API_KEY vazia: /perguntar, /audio e a rega ficariam abertas para qualquer um")
    elif _chave_fraca(settings.api_key):
        problemas.append(f"API_KEY fraca (use pelo menos {CHAVE_TAMANHO_MIN} caracteres aleatórios; "
                         "ex.: openssl rand -hex 24)")
    # ADMIN_API_KEY vazia é seguro (a rota de firmware fica desligada); preenchida e fraca não é.
    if settings.admin_api_key and _chave_fraca(settings.admin_api_key):
        problemas.append(f"ADMIN_API_KEY fraca (use pelo menos {CHAVE_TAMANHO_MIN} caracteres aleatórios)")
    return problemas


def validar_producao() -> None:
    """No Render, recusa subir com chave vazia ou fraca (melhor não subir do que subir aberto)."""
    if not em_producao():
        return
    problemas = problemas_de_producao()
    if problemas:
        raise RuntimeError("Configuração insegura para produção: " + "; ".join(problemas))
    if not settings.mqtt_use_tls:
        logger.warning("MQTT_USE_TLS=false em produção: a conexão com o broker não é criptografada")
    if settings.mqtt_host in ("localhost", "mosquitto", "127.0.0.1"):
        logger.warning("MQTT_HOST=%s parece um broker local; em produção use o do EMQX Cloud", settings.mqtt_host)


def avisar_firmware() -> None:
    """Aviso de inicialização da rota de firmware (função própria, chamada após avisar_configuracao)."""
    if not settings.admin_api_key:
        logger.warning("ADMIN_API_KEY vazia: a rota de firmware (PUT /firmware/{alvo}) está DESLIGADA")


@asynccontextmanager
async def lifespan(app: FastAPI):
    validar_producao()      # antes de abrir qualquer conexão: configuração insegura não sobe
    init_firebase()
    avisar_configuracao()
    avisar_firmware()
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
app.include_router(dispositivos_router)
app.include_router(firmware_router)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.get("/health")
def health():
    """Saúde para o Render (Health Check Path). Não acessa Firestore, MQTT nem Redis: responde
    enquanto o processo estiver de pé, sem depender (nem gastar cota) de nenhum serviço externo."""
    return {"status": "ok"}
