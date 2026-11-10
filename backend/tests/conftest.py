"""Configuração comum dos testes."""
import pytest

from app import redis_client
from app.config import settings


@pytest.fixture(autouse=True)
def sem_redis_real(monkeypatch):
    """Os testes nunca falam com um Redis de verdade, mesmo que o .env tenha REDIS_URL.

    Sem isso, o contador do Redis real misturaria uma execução com a outra
    e os testes passariam a falhar com 429 de vez em quando.
    """
    monkeypatch.setattr(settings, "redis_url", "")
    monkeypatch.setattr(redis_client, "_client", None)

@pytest.fixture(autouse=True)
def config_padrao(monkeypatch):
    """Todo teste começa com os valores PADRÃO de app/config.py, nunca com os do .env.

    O docker-compose injeta o .env no contêiner; sem isto, mudar um limite lá
    (ex.: REGA_DURACAO_MAX_S) quebraria testes que não têm nada a ver com isso.
    Quem precisa de outro valor continua usando monkeypatch.setattr(settings, ...).
    """
    for nome, campo in type(settings).model_fields.items():
        monkeypatch.setattr(settings, nome, campo.default)
