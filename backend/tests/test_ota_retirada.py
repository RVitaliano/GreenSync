"""Versões bloqueadas e retirada (repositório + rotas de administração do firmware)."""
import copy
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import settings
from app.ota import repositorio as repo
from app.routes import firmware as rota
from tests.falso_firestore import FIRESTORE_FALSO, DbFalso

URL = "https://github.com/o/r/releases/download/{}/fw.bin"
ANTES = datetime(2026, 1, 1, tzinfo=timezone.utc)


def registro(versao, anterior=None, bloqueadas=None, **kw):
    r = {"versao": versao, "url": URL.format(versao), "sha256": "ab" * 32, "notas": "n",
         "publicado_em": ANTES, "anterior": anterior}
    if bloqueadas is not None:
        r["bloqueadas"] = bloqueadas
    return {**r, **kw}


def ant(versao):
    return {"versao": versao, "url": URL.format(versao), "sha256": "cd" * 32}


@pytest.fixture
def db(monkeypatch):
    db = DbFalso()
    monkeypatch.setattr(repo, "init_firebase", lambda: db)
    monkeypatch.setattr(repo, "firestore", FIRESTORE_FALSO)
    return db


# ---------- registrar x versões bloqueadas ----------

@pytest.mark.anyio
async def test_registrar_recusa_versao_bloqueada_e_nao_grava(db):
    db.store["firmware"] = {"wroom": registro("2.0.0", bloqueadas=["1.5.0"])}
    antes = copy.deepcopy(db.store)
    with pytest.raises(repo.VersaoBloqueada):
        await repo.registrar("wroom", "1.5.0", URL.format("1.5.0"), "ef" * 32)
    assert db.store == antes


@pytest.mark.anyio
async def test_registrar_versao_igual_a_atual_continua_conflito(db):
    db.store["firmware"] = {"wroom": registro("2.0.0", bloqueadas=["1.5.0"])}
    with pytest.raises(repo.VersaoJaRegistrada):
        await repo.registrar("wroom", "2.0.0", URL.format("x"), "ef" * 32)


@pytest.mark.anyio
async def test_registrar_outra_versao_mantem_as_bloqueadas(db):
    db.store["firmware"] = {"wroom": registro("2.0.0", bloqueadas=["1.5.0"])}
    r = await repo.registrar("wroom", "3.0.0", URL.format("3.0.0"), "ef" * 32)
    assert r["bloqueadas"] == ["1.5.0"] and r["anterior"]["versao"] == "2.0.0"


@pytest.mark.anyio
async def test_registro_antigo_sem_o_campo_bloqueadas_continua_valido(db):
    db.store["firmware"] = {"wroom": registro("2.0.0")}                 # sem "bloqueadas"
    r = await repo.registrar("wroom", "3.0.0", URL.format("3.0.0"), "ef" * 32)
    assert r["bloqueadas"] == []


@pytest.mark.anyio
async def test_primeiro_registro_tem_lista_vazia(db):
    r = await repo.registrar("s3", "1.0.0", URL.format("1.0.0"), "ef" * 32)
    assert r["bloqueadas"] == []


# ---------- retirar ----------

@pytest.mark.anyio
async def test_retirar_volta_para_a_anterior_e_bloqueia_a_atual(db):
    db.store["firmware"] = {"wroom": registro("2.0.0", anterior=ant("1.0.0"), bloqueadas=["0.9.0"])}
    r = await repo.retirar("wroom")
    assert (r["versao"], r["url"], r["sha256"]) == ("1.0.0", URL.format("1.0.0"), "cd" * 32)
    assert r["anterior"] is None and r["notas"] is None
    assert r["bloqueadas"] == ["0.9.0", "2.0.0"]
    assert r["publicado_em"] > ANTES
    assert db.store["firmware"]["wroom"] == r                             # gravou o mesmo registro


@pytest.mark.anyio
async def test_retirar_nao_duplica_na_lista(db):
    db.store["firmware"] = {"wroom": registro("2.0.0", anterior=ant("1.0.0"), bloqueadas=["2.0.0"])}
    assert (await repo.retirar("wroom"))["bloqueadas"] == ["2.0.0"]


@pytest.mark.anyio
@pytest.mark.parametrize("doc", [
    None,                                         # sem registro
    registro("1.0.0"),                            # sem "anterior"
    registro("1.0.0", anterior=None),
    registro("1.0.0", anterior={}),
])
async def test_retirar_sem_anterior_recusa_e_nao_grava(db, doc):
    if doc is not None:
        db.store["firmware"] = {"wroom": doc}
    antes = copy.deepcopy(db.store)
    with pytest.raises(repo.SemVersaoAnterior):
        await repo.retirar("wroom")
    assert db.store == antes


