"""Registro de firmware no Firestore: firmware/{alvo} (alvo = "wroom" ou "s3").

Campos: versao, url, sha256, notas, publicado_em, anterior ({versao, url, sha256} ou null).
O SDK é síncrono, então tudo roda em asyncio.to_thread (como em agenda/repositorio.py).
"""
import asyncio
from datetime import datetime, timezone

from firebase_admin import firestore

from app.firebase_client import init_firebase

COLECAO = "firmware"


class VersaoJaRegistrada(Exception):
    """A versão enviada já é a versão atual do alvo."""


def _agora() -> datetime:
    return datetime.now(timezone.utc)


def montar_registro(atual: dict | None, versao: str, url: str, sha256: str, notas: str | None,
                    agora: datetime) -> dict:
    """Regra pura: o registro atual vira "anterior" e o novo entra no lugar.

    Versão igual à atual é conflito; versão menor é permitida (voltar é permitido).
    """
    if atual and atual.get("versao") == versao:
        raise VersaoJaRegistrada(versao)
    anterior = None
    if atual and atual.get("versao"):
        anterior = {"versao": atual.get("versao"), "url": atual.get("url"), "sha256": atual.get("sha256")}
    return {"versao": versao, "url": url, "sha256": sha256, "notas": notas,
            "publicado_em": agora, "anterior": anterior}


def _ref(alvo: str):
    return init_firebase().collection(COLECAO).document(alvo)


def _ler_sync(alvo: str) -> dict | None:
    doc = _ref(alvo).get()
    return (doc.to_dict() or None) if doc.exists else None


def _registrar_sync(alvo: str, versao: str, url: str, sha256: str, notas: str | None) -> dict:
    db = init_firebase()
    ref = _ref(alvo)

    @firestore.transactional
    def _tx(transaction) -> dict:
        snap = ref.get(transaction=transaction)
        atual = snap.to_dict() if snap.exists else None
        novo = montar_registro(atual, versao, url, sha256, notas, _agora())
        transaction.set(ref, novo)
        return novo

    return _tx(db.transaction())


async def ler(alvo: str) -> dict | None:
    return await asyncio.to_thread(_ler_sync, alvo)


async def registrar(alvo: str, versao: str, url: str, sha256: str, notas: str | None = None) -> dict:
    """Grava o novo firmware (em transação). Levanta VersaoJaRegistrada se a versão já é a atual."""
    return await asyncio.to_thread(_registrar_sync, alvo, versao, url, sha256, notas)
