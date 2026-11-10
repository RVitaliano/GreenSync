"""Inicialização: avisos de configuração insegura e nível de log."""
import logging

import pytest

from app import main
from app.config import settings


def avisos(caplog):
    return [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING and r.name == "greensync"]


def test_api_key_vazia_avisa_no_log(monkeypatch, caplog):
    monkeypatch.setattr(settings, "api_key", "")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.avisar_configuracao()
    assert any("API_KEY vazia" in a for a in avisos(caplog))


def test_api_key_preenchida_nao_avisa_nem_vaza_a_chave(monkeypatch, caplog):
    monkeypatch.setattr(settings, "api_key", "segredo-super-secreto")
    monkeypatch.setattr(settings, "redis_url", "redis://x:6379/0")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.avisar_configuracao()
    assert avisos(caplog) == []
    assert "segredo-super-secreto" not in caplog.text


def test_redis_vazio_continua_avisando(monkeypatch, caplog):
    monkeypatch.setattr(settings, "redis_url", "")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.avisar_configuracao()
    assert any("REDIS_URL vazia" in a for a in avisos(caplog))


@pytest.mark.parametrize("nome,esperado", [
    ("INFO", logging.INFO), ("debug", logging.DEBUG), (" warning ", logging.WARNING),
    ("ERROR", logging.ERROR), ("", logging.INFO), ("verboso", logging.INFO),
])
def test_nivel_de_log(nome, esperado):
    assert main.nivel_de_log(nome) == esperado
