"""Agendador: horário certo, uma vez só, cancelamento e recarga ao reiniciar."""
import asyncio
from datetime import timedelta

import pytest

from app.agenda.agendador import Agendador
from app.agenda.regras import Pedido
from app.config import settings
from tests.falsos import RepoFalso, agora_utc, leitura_ok

pytestmark = pytest.mark.anyio


class Montagem:
    """Agendador com repositório, MQTT e leitura falsos."""

    def __init__(self):
        self.repo = RepoFalso()
        self.publicados = []
        self.leitura = leitura_ok()
        self.mqtt_cai = False
        self.ag = Agendador(self.repo, self.publicar, self.ler_leitura)

    async def publicar(self, device_id, payload):
        if self.mqtt_cai:
            raise ConnectionError("broker fora")
        self.repo.eventos.append(("publicar", payload["id"]))
        self.publicados.append((device_id, payload))

    async def ler_leitura(self, device_id):
        return self.leitura


@pytest.fixture
def m():
    return Montagem()


def pedido(atraso_s=0.0, duracao_s=5):
    return Pedido(quando=agora_utc() + timedelta(seconds=atraso_s), duracao_s=duracao_s, atraso_s=int(atraso_s))


async def rodar(m, atraso_s=0.0, **kw):
    """Agenda e espera terminar. Devolve (id, (status, motivo))."""
    ag_id = await m.ag.agendar("vaso-01", pedido(atraso_s, **kw), "voz")
    return ag_id, await m.ag.aguardar("vaso-01", ag_id, timeout_s=3)


# ---------- execução ----------

async def test_rega_de_agora_publica_o_comando(m):
    ag_id, final = await rodar(m)
    assert final == ("concluida", None)
    assert m.publicados == [("vaso-01", {"acao": "regar", "duracao_s": 5, "id": ag_id})]
    assert m.repo.status(ag_id) == "concluida"


async def test_so_dispara_na_hora_marcada(m):
    ag_id = await m.ag.agendar("vaso-01", pedido(0.3), "voz")
    await asyncio.sleep(0.1)
    assert m.publicados == []                       # ainda não é a hora
    assert m.repo.status(ag_id) == "pendente"
    assert await m.ag.aguardar("vaso-01", ag_id, timeout_s=3) == ("concluida", None)
    assert len(m.publicados) == 1


async def test_executando_e_gravado_antes_de_publicar(m):
    ag_id, _ = await rodar(m)
    ev = m.repo.eventos
    assert ev.index(("status", ag_id, "executando")) < ev.index(("publicar", ag_id))
    assert ev.index(("publicar", ag_id)) < ev.index(("status", ag_id, "concluida"))


async def test_nunca_executa_duas_vezes(m):
    ag_id = await m.ag.agendar("vaso-01", pedido(5), "voz")       # tarefa dormindo
    # duas tentativas disputando a mesma rega (ex.: duas instâncias durante um deploy)
    r = await asyncio.gather(m.ag._disparar("vaso-01", ag_id, 5), m.ag._disparar("vaso-01", ag_id, 5))
    assert sorted(x[0] for x in r) == ["concluida", "ignorada"]
    assert len(m.publicados) == 1
    await m.ag.parar()


# ---------- conferências na hora de regar ----------

async def test_vaso_offline_na_hora_nao_publica(m):
    m.leitura = leitura_ok(status_vaso="offline")
    ag_id, final = await rodar(m)
    assert final == ("falhou", "o vaso está desconectado")
    assert m.publicados == [] and m.repo.status(ag_id) == "falhou"
    assert m.repo.docs[("vaso-01", ag_id)]["motivo"] == "o vaso está desconectado"


async def test_sem_leitura_na_hora_nao_publica(m):
    m.leitura = None
    _, final = await rodar(m)
    assert final[0] == "falhou" and m.publicados == []


