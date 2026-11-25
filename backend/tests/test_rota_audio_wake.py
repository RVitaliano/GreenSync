"""POST /audio com a palavra de ativação (WAKE_WORD_ATIVA), sem Gemini, voz, Firestore nem Redis reais."""
import logging

import pytest

from app import limite, redis_client
from app.ai.prompt import montar_system_prompt
from app.config import settings
from app.routes import audio as rota
from tests.falsos import leitura_ok
from tests.test_limite import FakeRedis
from tests.test_rota_audio import VOZ, client, post  # noqa: F401  (client é um fixture reaproveitado)

FALA_COM = "GreenSync, como ela está?"
FALA_SEM = "Bom dia pessoal, como ela está?"


@pytest.fixture
def wake(client, monkeypatch):
    monkeypatch.setattr(settings, "wake_word_ativa", True)
    return client


def conta_gemini(client, monkeypatch):
    """Conta quantas vezes o (falso) Gemini foi chamado."""
    original = rota.responder_audio
    chamadas = []

    async def espia(*a, **kw):
        chamadas.append(1)
        return await original(*a, **kw)

    monkeypatch.setattr(rota, "responder_audio", espia)
    return chamadas


# ------------------------------------------------------ desligada (padrão) ----

def test_padroes_da_configuracao():
    assert settings.wake_word_ativa is False
    assert settings.wake_word == "greensync"
    assert settings.wake_limite_clipes_por_min == 20


def test_desligada_o_comportamento_e_o_de_sempre(client, monkeypatch):
    def proibido(*a, **kw):
        raise AssertionError("o limite por minuto não existe com a palavra desligada")

    monkeypatch.setattr(rota, "verificar_limite_clipes", proibido)
    client.chamadas["ouviu"] = FALA_SEM                       # sem a palavra, e mesmo assim responde
    r = post(client)
    assert r.status_code == 200 and r.content == VOZ
    assert "x-ativada" not in r.headers
    assert client.chamadas["limite_chave"] == "segredo"        # limite de perguntas contado como antes
    assert client.chamadas["texto_falado"] == "Estou com sede."
    assert client.chamadas["salvos"][0][1] == FALA_SEM         # a fala segue inteira para o contexto


def test_desligada_nao_tira_nada_da_pergunta(client):
    client.chamadas["ouviu"] = FALA_COM
    post(client)
    assert client.chamadas["salvos"][0][1] == FALA_COM


# ---------------------------------------------------------- ligada, ignorada ----

def test_fala_sem_a_palavra_da_204_e_nao_gera_efeito_nenhum(wake):
    wake.chamadas["ouviu"] = FALA_SEM
    r = post(wake)
    assert r.status_code == 204 and r.content == b""
    assert r.headers["x-ativada"] == "nao"
    assert "audio" in wake.chamadas                            # o Gemini foi chamado (é ele que transcreve)
    assert "texto_falado" not in wake.chamadas                 # TTS NÃO chamado
    assert "limite_chave" not in wake.chamadas                 # limite de perguntas NÃO contado
    assert "salvos" not in wake.chamadas                       # contexto (Redis) NÃO gravado


@pytest.mark.parametrize("fala", ["como está o greensync", "", "regue a planta agora"])
def test_ignorada_nunca_aciona_a_rega(wake, fala):
    wake.chamadas["ouviu"] = fala
    wake.chamadas["acao"] = {"tipo": "regar", "daqui_a_s": None, "as_hora": None, "duracao_s": None}
    assert post(wake).status_code == 204
    assert "rega" not in wake.chamadas                         # tratar_acao nem foi chamado


def test_ignorada_nao_escreve_a_fala_no_log(wake, caplog):
    wake.chamadas["ouviu"] = "bom dia SEGREDO-DA-FALA"
    with caplog.at_level(logging.DEBUG):
        post(wake)
    assert "SEGREDO-DA-FALA" not in caplog.text
    assert "fala ignorada (sem palavra de ativação)" in caplog.text


