"""Agendamentos no Firestore: devices/{deviceId}/agendamentos/{id} (REQ-FUNC-012).

Campos: quando (hora da rega), duracao_s, status, origem, motivo (quando falha),
criado_em, atualizado_em. Status: pendente, executando, concluida, cancelada,
expirada, falhou. "concluida" quer dizer "comando publicado": quem confirma que
a bomba girou é o firmware.

O SDK do Firestore é síncrono, então tudo roda em asyncio.to_thread.
Nenhuma consulta aqui precisa de índice composto (filtramos o resto em Python).
"""
import asyncio
from datetime import datetime, timedelta

from firebase_admin import firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from app.firebase_client import init_firebase


def _colecao(device_id: str):
    return init_firebase().collection("devices").document(device_id).collection("agendamentos")


def _como_dict(doc) -> dict:
    return {**(doc.to_dict() or {}), "id": doc.id}


# ----------------------------------------------------------------- escrita ----

def _criar_sync(device_id: str, quando: datetime, duracao_s: int, origem: str) -> str:
    ref = _colecao(device_id).document()
    ref.set({
        "quando": quando,
        "duracao_s": duracao_s,
        "status": "pendente",
        "origem": origem,
        "criado_em": firestore.SERVER_TIMESTAMP,
        "atualizado_em": firestore.SERVER_TIMESTAMP,
    })
    return ref.id


def _mudar_status_sync(device_id: str, ag_id: str, de: tuple, para: str, motivo: str | None) -> bool:
    """Troca o status SÓ SE o atual for um dos de `de` (transação).

    É isso que impede a rega duplicada: duas tentativas de "pendente -> executando"
    (ex.: duas instâncias durante um deploy) nunca passam as duas.
    """
    db = init_firebase()
    ref = _colecao(device_id).document(ag_id)

    @firestore.transactional
    def _tx(transaction) -> bool:
        snap = ref.get(transaction=transaction)
        if not snap.exists or (snap.to_dict() or {}).get("status") not in de:
            return False
        mudanca = {"status": para, "atualizado_em": firestore.SERVER_TIMESTAMP}
        if motivo:
            mudanca["motivo"] = motivo
        transaction.update(ref, mudanca)
        return True

    return _tx(db.transaction())


# ----------------------------------------------------------------- leitura ----

def _por_status_sync(device_id: str, status: str) -> list[dict]:
    return [_como_dict(d) for d in _colecao(device_id).where(filter=FieldFilter("status", "==", status)).stream()]


def _vizinhos_sync(device_id: str, centro: datetime, janela_s: int) -> list[dict]:
    """Regas com `quando` a menos de `janela_s` de `centro` (filtro de status fica com quem chama)."""
    j = timedelta(seconds=janela_s)
    docs = (_colecao(device_id)
            .where(filter=FieldFilter("quando", ">", centro - j))
            .where(filter=FieldFilter("quando", "<", centro + j))
            .stream())
    return [_como_dict(d) for d in docs]


def _devices_sync() -> list[str]:
    # list_documents também devolve documentos "virtuais" (só têm subcoleção).
    return [d.id for d in init_firebase().collection("devices").list_documents()]


async def criar(device_id: str, quando: datetime, duracao_s: int, origem: str) -> str:
    return await asyncio.to_thread(_criar_sync, device_id, quando, duracao_s, origem)


async def mudar_status(device_id: str, ag_id: str, de: tuple, para: str, motivo: str | None = None) -> bool:
    return await asyncio.to_thread(_mudar_status_sync, device_id, ag_id, de, para, motivo)


async def por_status(device_id: str, status: str) -> list[dict]:
    return await asyncio.to_thread(_por_status_sync, device_id, status)


async def vizinhos(device_id: str, centro: datetime, janela_s: int) -> list[dict]:
    return await asyncio.to_thread(_vizinhos_sync, device_id, centro, janela_s)


async def devices() -> list[str]:
    return await asyncio.to_thread(_devices_sync)