async def test_solo_encharcado_na_hora_nao_publica(m):
    m.leitura = leitura_ok(umidade_solo=90)
    _, final = await rodar(m)
    assert final == ("falhou", "o solo já está encharcado")
    assert m.publicados == []


async def test_broker_fora_marca_falhou(m):
    m.mqtt_cai = True
    ag_id, final = await rodar(m)
    assert final == ("falhou", "não consegui falar com o broker")
    assert m.repo.status(ag_id) == "falhou"


async def test_erro_inesperado_nao_derruba_a_tarefa(m):
    async def quebra(device_id):
        raise RuntimeError("firestore caiu")

    m.ag.ler_leitura = quebra
    _, final = await rodar(m)
    assert final == ("falhou", "erro interno")


# ---------- cancelamento ----------

async def test_cancelar_antes_da_hora_nao_publica(m):
    ag_id = await m.ag.agendar("vaso-01", pedido(0.3), "voz")
    achou = await m.ag.cancelar_proxima("vaso-01")
    assert achou[0]["id"] == ag_id and achou[1] == 0
    await asyncio.sleep(0.5)
    assert m.publicados == [] and m.repo.status(ag_id) == "cancelada"


async def test_cancelar_escolhe_a_mais_proxima_e_conta_as_restantes(m):
    longe = await m.ag.agendar("vaso-01", pedido(900), "voz")
    perto = await m.ag.agendar("vaso-01", pedido(300), "voz")
    achou = await m.ag.cancelar_proxima("vaso-01")
    assert achou[0]["id"] == perto and achou[1] == 1
    assert m.repo.status(longe) == "pendente"
    await m.ag.parar()


async def test_cancelar_sem_nada_pendente(m):
    assert await m.ag.cancelar_proxima("vaso-01") is None


async def test_nao_cancela_rega_que_ja_esta_executando(m):
    ag_id = await m.ag.agendar("vaso-01", pedido(900), "voz")
    m.repo.docs[("vaso-01", ag_id)]["status"] = "executando"
    assert await m.ag.cancelar_proxima("vaso-01") is None
    await m.ag.parar()


async def test_cancelar_so_mexe_no_proprio_vaso(m):
    await m.ag.agendar("vaso-02", pedido(900), "voz")
    assert await m.ag.cancelar_proxima("vaso-01") is None
    await m.ag.parar()


# ---------- reinício (REQ-FUNC-012) ----------

async def test_reinicio_executa_uma_vez_a_rega_dentro_da_tolerancia(m):
    atrasada = agora_utc() - timedelta(seconds=settings.rega_tolerancia_s - 60)
    m.repo.inserir("ag-velha", atrasada)
    await m.ag.iniciar()
    assert await m.ag.aguardar("vaso-01", "ag-velha", timeout_s=3) == ("concluida", None)
    assert len(m.publicados) == 1
    # reiniciar de novo não repete: já não está pendente
    await m.ag.iniciar()
    await asyncio.sleep(0.1)
    assert len(m.publicados) == 1


async def test_reinicio_expira_a_rega_fora_da_tolerancia(m):
    m.repo.inserir("ag-muito-velha", agora_utc() - timedelta(seconds=settings.rega_tolerancia_s + 60))
    await m.ag.iniciar()
    await asyncio.sleep(0.2)
    assert m.repo.status("ag-muito-velha") == "expirada"
    assert m.publicados == []


async def test_reinicio_mantem_o_que_ainda_e_futuro(m):
    m.repo.inserir("ag-futura", agora_utc() + timedelta(hours=1))
    await m.ag.iniciar()
    await asyncio.sleep(0.1)
    assert m.repo.status("ag-futura") == "pendente" and m.publicados == []
    await m.ag.parar()


async def test_reinicio_nao_repete_o_que_ficou_executando(m):
    # O backend caiu depois de marcar "executando": não sabemos se o comando saiu. Não repete.
    m.repo.inserir("ag-meio", agora_utc() - timedelta(seconds=20), status="executando")
    await m.ag.iniciar()
    await asyncio.sleep(0.1)
    assert m.repo.status("ag-meio") == "falhou"
    assert m.publicados == []


