"""Testa retry, timeout e modelo reserva (o que antes só dava para ver na mão)."""
import asyncio

import pytest
from google.genai import errors

from app.ai import resiliencia
from app.ai.resiliencia import IAError, tentar_modelos

pytestmark = pytest.mark.anyio


@pytest.fixture(autouse=True)
def sem_espera(monkeypatch):
    monkeypatch.setattr(resiliencia, "ESPERA_ENTRE_TENTATIVAS_S", 0)


def erro_503():
    return errors.ServerError(503, {"error": {"message": "high demand"}})


def erro_404():
    return errors.ClientError(404, {"error": {"message": "modelo não existe"}})


def roteiro(**por_modelo):
    """Monta `chamar(modelo)` que segue um roteiro: cada item é um valor ou uma exceção."""
    chamadas = []
    filas = {m: list(itens) for m, itens in por_modelo.items()}

    async def chamar(modelo):
        chamadas.append(modelo)
        item = filas[modelo].pop(0)
        if isinstance(item, BaseException):
            raise item
        if callable(item):
            return await item()
        return item

    return chamar, chamadas


async def test_primeiro_modelo_responde():
    chamar, chamadas = roteiro(a=["ok"], b=["nunca"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert (valor, modelo) == ("ok", "a")
    assert chamadas == ["a"]


async def test_503_tenta_de_novo_no_mesmo_modelo():
    chamar, chamadas = roteiro(a=[erro_503(), "ok"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert (valor, modelo) == ("ok", "a")
    assert chamadas == ["a", "a"]


async def test_dois_503_vai_para_o_reserva():
    chamar, chamadas = roteiro(a=[erro_503(), erro_503()], b=["ok"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert (valor, modelo) == ("ok", "b")
    assert chamadas == ["a", "a", "b"]


async def test_timeout_vai_direto_para_o_reserva_sem_repetir():
    async def lento():
        await asyncio.sleep(1)

    chamar, chamadas = roteiro(a=[lento], b=["ok"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 0.01)
    assert (valor, modelo) == ("ok", "b")
    assert chamadas == ["a", "b"]


async def test_erro_4xx_vai_direto_para_o_reserva_sem_repetir():
    chamar, chamadas = roteiro(a=[erro_404()], b=["ok"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert (valor, modelo) == ("ok", "b")
    assert chamadas == ["a", "b"]


async def test_resposta_vazia_vai_para_o_reserva():
    chamar, chamadas = roteiro(a=[""], b=["ok"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert (valor, modelo) == ("ok", "b")


async def test_erro_inesperado_vai_para_o_reserva():
    chamar, _ = roteiro(a=[RuntimeError("bug")], b=["ok"])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert modelo == "b"


async def test_todos_falham_levanta_iaerror_com_o_ultimo_motivo():
    chamar, _ = roteiro(a=[erro_503(), erro_503()], b=[erro_404()])
    with pytest.raises(IAError) as e:
        await tentar_modelos(["a", "b"], chamar, lambda r: r, 1)
    assert "b:" in str(e.value)


async def test_extrair_decide_o_que_conta_como_vazio():
    chamar, _ = roteiro(a=[{"x": b""}], b=[{"x": b"audio"}])
    valor, modelo = await tentar_modelos(["a", "b"], chamar, lambda r: r["x"], 1)
    assert (valor, modelo) == (b"audio", "b")