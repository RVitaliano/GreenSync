"""Testa o limite de perguntas sem precisar de um Redis de verdade."""
import pytest
from redis.exceptions import ConnectionError as RedisConnectionError

from app import limite, redis_client
from app.config import settings

# Roda os testes "async def" com o plugin anyio, que já vem instalado.
pytestmark = pytest.mark.anyio


class FakePipeline:
    """Imita só o que o limite usa: pipeline com incr e expire."""

    def __init__(self, redis):
        self.redis = redis
        self.comandos = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    def incr(self, chave):
        self.comandos.append(("incr", chave))
        return self

    def expire(self, chave, segundos):
        self.comandos.append(("expire", chave, segundos))
        return self

    async def execute(self):
        if self.redis.caido:
            raise RedisConnectionError("redis fora do ar")
        resultados = []
        for cmd in self.comandos:
            if cmd[0] == "incr":
                self.redis.contadores[cmd[1]] = self.redis.contadores.get(cmd[1], 0) + 1
                resultados.append(self.redis.contadores[cmd[1]])
            else:
                self.redis.expiracoes[cmd[1]] = cmd[2]
                resultados.append(True)
        return resultados


class FakeRedis:
    def __init__(self):
        self.contadores = {}
        self.expiracoes = {}
        self.caido = False

    def pipeline(self, transaction=True):
        return FakePipeline(self)


@pytest.fixture
def redis_falso(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda: r)
    monkeypatch.setattr(settings, "limite_perguntas", 3)
    monkeypatch.setattr(settings, "janela_limite_s", 60)
    monkeypatch.setattr(limite, "_agora", lambda: 300.0)  # início de uma janela
    return r


async def test_sem_redis_nao_limita():
    # conftest zera REDIS_URL, então get_redis() devolve None
    for _ in range(50):
        assert await limite.verificar_limite("chave") is None


async def test_bloqueia_depois_do_limite(redis_falso):
    for _ in range(3):
        assert await limite.verificar_limite("chave") is None
    espera = await limite.verificar_limite("chave")
    assert espera is not None and 1 <= espera <= 60


async def test_espera_e_o_tempo_ate_a_proxima_janela(redis_falso, monkeypatch):
    # 20 s depois do início de uma janela de 60 s: faltam 40 s
    monkeypatch.setattr(limite, "_agora", lambda: 320.0)
    for _ in range(3):
        await limite.verificar_limite("chave")
    assert await limite.verificar_limite("chave") == 40


async def test_cada_chave_tem_seu_contador(redis_falso):
    for _ in range(3):
        await limite.verificar_limite("chave-a")
    assert await limite.verificar_limite("chave-a") is not None
    assert await limite.verificar_limite("chave-b") is None


async def test_nova_janela_zera_o_contador(redis_falso, monkeypatch):
    for _ in range(4):
        await limite.verificar_limite("chave")
    assert await limite.verificar_limite("chave") is not None
    monkeypatch.setattr(limite, "_agora", lambda: 361.0)  # janela seguinte
    assert await limite.verificar_limite("chave") is None


async def test_chave_nao_fica_em_texto_no_redis(redis_falso):
    await limite.verificar_limite("minha-chave-secreta")
    assert redis_falso.contadores
    assert all("minha-chave-secreta" not in k for k in redis_falso.contadores)


async def test_contador_sempre_tem_prazo_de_validade(redis_falso):
    await limite.verificar_limite("chave")
    assert set(redis_falso.expiracoes) == set(redis_falso.contadores)


async def test_redis_fora_do_ar_deixa_passar(redis_falso):
    redis_falso.caido = True
    assert await limite.verificar_limite("chave") is None