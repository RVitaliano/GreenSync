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


# ------------------------------------------------- atualização de um vaso (devices/{id}.ota) ----

ESTADOS_EM_CURSO = ("solicitada", "baixando", "aplicando")


def ota_em_curso(ota: dict | None, agora: datetime, timeout_s: int) -> bool:
    """Há uma atualização andando? (solicitada/baixando/aplicando e atualizada há menos de `timeout_s`).

    Sem `atualizado_em` legível não dá para saber a idade: conta como travada (não bloqueia para sempre).
    """
    if not ota or ota.get("estado") not in ESTADOS_EM_CURSO:
        return False
    quando = ota.get("atualizado_em")
    if not isinstance(quando, datetime):
        return False
    if quando.tzinfo is None:
        quando = quando.replace(tzinfo=timezone.utc)
    return (agora - quando).total_seconds() < timeout_s


def _dispositivo(device_id: str):
    return init_firebase().collection("devices").document(device_id)


def _ler_dispositivo_sync(device_id: str) -> dict | None:
    doc = _dispositivo(device_id).get()
    return (doc.to_dict() or {}) if doc.exists else None


def _reivindicar_sync(device_id: str, ota: dict, timeout_s: int) -> bool:
    """Grava `ota` (solicitada) SÓ SE não houver outra em curso (transação)."""
    db = init_firebase()
    ref = _dispositivo(device_id)

    @firestore.transactional
    def _tx(transaction) -> bool:
        snap = ref.get(transaction=transaction)
        dados = (snap.to_dict() or {}) if snap.exists else {}
        if ota_em_curso(dados.get("ota"), ota["atualizado_em"], timeout_s):
            return False
        if snap.exists:
            transaction.update(ref, {"ota": ota})     # troca o mapa inteiro (não herda motivo antigo)
        else:
            transaction.set(ref, {"ota": ota})
        return True

    return _tx(db.transaction())


def _marcar_sync(device_id: str, ota_id: str, estado: str, motivo: str | None, agora: datetime) -> bool:
    """Muda o estado da atualização `ota_id`, mas só se ela ainda for a atual do vaso."""
    db = init_firebase()
    ref = _dispositivo(device_id)

    @firestore.transactional
    def _tx(transaction) -> bool:
        snap = ref.get(transaction=transaction)
        atual = ((snap.to_dict() or {}).get("ota") or {}) if snap.exists else {}
        if atual.get("id") != ota_id:
            return False
        mudanca = {"ota.estado": estado, "ota.atualizado_em": agora}
        if motivo:
            mudanca["ota.motivo"] = motivo
        transaction.update(ref, mudanca)
        return True

    return _tx(db.transaction())


async def ler_dispositivo(device_id: str) -> dict | None:
    return await asyncio.to_thread(_ler_dispositivo_sync, device_id)


async def reivindicar_ota(device_id: str, ota: dict, timeout_s: int) -> bool:
    return await asyncio.to_thread(_reivindicar_sync, device_id, ota, timeout_s)


async def marcar_ota(device_id: str, ota_id: str, estado: str, motivo: str | None = None) -> bool:
    return await asyncio.to_thread(_marcar_sync, device_id, ota_id, estado, motivo, _agora())