async def test_parar_mantem_pendente_para_a_proxima_subida(m):
    ag_id = await m.ag.agendar("vaso-01", pedido(900), "voz")
    await m.ag.parar()
    assert m.repo.status(ag_id) == "pendente"
    assert m.publicados == []


async def test_aguardar_devolve_none_se_demora_demais(m):
    ag_id = await m.ag.agendar("vaso-01", pedido(900), "voz")
    assert await m.ag.aguardar("vaso-01", ag_id, timeout_s=0.1) is None
    await m.ag.parar()

# ---------- erros no meio do caminho (rega nunca fica presa em "executando") ----------

async def test_erro_depois_de_reivindicar_nao_deixa_a_rega_presa_em_executando(m):
    async def quebra(device_id):
        raise RuntimeError("firestore caiu")

    m.ag.ler_leitura = quebra
    ag_id, final = await rodar(m)
    assert final == ("falhou", "erro interno")
    assert m.repo.status(ag_id) == "falhou"          # antes ficava "executando" até o próximo reinício
    assert m.publicados == []


async def test_erro_ao_marcar_falhou_nao_derruba_a_tarefa(m):
    async def quebra(device_id):
        raise RuntimeError("firestore caiu")

    original = m.repo.mudar_status

    async def mudar_quebrado(device_id, ag_id, de, para, motivo=None):
        if para == "falhou":
            raise RuntimeError("firestore continua fora")
        return await original(device_id, ag_id, de, para, motivo)

    m.ag.ler_leitura = quebra
    m.repo.mudar_status = mudar_quebrado
    _, final = await rodar(m)
    assert final == ("falhou", "erro interno")


@pytest.mark.parametrize("duracao", [0, -5, 11, 9999, None, "5", 5.5, True])
async def test_duracao_invalida_vinda_do_firestore_nunca_vira_comando(m, duracao):
    # settings.rega_duracao_max_s = 10 (padrão). O documento pode ter sido mexido fora do backend.
    ag_id = await m.ag.agendar("vaso-01", pedido(900), "voz")
    r = await m.ag._disparar("vaso-01", ag_id, duracao)
    assert r == ("falhou", "a duração da rega é inválida")
    assert m.publicados == []
    assert m.repo.status(ag_id) == "falhou"
    await m.ag.parar()


async def test_duracao_no_limite_ainda_publica(m):
    ag_id, final = await rodar(m, duracao_s=settings.rega_duracao_max_s)
    assert final == ("concluida", None)
    assert m.publicados[0][1]["duracao_s"] == settings.rega_duracao_max_s


# ---------- reinício com dados ruins ----------

async def test_reinicio_um_documento_ruim_nao_impede_os_outros(m):
    m.repo.docs[("vaso-01", "ag-sem-quando")] = {"id": "ag-sem-quando", "duracao_s": 5, "status": "pendente"}
    m.repo.inserir("ag-boa", agora_utc() + timedelta(hours=1))
    await m.ag.iniciar()
    assert "vaso-01/ag-boa" in m.ag._tarefas        # antes: KeyError abortava o iniciar() inteiro
    assert "vaso-01/ag-sem-quando" not in m.ag._tarefas
    await m.ag.parar()


async def test_reinicio_um_vaso_com_erro_nao_impede_os_outros(m):
    m.repo.inserir("ag-b", agora_utc() + timedelta(hours=1), device_id="vaso-02")
    m.repo.inserir("ag-a", agora_utc() + timedelta(hours=1), device_id="vaso-01")
    original = m.repo.por_status

    async def por_status_quebrado(device_id, status):
        if device_id == "vaso-01":
            raise RuntimeError("firestore falhou neste vaso")
        return await original(device_id, status)

    m.repo.por_status = por_status_quebrado
    await m.ag.iniciar()
    assert "vaso-02/ag-b" in m.ag._tarefas
    await m.ag.parar()
