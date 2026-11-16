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


# ------------------------------------------------- progresso informado pelo vaso ----

# solicitada < baixando < aplicando < (ok | falhou | revertido). Os finais são terminais.
ORDEM_ESTADOS = {"solicitada": 0, "baixando": 1, "aplicando": 2, "ok": 3, "falhou": 3, "revertido": 3}
ESTADOS_FINAIS = ("ok", "falhou", "revertido")


def decidir_progresso(ota: dict | None, ota_id: str, alvo: str, estado: str) -> str:
    """Regra pura. Devolve "aplicar" ou o motivo de ignorar o progresso.

    Motivos: sem_ota, id_diferente, alvo_diferente, estado_desconhecido, terminal, regressao.
    Mesmo estado repetido (QoS 1 pode duplicar) é aceito; pular etapas para frente também.
    """
    if not ota:
        return "sem_ota"
    if ota.get("id") != ota_id:
        return "id_diferente"
    if ota.get("alvo") != alvo:
        return "alvo_diferente"
    atual = ota.get("estado")
    if atual not in ORDEM_ESTADOS or estado not in ORDEM_ESTADOS:
        return "estado_desconhecido"
    if atual in ESTADOS_FINAIS:
        return "terminal"                  # depois de um estado final nada muda
    if ORDEM_ESTADOS[estado] < ORDEM_ESTADOS[atual]:
        return "regressao"
    return "aplicar"


def _progresso_sync(device_id: str, ota_id: str, alvo: str, estado: str, motivo: str | None,
                    agora: datetime) -> str:
    """Lê e grava na MESMA transação: conferir o id/ordem e escrever não podem se separar."""
    db = init_firebase()
    ref = _dispositivo(device_id)

    @firestore.transactional
    def _tx(transaction) -> str:
        snap = ref.get(transaction=transaction)
        ota = ((snap.to_dict() or {}).get("ota")) if snap.exists else None
        decisao = decidir_progresso(ota, ota_id, alvo, estado)
        if decisao != "aplicar":
            return decisao
        mudanca = {"ota.estado": estado, "ota.atualizado_em": agora}
        if motivo:
            mudanca["ota.motivo"] = motivo
        transaction.update(ref, mudanca)
        return "aplicar"

    return _tx(db.transaction())


async def aplicar_progresso(device_id: str, ota_id: str, alvo: str, estado: str,
                            motivo: str | None = None) -> str:
    """Reflete o progresso do vaso em devices/{id}.ota. Devolve "aplicar" ou o motivo de ter ignorado."""
    return await asyncio.to_thread(_progresso_sync, device_id, ota_id, alvo, estado, motivo, _agora())