def test_ignorada_nao_consulta_o_limite_de_perguntas_mesmo_estourado(wake):
    wake.chamadas["espera"] = 30                               # o limite de perguntas estaria estourado
    wake.chamadas["ouviu"] = FALA_SEM
    assert post(wake).status_code == 204


def test_ignorada_com_debug_continua_sem_corpo_nem_transcricao(wake):
    wake.chamadas["ouviu"] = FALA_SEM
    r = post(wake, url="/audio?debug=true")
    assert r.status_code == 204 and "x-ouviu" not in r.headers and "x-texto" not in r.headers


# ----------------------------------------------------------- ligada, ativada ----

def test_fala_com_a_palavra_responde_200_com_wav_e_cabecalho(wake):
    wake.chamadas["ouviu"] = FALA_COM
    r = post(wake)
    assert r.status_code == 200 and r.content == VOZ
    assert r.headers["x-ativada"] == "sim"
    assert r.headers["content-type"] == "audio/wav"
    assert wake.chamadas["limite_chave"] == "segredo"          # conta no limite de perguntas
    assert wake.chamadas["texto_falado"] == "Estou com sede."  # TTS chamado


def test_ativada_segue_sem_a_palavra_para_contexto_tela_e_rega(wake):
    wake.chamadas["ouviu"] = "GreenSync, regue a planta"
    wake.chamadas["acao"] = {"tipo": "regar", "daqui_a_s": None, "as_hora": None, "duracao_s": None}
    r = post(wake)
    assert r.status_code == 200
    assert wake.chamadas["rega"]["fala_usuario"] == "regue a planta"
    assert wake.chamadas["salvos"][0][1] == "regue a planta"


def test_ativada_com_tela_de_dados_usa_a_pergunta_sem_a_palavra(wake):
    wake.chamadas["ouviu"] = "GreenSync, qual a temperatura?"
    assert post(wake).headers["x-tela"] == "dados"


@pytest.mark.parametrize("fala", ["green sync, como ela está", "greensinc como ela está",
                                  "ei greensync como ela está", "grin sink como ela está"])
def test_variacoes_de_transcricao_ativam(wake, fala):
    wake.chamadas["ouviu"] = fala
    r = post(wake)
    assert r.status_code == 200 and r.headers["x-ativada"] == "sim"


def test_ativada_com_limite_de_perguntas_estourado_da_429_sem_voz(wake):
    wake.chamadas["ouviu"] = FALA_COM
    wake.chamadas["espera"] = 30
    r = post(wake)
    assert r.status_code == 429 and r.headers["retry-after"] == "30"
    assert "texto_falado" not in wake.chamadas and "salvos" not in wake.chamadas


def test_debug_ainda_funciona_quando_ativada(wake):
    wake.chamadas["ouviu"] = FALA_COM
    r = post(wake, url="/audio?debug=true")
    assert r.status_code == 200 and r.headers["x-ativada"] == "sim" and "x-ouviu" in r.headers


# ----------------------------------------- validações de sempre continuam ----

def test_chave_errada_e_audio_ruim_continuam_recusados(wake):
    assert post(wake, chave="errada").status_code == 401
    assert post(wake, corpo=b"nao e wav").status_code == 422
    assert "audio" not in wake.chamadas                        # nem chegou ao Gemini


# ------------------------------------------------- limite de falas por minuto ----

@pytest.fixture
def redis_falso(monkeypatch):
    r = FakeRedis()
    monkeypatch.setattr(redis_client, "get_redis", lambda: r)
    monkeypatch.setattr(limite, "_agora", lambda: 300.0)       # início de uma janela
    return r


def test_limite_por_minuto_estourado_da_429_e_o_gemini_nao_e_chamado(wake, redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 0)
    r = post(wake)
    assert r.status_code == 429
    assert r.json()["detail"] == "limite de perguntas atingido, tente de novo em instantes"
    assert int(r.headers["retry-after"]) >= 1
    assert "audio" not in wake.chamadas                        # Gemini NÃO chamado
    assert "texto_falado" not in wake.chamadas


