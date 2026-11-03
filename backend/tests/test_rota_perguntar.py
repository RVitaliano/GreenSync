"""Testa a rota POST /perguntar sem Gemini e sem Firestore (tudo simulado)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.responder import IAError
from app.config import settings
from app.routes import ia as rota

LEITURA = {"umidade_solo": 20, "temperatura_ar": 24.1, "bomba_ligada": False}


@pytest.fixture
def client(monkeypatch):
    """App só com o router de IA; Firestore e Gemini trocados por versões falsas."""
    chamadas = {}

    async def leitura_falsa(device_id):
        chamadas["device_id"] = device_id
        return LEITURA

    async def responder_falso(pergunta, leitura):
        chamadas["pergunta"] = pergunta
        chamadas["leitura"] = leitura
        return {"texto": "Estou com sede.", "estado": {"estado": "atencao", "problemas": ["solo_seco"]},
                "modelo": "modelo-falso"}

    monkeypatch.setattr(rota, "ler_leitura_atual", leitura_falsa)
    monkeypatch.setattr(rota, "responder", responder_falso)
    monkeypatch.setattr(settings, "api_key", "segredo")

    app = FastAPI()
    app.include_router(rota.router)
    c = TestClient(app)
    c.chamadas = chamadas
    return c


def post(c, device="vaso-01", pergunta="Qual a temperatura?", chave="segredo"):
    return c.post("/perguntar", json={"device_id": device, "pergunta": pergunta},
                  headers={"X-API-Key": chave})


def test_resposta_ok(client):
    r = post(client)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["texto"] == "Estou com sede."
    assert corpo["tela"] == "dados"            # a pergunta cita "temperatura"
    assert corpo["modelo"] == "modelo-falso"
    assert client.chamadas["device_id"] == "vaso-01"
    assert client.chamadas["leitura"] == LEITURA


def test_chave_errada_da_401(client):
    assert post(client, chave="errada").status_code == 401


def test_sem_chave_da_401(client):
    r = client.post("/perguntar", json={"device_id": "vaso-01", "pergunta": "Oi?"})
    assert r.status_code == 401


def test_chave_com_acento_nao_derruba(client):
    # compare_digest com str não aceita acento; aqui deve só dar 401, nunca 500
    r = client.post("/perguntar", json={"device_id": "vaso-01", "pergunta": "Oi?"},
                    headers={"X-API-Key": "segredoé".encode("utf-8")})
    assert r.status_code == 401


def test_chave_vazia_no_env_deixa_aberta(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    r = client.post("/perguntar", json={"device_id": "vaso-01", "pergunta": "Oi?"})
    assert r.status_code == 200


@pytest.mark.parametrize("device", ["a/b", "../x", "", "x" * 65, "vaso 01"])
def test_device_id_invalido_da_422(client, device):
    assert post(client, device=device).status_code == 422


def test_pergunta_vazia_ou_longa_da_422(client):
    assert post(client, pergunta="").status_code == 422
    assert post(client, pergunta="a" * 501).status_code == 422


def test_ia_fora_do_ar_da_502(client, monkeypatch):
    async def falha(pergunta, leitura):
        raise IAError("nenhum modelo respondeu")

    monkeypatch.setattr(rota, "responder", falha)
    r = post(client)
    assert r.status_code == 502
    assert r.json()["detail"] == "assistente indisponível"