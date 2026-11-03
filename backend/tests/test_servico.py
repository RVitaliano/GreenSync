"""tratar_acao: do pedido do LLM até a frase falada (Firestore e MQTT falsos)."""
import asyncio
import pytest

from app.agenda import servico
from app.agenda.agendador import Agendador
from app.ai.estado import avaliar_estado
from app.config import settings
from tests.falsos import RepoFalso, leitura_ok

pytestmark = pytest.mark.anyio


class Montagem:
    def __init__(self):
        self.repo = RepoFalso()
        self.publicados = []
        self.leitura = leitura_ok()
        self.ag = Agendador(self.repo, self.publicar, self.ler_leitura)

    async def publicar(self, device_id, payload):
        self.repo.eventos.append(("publicar", payload["id"]))
        self.publicados.append((device_id, payload))

    async def ler_leitura(self, device_id):
        return self.leitura

    async def tratar(self, acao, fala_usuario="Rega a planta", leitura=None, device_id="vaso-01"):
        leitura = self.leitura if leitura is None else leitura
        return await servico.tratar_acao(acao, fala_usuario, device_id, leitura,
                                         avaliar_estado(leitura), "voz")


@pytest.fixture
def m(monkeypatch):
    m = Montagem()
    monkeypatch.setattr(servico, "agendador", m.ag)
    return m


def regar(**kw):
    return {"tipo": "regar", "daqui_a_s": None, "as_hora": None, "duracao_s": None, **kw}


# ---------- sem pedido ----------

@pytest.mark.parametrize("acao", [None, {}, {"tipo": "nenhuma"}, {"tipo": "ligar_bomba"}])
async def test_sem_pedido_devolve_none(m, acao):
    assert await m.tratar(acao) is None
    assert m.repo.docs == {}


# ---------- trava de segurança ----------

async def test_modelo_inventou_a_rega_a_bomba_nao_liga(m):
    r = await m.tratar(regar(), fala_usuario="Qual a temperatura?")
    assert r["resultado"] == "ignorada"
    assert m.repo.docs == {} and m.publicados == []


async def test_fala_vazia_nao_aciona(m):
    assert (await m.tratar(regar(), fala_usuario=""))["resultado"] == "ignorada"


# ---------- rega aceita ----------

async def test_rega_agora_publica_e_confirma(m):
    r = await m.tratar(regar(daqui_a_s=0))
    assert r["resultado"] == "agendada"
    assert r["fala"] == "Pode deixar, vou me regar agora por 5 segundos."
    assert m.publicados == [("vaso-01", {"acao": "regar", "duracao_s": 5, "id": r["id"]})]
    assert m.repo.status(r["id"]) == "concluida"


async def test_rega_agora_com_duracao_pedida(m):
    r = await m.tratar(regar(duracao_s=8))
    assert "por 8 segundos" in r["fala"]
    assert m.publicados[0][1]["duracao_s"] == 8


async def test_rega_futura_so_agenda(m):
    r = await m.tratar(regar(daqui_a_s=600))
    assert r["resultado"] == "agendada"
    assert r["fala"] == "Combinado, vou regar daqui a 10 minutos por 5 segundos."
    assert m.publicados == []                       # ainda não é a hora
    assert m.repo.status(r["id"]) == "pendente"
    assert m.repo.docs[("vaso-01", r["id"])]["origem"] == "voz"
    await m.ag.parar()


async def test_rega_com_hora_do_relogio(m):
    r = await m.tratar(regar(as_hora="23:59"))
    assert r["resultado"] == "agendada"
    assert r["fala"].startswith("Combinado, vou regar ")
    await m.ag.parar()


# ---------- rega recusada ----------

async def test_vaso_offline_recusa_e_nao_grava(m):
    r = await m.tratar(regar(), leitura=leitura_ok(status_vaso="offline"))
    assert r["resultado"] == "recusada" and r["motivo"] == "offline"
    assert "desconectado" in r["fala"]
    assert m.repo.docs == {} and m.publicados == []


