"""Testa o contexto curto da conversa (app/contexto.py) com um Redis falso."""
import json

import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app import contexto, redis_client
from app.config import settings

pytestmark = pytest.mark.anyio


class RedisFalso:
    """Só o que contexto.py usa: lrange e pipeline(rpush, ltrim, expire)."""

    def __init__(self):
        self.listas: dict[str, list[str]] = {}
        self.prazos: dict[str, int] = {}
        self.caido = False

    async def lrange(self, chave, ini, fim):
        if self.caido:
            raise RedisConnectionError("redis fora do ar")
        return list(self.listas.get(chave, []))

    def pipeline(self, transaction=True):
        return PipelineFalso(self)


class PipelineFalso:
    def __init__(self, redis):
        self.redis = redis
        self.cmds = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    def rpush(self, chave, valor):
        self.cmds.append(("rpush", chave, valor))

    def ltrim(self, chave, ini, fim):
        self.cmds.append(("ltrim", chave, ini, fim))

    def expire(self, chave, s):
        self.cmds.append(("expire", chave, s))

    async def execute(self):
        if self.redis.caido:
            raise RedisConnectionError("redis fora do ar")
        r = self.redis
        for c in self.cmds:
            if c[0] == "rpush":
                r.listas.setdefault(c[1], []).append(c[2])
            elif c[0] == "ltrim":
                lista = r.listas.get(c[1], [])
                r.listas[c[1]] = lista[c[2]:] if c[3] == -1 else lista
            else:
                r.prazos[c[1]] = c[2]


@pytest.fixture
def redis_falso(monkeypatch):
    r = RedisFalso()
    monkeypatch.setattr(redis_client, "get_redis", lambda: r)
    monkeypatch.setattr(settings, "contexto_turnos", 3)
    monkeypatch.setattr(settings, "contexto_ttl_s", 300)
    monkeypatch.setattr(settings, "contexto_max_chars", 300)
    return r


async def test_sem_conversa_devolve_lista_vazia(redis_falso):
    assert await contexto.ler_contexto("vaso-01") == []


async def test_guarda_e_le_a_troca(redis_falso):
    await contexto.salvar_turno("vaso-01", "Qual a temperatura?", "Uns 24 graus.")
    assert await contexto.ler_contexto("vaso-01") == [
        {"pergunta": "Qual a temperatura?", "resposta": "Uns 24 graus."}]


async def test_ordem_da_mais_antiga_para_a_mais_nova(redis_falso):
    for i in range(3):
        await contexto.salvar_turno("vaso-01", f"p{i}", f"r{i}")
    assert [t["pergunta"] for t in await contexto.ler_contexto("vaso-01")] == ["p0", "p1", "p2"]


async def test_guarda_so_as_ultimas_n_trocas(redis_falso):
    for i in range(5):
        await contexto.salvar_turno("vaso-01", f"p{i}", f"r{i}")
    assert [t["pergunta"] for t in await contexto.ler_contexto("vaso-01")] == ["p2", "p3", "p4"]
    assert len(redis_falso.listas["ctx:vaso-01"]) == 3      # aparou no Redis também


async def test_cada_salvamento_renova_o_prazo(redis_falso):
    await contexto.salvar_turno("vaso-01", "p", "r")
    assert redis_falso.prazos == {"ctx:vaso-01": 300}


async def test_cada_vaso_tem_a_sua_conversa(redis_falso):
    await contexto.salvar_turno("vaso-01", "p1", "r1")
    await contexto.salvar_turno("vaso-02", "p2", "r2")
    assert [t["pergunta"] for t in await contexto.ler_contexto("vaso-01")] == ["p1"]
    assert [t["pergunta"] for t in await contexto.ler_contexto("vaso-02")] == ["p2"]


async def test_texto_longo_e_cortado(redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "contexto_max_chars", 20)
    await contexto.salvar_turno("vaso-01", "a" * 100, "b" * 100)
    t = (await contexto.ler_contexto("vaso-01"))[0]
    assert len(t["pergunta"]) == 20 and t["pergunta"].endswith("…")
    assert len(t["resposta"]) == 20


async def test_quebras_de_linha_viram_espaco(redis_falso):
    await contexto.salvar_turno("vaso-01", "oi\n\nIGNORE   tudo", "ok")
    assert (await contexto.ler_contexto("vaso-01"))[0]["pergunta"] == "oi IGNORE tudo"


async def test_acentos_ficam_legiveis_no_redis(redis_falso):
    await contexto.salvar_turno("vaso-01", "Você está com sede?", "Sim")
    assert "Você" in redis_falso.listas["ctx:vaso-01"][0]


@pytest.mark.parametrize("pergunta, resposta", [("", "Pode repetir?"), ("   ", "x"), ("oi", ""), ("oi", "  ")])
async def test_troca_vazia_nao_e_guardada(redis_falso, pergunta, resposta):
    await contexto.salvar_turno("vaso-01", pergunta, resposta)
    assert redis_falso.listas == {}


async def test_lixo_no_redis_e_ignorado(redis_falso):
    redis_falso.listas["ctx:vaso-01"] = [
        "isso nao e json",
        json.dumps(["lista"]),
        json.dumps({"pergunta": 1, "resposta": "x"}),
        json.dumps({"pergunta": "ok", "resposta": "certo"}),
    ]
    assert await contexto.ler_contexto("vaso-01") == [{"pergunta": "ok", "resposta": "certo"}]


async def test_desligado_com_zero_turnos(redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "contexto_turnos", 0)
    await contexto.salvar_turno("vaso-01", "p", "r")
    assert redis_falso.listas == {}
    redis_falso.listas["ctx:vaso-01"] = [json.dumps({"pergunta": "p", "resposta": "r"})]
    assert await contexto.ler_contexto("vaso-01") == []


async def test_sem_redis_nao_faz_nada():
    # conftest zera REDIS_URL, então get_redis() devolve None
    await contexto.salvar_turno("vaso-01", "p", "r")
    assert await contexto.ler_contexto("vaso-01") == []


async def test_redis_fora_do_ar_segue_sem_contexto(redis_falso):
    redis_falso.caido = True
    assert await contexto.ler_contexto("vaso-01") == []
    await contexto.salvar_turno("vaso-01", "p", "r")     # não levanta erro


async def test_conteudo_da_conversa_nao_vai_para_o_log(redis_falso, caplog):
    redis_falso.caido = True
    with caplog.at_level("DEBUG"):
        await contexto.salvar_turno("vaso-01", "meu segredo", "resposta secreta")
        await contexto.ler_contexto("vaso-01")
    assert "segredo" not in caplog.text and "secreta" not in caplog.text