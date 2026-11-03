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