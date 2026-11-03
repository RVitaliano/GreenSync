"""Peças falsas compartilhadas pelos testes da rega (sem Firestore nem MQTT)."""
from datetime import datetime, timedelta, timezone


class RepoFalso:
    """Mesma interface de app/agenda/repositorio.py, só que em memória."""

    def __init__(self):
        self.docs: dict[tuple[str, str], dict] = {}
        self.eventos: list[tuple] = []     # ordem em que as coisas aconteceram
        self.falhar_ao_criar = False
        self._n = 0

    async def criar(self, device_id, quando, duracao_s, origem):
        if self.falhar_ao_criar:
            raise RuntimeError("firestore fora")
        self._n += 1
        ag_id = f"ag{self._n}"
        self.docs[(device_id, ag_id)] = {"id": ag_id, "quando": quando, "duracao_s": duracao_s,
                                         "status": "pendente", "origem": origem}
        self.eventos.append(("criar", ag_id))
        return ag_id

    async def mudar_status(self, device_id, ag_id, de, para, motivo=None):
        d = self.docs.get((device_id, ag_id))
        if d is None or d["status"] not in de:
            return False
        d["status"] = para
        if motivo:
            d["motivo"] = motivo
        self.eventos.append(("status", ag_id, para))
        return True

    async def por_status(self, device_id, status):
        return [dict(d) for (dev, _), d in self.docs.items() if dev == device_id and d["status"] == status]

    async def vizinhos(self, device_id, centro, janela_s):
        j = timedelta(seconds=janela_s)
        return [dict(d) for (dev, _), d in self.docs.items()
                if dev == device_id and centro - j < d["quando"] < centro + j]

    async def devices(self):
        return sorted({dev for dev, _ in self.docs})

    # atalhos para os testes
    def status(self, ag_id, device_id="vaso-01"):
        return self.docs[(device_id, ag_id)]["status"]

    def inserir(self, ag_id, quando, status="pendente", duracao_s=5, device_id="vaso-01"):
        self.docs[(device_id, ag_id)] = {"id": ag_id, "quando": quando, "duracao_s": duracao_s, "status": status}


def agora_utc():
    return datetime.now(timezone.utc)


LEITURA_OK = {"ph": 6.4, "umidade_solo": 20, "temperatura_ar": 24.0, "bomba_ligada": False,
              "status_vaso": "online", "updated_at": None}


def leitura_ok(**extra):
    """Leitura de um vaso online com leitura recém-chegada (sem updated_at = idade desconhecida)."""
    return {**LEITURA_OK, **extra}