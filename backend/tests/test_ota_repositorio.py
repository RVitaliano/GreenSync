"""Registro de firmware: regras de troca de versão (Firestore falso, transação simulada)."""
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.ota import repositorio as repo

pytestmark = pytest.mark.anyio

URL1, URL2 = "https://github.com/o/r/v1.bin", "https://github.com/o/r/v2.bin"
H1, H2 = "1" * 64, "2" * 64


class Snap:
    def __init__(self, dados):
        self.exists = dados is not None
        self._d = dados

    def to_dict(self):
        return dict(self._d) if self._d is not None else None


class Ref:
    def __init__(self, store, chave):
        self.store, self.chave = store, chave

    def get(self, transaction=None):
        return Snap(self.store.get(self.chave))


class Tx:
    def set(self, ref, dados):
        ref.store[ref.chave] = dados


class DbFalso:
    def __init__(self):
        self.store = {}

    def collection(self, nome):
        assert nome == "firmware"
        return SimpleNamespace(document=lambda alvo: Ref(self.store, alvo))

    def transaction(self):
        return Tx()


@pytest.fixture
def db(monkeypatch):
    db = DbFalso()
    monkeypatch.setattr(repo, "init_firebase", lambda: db)
    # troca só a transação real do SDK por uma que roda a função direto
    monkeypatch.setattr(repo, "firestore", SimpleNamespace(transactional=lambda f: f))
    return db


async def test_primeiro_registro_nao_tem_anterior(db):
    r = await repo.registrar("wroom", "1.0.0", URL1, H1, "primeira")
    assert r["versao"] == "1.0.0" and r["anterior"] is None and r["notas"] == "primeira"
    assert isinstance(r["publicado_em"], datetime) and r["publicado_em"].tzinfo == timezone.utc
    assert db.store["wroom"] == r
    assert await repo.ler("wroom") == r


async def test_novo_registro_move_o_atual_para_anterior(db):
    await repo.registrar("wroom", "1.0.0", URL1, H1, "a")
    r = await repo.registrar("wroom", "1.1.0", URL2, H2, None)
    assert r["anterior"] == {"versao": "1.0.0", "url": URL1, "sha256": H1}
    assert r["versao"] == "1.1.0" and r["notas"] is None
    assert db.store["wroom"]["versao"] == "1.1.0"


async def test_versao_igual_a_atual_e_conflito_e_nao_grava(db):
    await repo.registrar("wroom", "1.0.0", URL1, H1)
    antes = dict(db.store["wroom"])
    with pytest.raises(repo.VersaoJaRegistrada):
        await repo.registrar("wroom", "1.0.0", URL2, H2)
    assert db.store["wroom"] == antes


async def test_versao_menor_e_aceita_voltar_e_permitido(db):
    await repo.registrar("wroom", "2.0.0", URL2, H2)
    r = await repo.registrar("wroom", "1.0.0", URL1, H1)
    assert r["versao"] == "1.0.0" and r["anterior"]["versao"] == "2.0.0"


async def test_versao_igual_a_anterior_nao_e_conflito(db):
    await repo.registrar("wroom", "1.0.0", URL1, H1)
    await repo.registrar("wroom", "1.1.0", URL2, H2)
    r = await repo.registrar("wroom", "1.0.0", URL1, H1)      # só a ATUAL conta para o conflito
    assert r["anterior"]["versao"] == "1.1.0"


async def test_cada_alvo_tem_seu_proprio_registro(db):
    await repo.registrar("wroom", "1.0.0", URL1, H1)
    r = await repo.registrar("s3", "1.0.0", URL1, H1)          # mesma versão, outro alvo: sem conflito
    assert r["anterior"] is None and set(db.store) == {"wroom", "s3"}


async def test_ler_sem_registro_devolve_none(db):
    assert await repo.ler("s3") is None