def test_falas_ignoradas_tambem_contam_no_limite_por_minuto(wake, redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 2)
    chamadas = conta_gemini(wake, monkeypatch)
    wake.chamadas["ouviu"] = FALA_SEM
    assert [post(wake).status_code for _ in range(4)] == [204, 204, 429, 429]
    assert len(chamadas) == 2                                  # só 2 falas chegaram ao Gemini


def test_limite_por_minuto_mistura_falas_ativadas_e_ignoradas(wake, redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 3)
    codigos = []
    for fala in (FALA_SEM, FALA_COM, FALA_SEM, FALA_COM):
        wake.chamadas["ouviu"] = fala
        codigos.append(post(wake).status_code)
    assert codigos == [204, 200, 204, 429]


def test_redis_fora_segue_sem_limite_por_minuto(wake, redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 0)    # com Redis, tudo seria 429
    redis_falso.caido = True
    wake.chamadas["ouviu"] = FALA_COM
    assert post(wake).status_code == 200
    wake.chamadas["ouviu"] = FALA_SEM
    assert post(wake).status_code == 204


def test_sem_redis_configurado_segue_sem_limite_por_minuto(wake, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 0)    # conftest zera REDIS_URL
    wake.chamadas["ouviu"] = FALA_COM
    assert post(wake).status_code == 200


# ----------------------------------- verificar_limite_clipes (a função em si) ----

@pytest.mark.anyio
async def test_clipes_usa_contador_proprio_e_nao_mexe_no_de_perguntas(redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 2)
    monkeypatch.setattr(settings, "limite_perguntas", 3)
    monkeypatch.setattr(settings, "janela_limite_s", 60)
    assert await limite.verificar_limite_clipes("chave") is None
    assert all(k.startswith("wk:") for k in redis_falso.contadores)
    assert await limite.verificar_limite("chave") is None               # perguntas: contador separado
    assert any(k.startswith("rl:") for k in redis_falso.contadores)
    assert redis_falso.contadores[next(k for k in redis_falso.contadores if k.startswith("wk:"))] == 1


@pytest.mark.anyio
async def test_clipes_por_chave_janela_e_chave_nao_fica_em_texto(redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 1)
    assert await limite.verificar_limite_clipes("a") is None
    assert await limite.verificar_limite_clipes("a") == 60              # início da janela: espera 60 s
    assert await limite.verificar_limite_clipes("b") is None            # outra chave, outro contador
    assert all("a" != k.split(":")[1] and "chave" not in k for k in redis_falso.contadores)
    monkeypatch.setattr(limite, "_agora", lambda: 360.0)                # próxima janela
    assert await limite.verificar_limite_clipes("a") is None
    assert all(t == 120 for t in redis_falso.expiracoes.values())       # sempre com prazo de validade


@pytest.mark.anyio
async def test_clipes_com_redis_fora_deixa_passar(redis_falso, monkeypatch):
    monkeypatch.setattr(settings, "wake_limite_clipes_por_min", 0)
    redis_falso.caido = True
    assert await limite.verificar_limite_clipes("chave") is None


# --------------------------------------------------------------- prompt ----

def _prompt(audio):
    leitura = leitura_ok()
    from app.ai.estado import avaliar_estado
    return montar_system_prompt(leitura, avaliar_estado(leitura), audio=audio)


DICA = "O nome do assistente é GreenSync; ao transcrever, escreva sempre 'GreenSync'."


def test_prompt_de_audio_tem_a_dica_so_com_a_palavra_ligada(monkeypatch):
    assert DICA not in _prompt(audio=True)                       # desligada: prompt como sempre
    monkeypatch.setattr(settings, "wake_word_ativa", True)
    assert DICA in _prompt(audio=True)


def test_prompt_de_texto_nunca_tem_a_dica(monkeypatch):
    monkeypatch.setattr(settings, "wake_word_ativa", True)
    assert DICA not in _prompt(audio=False)


def test_dica_usa_a_palavra_configurada(monkeypatch):
    monkeypatch.setattr(settings, "wake_word_ativa", True)
    monkeypatch.setattr(settings, "wake_word", "Jardim")
    assert "O nome do assistente é Jardim; ao transcrever, escreva sempre 'Jardim'." in _prompt(audio=True)
