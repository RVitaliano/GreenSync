"""Firestore falso em memória (coleção -> documento -> dict), com transação simulada.

Serve para exercitar a lógica REAL dos repositórios (ota/repositorio.py) sem rede.
"""
import copy
import threading
from types import SimpleNamespace


class Snap:
    def __init__(self, dados):
        self.exists = dados is not None
        self._d = copy.deepcopy(dados)      # snapshot imutável, como no Firestore real

    def to_dict(self):
        return copy.deepcopy(self._d) if self._d is not None else None


class Ref:
    def __init__(self, db, col, doc_id):
        self.db, self.col, self.id = db, col, doc_id

    def get(self, transaction=None):
        snap = Snap(self.db.store.get(self.col, {}).get(self.id))
        if transaction is not None and self.db.barreira is not None:
            # Depois de LER, espera as outras transações lerem também: força o cenário "todas viram
            # nada em curso". Se só uma entra por vez, a barreira expira e segue.
            try:
                self.db.barreira.wait(timeout=0.3)
            except threading.BrokenBarrierError:
                pass
        return snap


class Tx:
    def __init__(self, db):
        self.db = db

    def set(self, ref, dados, merge=False):
        self.db.store.setdefault(ref.col, {})[ref.id] = copy.deepcopy(dados)

    def update(self, ref, mudanca):
        doc = self.db.store[ref.col][ref.id]
        for chave, valor in mudanca.items():
            if "." in chave:
                mapa, campo = chave.split(".", 1)
                doc[mapa][campo] = valor
            else:
                doc[chave] = valor


class DbFalso:
    def __init__(self):
        self.store = {}
        self.barreira = None

    def collection(self, nome):
        return SimpleNamespace(document=lambda doc_id: Ref(self, nome, doc_id))

    def transaction(self):
        return Tx(self)

    def doc(self, col, doc_id):
        return self.store.get(col, {}).get(doc_id)


# No lugar de `repositorio.firestore`: a transação do SDK vira uma chamada direta.
FIRESTORE_FALSO = SimpleNamespace(transactional=lambda f: f)
