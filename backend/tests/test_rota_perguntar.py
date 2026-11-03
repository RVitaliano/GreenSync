"""Testa a rota POST /perguntar sem Gemini, Firestore e Redis (tudo simulado)."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.responder import IAError
from app.config import settings
from app.routes import ia as rota

LEITURA = {"umidade_solo": 20, "temperatura_ar": 24.1, "bomba_ligada": False}


@pytest.fixture
def client(monkeypatch):
    """App só com o router de IA; Firestore, Gemini e limite trocados por versões falsas."""
    chamadas = {}

    async def leitura_falsa(device_id):
        chamadas["device_id"] = device_id
        return LEITURA

    async def responder_falso(pergunta, leitura, historico=None):
        chamadas["pergunta"] = pergunta
        chamadas["leitura"] = leitura
        chamadas["historico_recebido"] = historico
        return {"texto": "Estou com sede.", "estado": {"estado": "atencao", "problemas": ["solo_seco"]},
                "modelo": "modelo-falso"}

    async def limite_falso(chave):
        chamadas["limite_chave"] = chave
        return chamadas.get("espera")  # None = pode seguir; número = segundos de espera

    async def rega_falsa(acao, fala_usuario, device_id, leitura, estado, origem):
        chamadas["rega"] = {"acao": acao, "fala_usuario": fala_usuario, "device_id": device_id,
                            "origem": origem}
        return chamadas.get("rega_resultado")   # None = não houve pedido de rega

    monkeypatch.setattr(rota, "ler_leitura_atual", leitura_falsa)
    monkeypatch.setattr(rota, "responder", responder_falso)
    monkeypatch.setattr(rota, "verificar_limite", limite_falso)
    monkeypatch.setattr(rota, "tratar_acao", rega_falsa)

    async def contexto_falso(device_id):
        chamadas["contexto_lido"] = device_id
        return chamadas.get("historico", [])

    async def salvar_falso(device_id, pergunta, resposta):
        chamadas.setdefault("salvos", []).append((device_id, pergunta, resposta))

    monkeypatch.setattr(rota, "ler_contexto", contexto_falso)
    monkeypatch.setattr(rota, "salvar_turno", salvar_falso)
    monkeypatch.setattr(settings, "api_key", "segredo")

    app = FastAPI()
    app.include_router(rota.router)
    c = TestClient(app)
    c.chamadas = chamadas
    return c


def post(c, device="vaso-01", pergunta="Qual a temperatura?", chave="segredo"):
    return c.post("/perguntar", json={"device_id": device, "pergunta": pergunta},
                  headers={"X-API-Key": chave})


def test_resposta_ok(client):
    r = post(client)
    assert r.status_code == 200
    corpo = r.json()
    assert corpo["texto"] == "Estou com sede."
    assert corpo["tela"] == "dados"            # a pergunta cita "temperatura"
    assert corpo["modelo"] == "modelo-falso"
    assert client.chamadas["device_id"] == "vaso-01"
    assert client.chamadas["leitura"] == LEITURA
    assert client.chamadas["limite_chave"] == "segredo"
    assert corpo["rega"] is None                # sem pedido de rega


def test_chave_errada_da_401(client):
    assert post(client, chave="errada").status_code == 401


def test_chave_errada_nao_gasta_o_limite(client):
    post(client, chave="errada")
    assert "limite_chave" not in client.chamadas


def test_sem_chave_da_401(client):
    r = client.post("/perguntar", json={"device_id": "vaso-01", "pergunta": "Oi?"})
    assert r.status_code == 401


def test_chave_com_acento_nao_derruba(client):
    # compare_digest com str não aceita acento; aqui deve só dar 401, nunca 500
    r = client.post("/perguntar", json={"device_id": "vaso-01", "pergunta": "Oi?"},
                    headers={"X-API-Key": "segredoé".encode("utf-8")})
    assert r.status_code == 401


def test_chave_vazia_no_env_deixa_aberta(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    r = client.post("/perguntar", json={"device_id": "vaso-01", "pergunta": "Oi?"})
    assert r.status_code == 200


def test_limite_estourado_da_429_sem_chamar_o_gemini(client):
    client.chamadas["espera"] = 30
    r = post(client)
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "30"
    assert "pergunta" not in client.chamadas   # o Gemini nem foi chamado
    assert "device_id" not in client.chamadas  # nem o Firestore


@pytest.mark.parametrize("device", ["a/b", "../x", "", "x" * 65, "vaso 01"])
def test_device_id_invalido_da_422(client, device):
    assert post(client, device=device).status_code == 422


def test_pergunta_vazia_ou_longa_da_422(client):
    assert post(client, pergunta="").status_code == 422
    assert post(client, pergunta="a" * 501).status_code == 422


def test_ia_fora_do_ar_da_502(client, monkeypatch):
    async def falha(pergunta, leitura, historico=None):
        raise IAError("nenhum modelo respondeu")

    monkeypatch.setattr(rota, "responder", falha)
    r = post(client)
    assert r.status_code == 502
    assert r.json()["detail"] == "assistente indisponível"
    assert "salvos" not in client.chamadas        # resposta que falhou não vira memória


# ---------- rega por voz/texto (REQ-FUNC-011) ----------

def test_pedido_de_rega_troca_a_frase_pela_oficial(client):
    client.chamadas["rega_resultado"] = {"fala": "Combinado, vou regar daqui a 10 minutos por 5 segundos.",
                                         "resultado": "agendada", "id": "ag1"}
    r = post(client, pergunta="Rega daqui a 10 minutos")
    corpo = r.json()
    assert r.status_code == 200
    assert corpo["texto"] == "Combinado, vou regar daqui a 10 minutos por 5 segundos."
    assert corpo["rega"] == {"resultado": "agendada", "id": "ag1"}
    # o serviço recebeu o que a pessoa escreveu (para a trava) e a origem
    assert client.chamadas["rega"]["fala_usuario"] == "Rega daqui a 10 minutos"
    assert client.chamadas["rega"]["device_id"] == "vaso-01"
    assert client.chamadas["rega"]["origem"] == "texto"


def test_rega_recusada_tambem_vira_a_frase_falada(client):
    client.chamadas["rega_resultado"] = {"fala": "Não consigo regar agora porque o vaso está desconectado.",
                                         "resultado": "recusada", "id": None}
    corpo = post(client, pergunta="Rega agora").json()
    assert corpo["texto"].startswith("Não consigo regar")
    assert corpo["rega"]["resultado"] == "recusada"


def test_limite_estourado_nao_trata_rega(client):
    client.chamadas["espera"] = 30
    post(client, pergunta="Rega agora")
    assert "rega" not in client.chamadas        # 429 antes de qualquer ação


# ---------- contexto da conversa (REQ-FUNC-008) ----------

def test_conversa_recente_vai_para_o_modelo(client):
    historico = [{"pergunta": "Qual a temperatura?", "resposta": "Uns 24 graus."}]
    client.chamadas["historico"] = historico
    post(client, pergunta="E a umidade?")
    assert client.chamadas["contexto_lido"] == "vaso-01"
    assert client.chamadas["historico_recebido"] == historico


def test_troca_e_guardada_com_a_frase_que_foi_dita(client):
    post(client, pergunta="Qual a temperatura?")
    assert client.chamadas["salvos"] == [("vaso-01", "Qual a temperatura?", "Estou com sede.")]


def test_na_rega_guarda_a_frase_oficial_do_backend(client):
    client.chamadas["rega_resultado"] = {"fala": "Combinado, vou regar daqui a 10 minutos por 5 segundos.",
                                         "resultado": "agendada", "id": "ag1"}
    post(client, pergunta="Rega daqui a 10 minutos")
    assert client.chamadas["salvos"][0][2] == "Combinado, vou regar daqui a 10 minutos por 5 segundos."


def test_limite_estourado_nao_toca_no_contexto(client):
    client.chamadas["espera"] = 30
    post(client)
    assert "contexto_lido" not in client.chamadas and "salvos" not in client.chamadas


def test_chave_errada_nao_toca_no_contexto(client):
    post(client, chave="errada")
    assert "contexto_lido" not in client.chamadas