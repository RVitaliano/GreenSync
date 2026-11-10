"""ler_leitura_segura (rotas) e ler_leitura_atual (agendador): erro e prazo do Firestore."""
import logging
import time

import pytest

from app import firebase_client
from app.config import settings

pytestmark = pytest.mark.anyio

LEITURA = {"umidade_solo": 20, "status_vaso": "online"}


async def test_leitura_normal_passa(monkeypatch):
    monkeypatch.setattr(firebase_client, "_read_current_sync", lambda d: LEITURA)
    assert await firebase_client.ler_leitura_segura("vaso-01") == LEITURA


def quebra(device_id):
    raise RuntimeError("segredo-no-erro")


async def test_erro_do_firestore_vira_none_nas_rotas(monkeypatch, caplog):
    monkeypatch.setattr(firebase_client, "_read_current_sync", quebra)
    with caplog.at_level(logging.ERROR, logger="greensync.firebase"):
        assert await firebase_client.ler_leitura_segura("vaso-01") is None
    assert "vaso-01" in caplog.text and "RuntimeError" in caplog.text
    assert "segredo-no-erro" not in caplog.text      # só o tipo do erro, nunca a mensagem


async def test_ler_leitura_atual_continua_levantando_o_erro(monkeypatch):
    monkeypatch.setattr(firebase_client, "_read_current_sync", quebra)
    with pytest.raises(RuntimeError):
        await firebase_client.ler_leitura_atual("vaso-01")


def lenta(device_id):
    time.sleep(0.4)
    return LEITURA


async def test_firestore_lento_vira_none_dentro_do_prazo(monkeypatch):
    monkeypatch.setattr(settings, "firestore_timeout_s", 0.05)
    monkeypatch.setattr(firebase_client, "_read_current_sync", lenta)
    t0 = time.monotonic()
    assert await firebase_client.ler_leitura_segura("vaso-01") is None
    assert time.monotonic() - t0 < 0.3


async def test_ler_leitura_atual_levanta_timeout_se_lento(monkeypatch):
    monkeypatch.setattr(settings, "firestore_timeout_s", 0.05)
    monkeypatch.setattr(firebase_client, "_read_current_sync", lenta)
    with pytest.raises(TimeoutError):
        await firebase_client.ler_leitura_atual("vaso-01")