async def test_sem_leitura_recusa(m):
    r = await servico.tratar_acao(regar(), "Rega", "vaso-01", None, avaliar_estado(None), "voz")
    assert r["resultado"] == "recusada" and r["motivo"] == "sem_dados"


async def test_duracao_acima_do_limite_recusa(m):
    r = await m.tratar(regar(duracao_s=settings.rega_duracao_max_s + 1))
    assert r["motivo"] == "duracao_grande" and m.repo.docs == {}


async def test_atraso_acima_do_limite_recusa(m):
    r = await m.tratar(regar(daqui_a_s=settings.rega_atraso_max_s + 60))
    assert r["motivo"] == "atraso_grande" and m.repo.docs == {}


async def test_solo_encharcado_recusa_rega_de_agora(m):
    r = await m.tratar(regar(), leitura=leitura_ok(umidade_solo=90))
    assert r["motivo"] == "solo_encharcado"


async def test_segunda_rega_colada_na_primeira_e_recusada(m):
    primeira = await m.tratar(regar(daqui_a_s=600))
    segunda = await m.tratar(regar(daqui_a_s=700))
    assert primeira["resultado"] == "agendada"
    assert segunda["resultado"] == "recusada" and segunda["motivo"] == "intervalo"
    assert len(m.repo.docs) == 1
    await m.ag.parar()


async def test_pedidos_simultaneos_so_um_passa(m):
    # Dois "regar agora" ao mesmo tempo (ex.: pergunta repetida): a trava garante um só.
    a, b = await asyncio.gather(m.tratar(regar()), m.tratar(regar()))
    assert sorted([a["resultado"], b["resultado"]]) == ["agendada", "recusada"]
    assert len(m.publicados) == 1


async def test_rega_longe_da_outra_passa(m):
    await m.tratar(regar(daqui_a_s=600))
    r = await m.tratar(regar(daqui_a_s=600 + settings.rega_intervalo_min_s + 60))
    assert r["resultado"] == "agendada"
    await m.ag.parar()


# ---------- falha na hora ----------

async def test_rega_agora_que_falha_na_hora_nao_promete(m):
    # A leitura usada na validação estava online, mas na hora de regar o vaso caiu.
    chamadas = {"n": 0}

    async def leitura_que_muda(device_id):
        chamadas["n"] += 1
        return leitura_ok(status_vaso="offline")

    m.ag.ler_leitura = leitura_que_muda
    r = await m.tratar(regar())
    assert r["resultado"] == "falhou"
    assert r["fala"] == "Tentei me regar, mas não consegui: o vaso está desconectado."
    assert m.publicados == []


async def test_firestore_fora_vira_frase_e_nao_excecao(m):
    m.repo.falhar_ao_criar = True
    r = await m.tratar(regar())
    assert r["resultado"] == "erro"
    assert "Não consegui marcar a rega" in r["fala"]


# ---------- cancelar ----------

async def test_cancelar_a_rega_marcada(m):
    marcada = await m.tratar(regar(daqui_a_s=7200))
    r = await m.tratar({"tipo": "cancelar", "daqui_a_s": None, "as_hora": None, "duracao_s": None},
                       fala_usuario="Cancela a rega")
    assert r["resultado"] == "cancelada" and r["id"] == marcada["id"]
    assert r["fala"].startswith("Pronto, cancelei a rega das ")
    assert m.repo.status(marcada["id"]) == "cancelada"


async def test_cancelar_sem_nada_marcado(m):
    r = await m.tratar({"tipo": "cancelar", "daqui_a_s": None, "as_hora": None, "duracao_s": None},
                       fala_usuario="Cancela a rega")
    assert r["resultado"] == "nada_a_cancelar"
    assert r["fala"] == "Não tem nenhuma rega marcada para cancelar."


async def test_cancelar_nao_exige_palavra_de_rega(m):
    # Cancelar é seguro: não precisa da trava (a pessoa pode dizer "esquece isso").
    r = await m.tratar({"tipo": "cancelar", "daqui_a_s": None, "as_hora": None, "duracao_s": None},
                       fala_usuario="esquece isso")
    assert r["resultado"] == "nada_a_cancelar"