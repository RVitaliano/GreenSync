"""Aviso de inicialização da rota de firmware."""
import logging

from app import main
from app.config import settings


def test_admin_key_vazia_avisa_que_a_rota_esta_desligada(monkeypatch, caplog):
    monkeypatch.setattr(settings, "admin_api_key", "")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.avisar_firmware()
    assert "ADMIN_API_KEY vazia" in caplog.text and "DESLIGADA" in caplog.text


def test_admin_key_preenchida_nao_avisa_nem_vaza_a_chave(monkeypatch, caplog):
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.avisar_firmware()
    assert caplog.text == ""