@pytest.mark.anyio
async def test_sequencia_registrar_retirar_retirar_de_novo_e_tentar_a_versao_ruim(db):
    await repo.registrar("wroom", "1.0.0", URL.format("1.0.0"), "ab" * 32)
    await repo.registrar("wroom", "2.0.0", URL.format("2.0.0"), "cd" * 32)
    r = await repo.retirar("wroom")
    assert (r["versao"], r["bloqueadas"], r["anterior"]) == ("1.0.0", ["2.0.0"], None)
    with pytest.raises(repo.SemVersaoAnterior):                          # só há um nível de volta
        await repo.retirar("wroom")
    with pytest.raises(repo.VersaoBloqueada):                            # a versão ruim não volta
        await repo.registrar("wroom", "2.0.0", URL.format("2.0.0"), "cd" * 32)
    r = await repo.registrar("wroom", "2.1.0", URL.format("2.1.0"), "ef" * 32)
    assert r["anterior"]["versao"] == "1.0.0" and r["bloqueadas"] == ["2.0.0"]


@pytest.mark.anyio
async def test_cada_alvo_tem_suas_bloqueadas(db):
    db.store["firmware"] = {"wroom": registro("2.0.0", anterior=ant("1.0.0")), "s3": registro("2.0.0")}
    await repo.retirar("wroom")
    r = await repo.registrar("s3", "3.0.0", URL.format("3.0.0"), "ef" * 32)
    assert r["bloqueadas"] == []


# ---------- rotas de administração ----------

CORPO = {"versao": "3.0.0", "url": URL.format("3.0.0"), "sha256": "ab" * 32}


@pytest.fixture
def c(db, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "admin-secreta")
    monkeypatch.setattr(settings, "api_key", "chave-do-app")
    db.store["firmware"] = {"wroom": registro("2.0.0", anterior=ant("1.0.0"))}
    app = FastAPI()
    app.include_router(rota.router)
    client = TestClient(app)
    client.db = db
    return client


def retirar(c, alvo="wroom", chave="admin-secreta"):
    return c.post(f"/firmware/{alvo}/retirar", headers={"X-Admin-Key": chave} if chave is not None else {})


def test_retirar_sucesso_devolve_o_registro_e_as_bloqueadas(c):
    r = retirar(c)
    assert r.status_code == 200
    j = r.json()
    assert j["versao"] == "1.0.0" and j["bloqueadas"] == ["2.0.0"] and j["anterior"] is None
    assert j["url"] == URL.format("1.0.0") and j["sha256"] == "cd" * 32
    assert c.db.store["firmware"]["wroom"]["versao"] == "1.0.0"


def test_retirar_sem_anterior_da_409(c):
    assert retirar(c).status_code == 200
    r = retirar(c)
    assert r.status_code == 409 and "sem_versao_anterior" in r.json()["detail"]


def test_retirar_sem_registro_da_409(c):
    assert retirar(c, alvo="s3").status_code == 409


@pytest.mark.parametrize("alvo", ["esp32", "WROOM", "s3x"])
def test_retirar_alvo_invalido_da_404(c, alvo):
    assert retirar(c, alvo=alvo).status_code == 404


def test_retirar_com_chave_de_admin_vazia_esta_desligada_403(c, monkeypatch):
    monkeypatch.setattr(settings, "admin_api_key", "")
    for chave in (None, "", "qualquer", "chave-do-app"):
        assert retirar(c, chave=chave).status_code == 403
    assert c.db.store["firmware"]["wroom"]["versao"] == "2.0.0"


@pytest.mark.parametrize("chave", [None, "", "errada"])
def test_retirar_chave_errada_ou_ausente_da_401(c, chave):
    assert retirar(c, chave=chave).status_code == 401
    assert c.db.store["firmware"]["wroom"]["versao"] == "2.0.0"


def test_api_key_comum_nao_abre_a_retirada(c):
    r = c.post("/firmware/wroom/retirar", headers={"X-API-Key": "chave-do-app"})
    assert r.status_code == 401
    r = c.post("/firmware/wroom/retirar", headers={"X-Admin-Key": "chave-do-app"})
    assert r.status_code == 401


def test_retirar_erro_inesperado_vira_502_sem_vazar(c, monkeypatch):
    async def quebra(alvo):
        raise RuntimeError("segredo-interno")

    monkeypatch.setattr(rota.repositorio, "retirar", quebra)
    r = retirar(c)
    assert r.status_code == 502 and "segredo-interno" not in r.text


def test_put_de_versao_bloqueada_da_409_com_motivo_claro(c):
    assert retirar(c).status_code == 200                                  # 2.0.0 fica bloqueada
    r = c.put("/firmware/wroom", headers={"X-Admin-Key": "admin-secreta"}, json={**CORPO, "versao": "2.0.0"})
    assert r.status_code == 409 and "versao_bloqueada" in r.json()["detail"]
    r = c.put("/firmware/wroom", headers={"X-Admin-Key": "admin-secreta"}, json=CORPO)
    assert r.status_code == 200 and r.json()["bloqueadas"] == ["2.0.0"]
