"""PUT /firmware/{alvo}: administração do registro de firmware."""
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.ota import repositorio
from app.routes import firmware as rota

URL = "https://github.com/o/r/releases/download/v1/fw.bin"
HASH = "AB" * 32
CORPO = {"versao": "1.0.0", "url": URL, "sha256": HASH}


@pytest.fixture
def c(monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(settings, "api_key", "chave-do-app")
    registros = {}
    chamadas = []

    async def registrar(alvo, versao, url, sha256, notas=None):
        chamadas.append(alvo)
        if alvo == "explode":
            raise RuntimeError("firestore fora do ar")
        atual = registros.get(alvo)
        if atual and atual["versao"] == versao:
            raise repositorio.VersaoJaRegistrada(versao)
        registros[alvo] = {"versao": versao, "url": url, "sha256": sha256, "notas": notas,
                           "publicado_em": None, "anterior": None}
        return registros[alvo]

    monkeypatch.setattr(rota.repositorio, "registrar", registrar)
    app = FastAPI()
    app.include_router(rota.router)
    client = TestClient(app)
    client.chamadas = chamadas
    return client


def put(c, alvo="wroom", corpo=None, chave="admin-secreta"):
    cab = {"X-Admin-Key": chave} if chave is not None else {}
    return c.put(f"/firmware/{alvo}", headers=cab, json=CORPO if corpo is None else corpo)


def test_sucesso_devolve_o_registro_gravado(c):
    r = put(c, corpo={**CORPO, "notas": "  primeira  "})
    assert r.status_code == 200
    j = r.json()
    assert j["versao"] == "1.0.0" and j["url"] == URL and j["notas"] == "primeira"
    assert j["sha256"] == HASH.lower()                    # normalizado para minúsculas
    assert c.chamadas == ["wroom"]


def test_alvo_s3_tambem_funciona(c):
    assert put(c, alvo="s3").status_code == 200


# ---------- autenticação ----------

def test_sem_admin_key_configurada_a_rota_esta_desligada_403(c, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    for chave in (None, "", "qualquer", "chave-do-app"):
        assert put(c, chave=chave).status_code == 403
    assert c.chamadas == []


@pytest.mark.parametrize("chave", [None, "", "errada", "admin-secret"])
def test_chave_errada_ou_ausente_da_401(c, chave):
    assert put(c, chave=chave).status_code == 401
    assert c.chamadas == []


def test_api_key_normal_nao_abre_a_rota_de_administracao(c):
    r = c.put("/firmware/wroom", headers={"X-API-Key": "chave-do-app"}, json=CORPO)
    assert r.status_code == 401
    r = c.put("/firmware/wroom", headers={"X-Admin-Key": "chave-do-app"}, json=CORPO)
    assert r.status_code == 401
    assert c.chamadas == []


def test_sem_chave_nao_revela_validacao_do_corpo(c):
    assert put(c, chave="errada", corpo={"versao": "lixo"}).status_code == 401
    assert put(c, chave="errada", alvo="xyz").status_code == 401


# ---------- alvo e corpo ----------

@pytest.mark.parametrize("alvo", ["esp32", "WROOM", "s3x", "wroom%20"])
def test_alvo_invalido_da_404(c, alvo):
    assert put(c, alvo=alvo).status_code == 404
    assert c.chamadas == []


@pytest.mark.parametrize("campo,valor", [
    ("versao", "1.0"),
    ("versao", "v1.0.0"),
    ("url", "http://github.com/x.bin"),
    ("url", "https://evil.com/x.bin"),
    ("url", "https://u:p@github.com/x.bin"),
    ("sha256", "abc"),
    ("sha256", "z" * 64),
    ("notas", "a" * 501),
])
def test_corpo_invalido_da_422_com_mensagem_clara(c, campo, valor):
    r = put(c, corpo={**CORPO, campo: valor})
    assert r.status_code == 422
    assert r.json()["detail"].startswith(f"{campo}:")
    assert c.chamadas == []


@pytest.mark.parametrize("corpo", [{}, {"versao": "1.0.0"}, {**CORPO, "versao": 5}])
def test_campos_faltando_ou_de_tipo_errado_da_422(c, corpo):
    assert put(c, corpo=corpo).status_code == 422


# ---------- conflito e erros ----------

def test_versao_igual_a_atual_da_409(c):
    assert put(c).status_code == 200
    r = put(c)
    assert r.status_code == 409
    assert "já é a atual" in r.json()["detail"]


def test_versao_menor_e_aceita(c):
    assert put(c, corpo={**CORPO, "versao": "2.0.0"}).status_code == 200
    assert put(c, corpo={**CORPO, "versao": "1.0.0"}).status_code == 200


def test_erro_inesperado_vira_502_sem_vazar_nem_logar_a_chave(c, caplog, monkeypatch):
    monkeypatch.setattr(rota.validacao, "ALVOS", ("wroom", "s3", "explode"))
    with caplog.at_level(logging.INFO, logger="greensync.firmware"):
        r = put(c, alvo="explode")
    assert r.status_code == 502
    assert "firestore" not in r.text.lower()
    assert "admin-secreta" not in caplog.text and "admin-secreta" not in r.text
