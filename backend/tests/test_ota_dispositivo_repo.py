"""devices/{id}.ota: o que conta como "em curso", reivindicar e marcar (Firestore falso)."""
from datetime import datetime, timedelta, timezone

import pytest

from app.ota import repositorio as repo
from tests.falso_firestore import FIRESTORE_FALSO, DbFalso

AGORA = datetime(2026, 11, 16, 12, 0, tzinfo=timezone.utc)


def ota(estado="solicitada", ha_s=10, **kw):
    return {"alvo": "wroom", "id": "antiga", "versao": "1.0.0", "estado": estado,
            "atualizado_em": AGORA - timedelta(seconds=ha_s), **kw}


@pytest.mark.parametrize("o,esperado", [
    (None, False),
    ({}, False),
    (ota("solicitada", 10), True),
    (ota("baixando", 599), True),
    (ota("aplicando", 100), True),
    (ota("solicitada", 600), False),             # no prazo exato já é considerada travada
    (ota("solicitada", 5000), False),            # travada
    (ota("ok", 1), False),
    (ota("falhou", 1), False),
    (ota("revertido", 1), False),
    ({"estado": "solicitada"}, False),            # sem atualizado_em: não bloqueia para sempre
    ({"estado": "solicitada", "atualizado_em": "ontem"}, False),
    (ota("solicitada", 10) | {"atualizado_em": (AGORA - timedelta(seconds=10)).replace(tzinfo=None)}, True),
])
def test_ota_em_curso(o, esperado):
    assert repo.ota_em_curso(o, AGORA, 600) is esperado


@pytest.fixture
def db(monkeypatch):
    db = DbFalso()
    monkeypatch.setattr(repo, "init_firebase", lambda: db)
    monkeypatch.setattr(repo, "firestore", FIRESTORE_FALSO)
    return db


def nova(id="nova"):
    return {"alvo": "wroom", "id": id, "versao": "2.0.0", "estado": "solicitada", "atualizado_em": AGORA}


@pytest.mark.anyio
async def test_reivindica_em_dispositivo_sem_documento(db):
    assert await repo.reivindicar_ota("vaso-01", nova(), 600) is True
    assert db.doc("devices", "vaso-01")["ota"]["id"] == "nova"


@pytest.mark.anyio
async def test_nao_reivindica_com_outra_em_curso(db):
    db.store["devices"] = {"vaso-01": {"ota": ota("baixando", 30)}}
    assert await repo.reivindicar_ota("vaso-01", nova(), 600) is False
    assert db.doc("devices", "vaso-01")["ota"]["id"] == "antiga"


@pytest.mark.anyio
async def test_reivindica_por_cima_de_uma_travada_sem_herdar_o_motivo(db):
    db.store["devices"] = {"vaso-01": {"fw": "1.0.0", "ota": ota("solicitada", 5000, motivo="velho")}}
    assert await repo.reivindicar_ota("vaso-01", nova(), 600) is True
    d = db.doc("devices", "vaso-01")
    assert d["ota"]["id"] == "nova" and "motivo" not in d["ota"]
    assert d["fw"] == "1.0.0"                      # o resto do documento fica intacto


@pytest.mark.anyio
async def test_marcar_so_mexe_na_atualizacao_certa(db):
    db.store["devices"] = {"vaso-01": {"ota": ota("solicitada", 10, id="abc")}}
    assert await repo.marcar_ota("vaso-01", "outra", "falhou", "x") is False
    assert db.doc("devices", "vaso-01")["ota"]["estado"] == "solicitada"
    assert await repo.marcar_ota("vaso-01", "abc", "falhou", "sem broker") is True
    o = db.doc("devices", "vaso-01")["ota"]
    assert (o["estado"], o["motivo"]) == ("falhou", "sem broker")
    assert isinstance(o["atualizado_em"], datetime)


@pytest.mark.anyio
async def test_marcar_sem_documento_devolve_false(db):
    assert await repo.marcar_ota("vaso-99", "abc", "falhou") is False
