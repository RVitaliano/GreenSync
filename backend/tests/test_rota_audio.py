"""Testa POST /audio sem Gemini, voz, Firestore e Redis (tudo simulado)."""
import json
from urllib.parse import unquote

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.ai.audio import wav_de_pcm
from app.ai.resiliencia import IAError
from app.config import settings
from app.routes import audio as rota

LEITURA = {"ph": 6.44, "umidade_solo": 20.4, "temperatura_ar": 24.14, "umidade_ar": 58.2,
           "bomba_ligada": False}
VOZ = wav_de_pcm(b"\x01\x00" * 2400, sample_rate=24000)   # a "resposta falada"


def wav(segundos=1.0):
    return wav_de_pcm(b"\x00\x00" * int(16000 * segundos), sample_rate=16000)


@pytest.fixture
def client(monkeypatch):
    """App só com a rota de áudio; Firestore, Gemini, voz e limite viram versões falsas."""
    chamadas = {}

    async def leitura_falsa(device_id):
        chamadas["device_id"] = device_id
        return chamadas.get("leitura", LEITURA)

    async def responder_falso(audio, mime, leitura):
        chamadas["audio"] = audio
        chamadas["mime"] = mime
        return {
            "texto": "Estou com sede.",
            "pergunta_ouvida": chamadas.get("ouviu", "Como você está?"),
            "acao": chamadas.get("acao"),
            "estado": chamadas.get("estado", {"estado": "atencao", "problemas": ["solo_seco"],
                                               "dados": "atuais", "idade_s": 3, "offline": False}),
            "modelo": "modelo-falso",
        }

    async def voz_falsa(texto):
        chamadas["texto_falado"] = texto
        return VOZ, "voz-falsa"

    async def limite_falso(chave):
        chamadas["limite_chave"] = chave
        return chamadas.get("espera")

    async def rega_falsa(acao, fala_usuario, device_id, leitura, estado, origem):
        chamadas["rega"] = {"acao": acao, "fala_usuario": fala_usuario, "device_id": device_id,
                            "origem": origem}
        return chamadas.get("rega_resultado")   # None = não houve pedido de rega

    monkeypatch.setattr(rota, "ler_leitura_atual", leitura_falsa)
    monkeypatch.setattr(rota, "responder_audio", responder_falso)
    monkeypatch.setattr(rota, "sintetizar", voz_falsa)
    monkeypatch.setattr(rota, "verificar_limite", limite_falso)
    monkeypatch.setattr(rota, "tratar_acao", rega_falsa)
    monkeypatch.setattr(settings, "api_key", "segredo")

    app = FastAPI()
    app.include_router(rota.router)
    c = TestClient(app)
    c.chamadas = chamadas
    return c


def post(c, corpo=None, chave="segredo", device="vaso-01", tipo="audio/wav", url="/audio"):
    cab = {"Content-Type": tipo}
    if chave is not None:
        cab["X-API-Key"] = chave
    if device is not None:
        cab["X-Device-Id"] = device
    return c.post(url, content=wav() if corpo is None else corpo, headers=cab)


# ---------- caminho feliz ----------

def test_resposta_ok_devolve_o_wav_da_voz(client):
    r = post(client)
    assert r.status_code == 200
    assert r.headers["content-type"] == "audio/wav"
    assert r.content == VOZ
    assert client.chamadas["device_id"] == "vaso-01"
    assert client.chamadas["mime"] == "audio/wav"
    assert client.chamadas["limite_chave"] == "segredo"
    assert client.chamadas["texto_falado"] == "Estou com sede."


def test_x_tela_vem_da_pergunta_ouvida(client):
    client.chamadas["ouviu"] = "Como você está?"
    assert post(client).headers["X-Tela"] == "rosto"
    client.chamadas["ouviu"] = "Qual é a temperatura?"
    assert post(client).headers["X-Tela"] == "dados"


def test_silencio_sem_pergunta_ouvida_fica_no_rosto(client):
    client.chamadas["ouviu"] = ""
    assert post(client).headers["X-Tela"] == "rosto"


def test_x_dados_e_json_pequeno_e_arredondado(client):
    h = post(client).headers["X-Dados"]
    assert json.loads(h) == {"ph": 6.4, "solo": 20, "temp": 24.1, "ar": 58, "atuais": True}
    assert len(h) < 100          # cabe no buffer de cabeçalho do ESP32


def test_x_dados_marca_dado_velho(client):
    client.chamadas["estado"] = {"estado": "ok", "problemas": [], "dados": "desatualizados",
                                 "idade_s": 600, "offline": False}
    assert json.loads(post(client).headers["X-Dados"])["atuais"] is False


def test_x_dados_com_campos_faltando_vira_null(client):
    client.chamadas["leitura"] = {"umidade_solo": 50}
    d = json.loads(post(client).headers["X-Dados"])
    assert d["solo"] == 50 and d["ph"] is None and d["temp"] is None and d["ar"] is None


def test_x_dados_sem_leitura_nenhuma(client):
    client.chamadas["leitura"] = None
    client.chamadas["estado"] = {"estado": "sem_dados", "problemas": [], "dados": "sem_dados",
                                 "idade_s": None, "offline": False}
    d = json.loads(post(client).headers["X-Dados"])
    assert d == {"ph": None, "solo": None, "temp": None, "ar": None, "atuais": False}


def test_cabecalhos_padrao_nao_vazam_texto_da_conversa(client):
    r = post(client)
    for nome in ("X-Ouviu", "X-Texto", "X-Modelo"):
        assert nome not in r.headers


def test_debug_traz_o_que_ouviu_e_respondeu(client):
    r = post(client, url="/audio?debug=true")
    assert unquote(r.headers["X-Ouviu"]) == "Como você está?"
    assert unquote(r.headers["X-Texto"]) == "Estou com sede."
    assert r.headers["X-Modelo"] == "modelo-falso / voz-falsa"
    r.headers["X-Texto"].encode("ascii")     # com %-encoding, cabe em qualquer cliente HTTP


def test_aceita_audio_do_celular(client):
    r = post(client, corpo=b"\xff\xfb\x90\x00" * 200, tipo="audio/mpeg")
    assert r.status_code == 200
    assert client.chamadas["mime"] == "audio/mp3"


# ---------- segurança ----------

def test_chave_errada_da_401(client):
    assert post(client, chave="errada").status_code == 401


def test_sem_chave_da_401(client):
    assert post(client, chave=None).status_code == 401


def test_chave_com_acento_nao_derruba(client):
    r = client.post("/audio", content=wav(),
                    headers={"Content-Type": "audio/wav", "X-Device-Id": "vaso-01",
                             "X-API-Key": "segredoé".encode("utf-8")})
    assert r.status_code == 401


def test_chave_errada_nao_gasta_o_limite_nem_o_gemini(client):
    post(client, chave="errada")
    assert "limite_chave" not in client.chamadas
    assert "audio" not in client.chamadas


def test_chave_vazia_no_env_deixa_aberta(client, monkeypatch):
    monkeypatch.setattr(settings, "api_key", "")
    assert post(client, chave=None).status_code == 200


@pytest.mark.parametrize("device", [None, "", "a/b", "../x", "x" * 65, "vaso 01"])
def test_device_id_invalido_ou_ausente_da_422(client, device):
    assert post(client, device=device).status_code == 422


# ---------- áudio inválido ----------

@pytest.mark.parametrize("corpo, tipo", [
    (b"", "audio/wav"),                          # vazio
    (b"isso nao e um wav", "audio/wav"),         # lixo
    (None, "application/json"),                  # formato não aceito
    (None, "text/plain"),
])
def test_audio_invalido_da_422_sem_gastar_limite(client, corpo, tipo):
    r = post(client, corpo=corpo, tipo=tipo)
    assert r.status_code == 422
    assert "limite_chave" not in client.chamadas
    assert "audio" not in client.chamadas


def test_wav_longo_demais_da_422(client, monkeypatch):
    monkeypatch.setattr(settings, "audio_max_s", 2.0)
    monkeypatch.setattr(settings, "audio_max_bytes", 10_000_000)
    r = post(client, corpo=wav(5))
    assert r.status_code == 422
    assert "longo demais" in r.json()["detail"]


def test_corpo_grande_demais_da_413_pelo_content_length(client, monkeypatch):
    monkeypatch.setattr(settings, "audio_max_bytes", 1000)
    r = post(client, corpo=b"x" * 2000)
    assert r.status_code == 413
    assert "audio" not in client.chamadas


def test_corpo_grande_demais_da_413_mesmo_sem_content_length(client, monkeypatch):
    # Corpo em pedaços (chunked): não há Content-Length para conferir antes.
    monkeypatch.setattr(settings, "audio_max_bytes", 1000)
    r = post(client, corpo=iter([b"x" * 600, b"x" * 600]))
    assert r.status_code == 413
    assert "audio" not in client.chamadas


# ---------- limite e falhas ----------

def test_limite_estourado_da_429_sem_chamar_o_gemini(client):
    client.chamadas["espera"] = 30
    r = post(client)
    assert r.status_code == 429
    assert r.headers["Retry-After"] == "30"
    assert "audio" not in client.chamadas        # o Gemini nem foi chamado
    assert "device_id" not in client.chamadas    # nem o Firestore
    assert "texto_falado" not in client.chamadas


def test_gemini_fora_do_ar_da_502(client, monkeypatch):
    async def falha(audio, mime, leitura):
        raise IAError("nenhum modelo respondeu")

    monkeypatch.setattr(rota, "responder_audio", falha)
    r = post(client)
    assert r.status_code == 502
    assert r.json()["detail"] == "assistente indisponível"


def test_voz_fora_do_ar_da_502(client, monkeypatch):
    async def falha(texto):
        raise IAError("tts fora")

    monkeypatch.setattr(rota, "sintetizar", falha)
    r = post(client)
    assert r.status_code == 502
    assert r.json()["detail"] == "voz indisponível"


# ---------- rega por voz (REQ-FUNC-011) ----------

PEDIDO = {"tipo": "regar", "daqui_a_s": 60, "as_hora": None, "duracao_s": None}


def test_rega_por_voz_fala_a_confirmacao_oficial(client):
    client.chamadas["ouviu"] = "Rega daqui a um minuto"
    client.chamadas["acao"] = PEDIDO
    client.chamadas["rega_resultado"] = {"fala": "Combinado, vou regar daqui a 1 minuto por 5 segundos.",
                                         "resultado": "agendada", "id": "ag1"}
    r = post(client)
    assert r.status_code == 200
    # o que vai para a síntese de voz é a frase do backend, não a do modelo
    assert client.chamadas["texto_falado"] == "Combinado, vou regar daqui a 1 minuto por 5 segundos."
    assert client.chamadas["rega"] == {"acao": PEDIDO, "fala_usuario": "Rega daqui a um minuto",
                                       "device_id": "vaso-01", "origem": "voz"}


def test_rega_recusada_por_voz_fala_a_recusa(client):
    client.chamadas["ouviu"] = "Rega agora"
    client.chamadas["acao"] = PEDIDO
    client.chamadas["rega_resultado"] = {"fala": "Meu solo já está encharcado, melhor não regar agora.",
                                         "resultado": "recusada", "id": None}
    assert post(client).status_code == 200
    assert client.chamadas["texto_falado"].startswith("Meu solo já está encharcado")


def test_sem_pedido_de_rega_fala_a_resposta_do_modelo(client):
    post(client)
    assert client.chamadas["texto_falado"] == "Estou com sede."


def test_limite_estourado_nao_trata_rega_por_voz(client):
    client.chamadas["espera"] = 30
    client.chamadas["acao"] = PEDIDO
    post(client)
    assert "rega" not in client.chamadas


def test_debug_mostra_a_frase_efetivamente_falada(client):
    # X-Texto no debug traz a frase que foi para a voz (a oficial da rega, não a do modelo)
    client.chamadas["ouviu"] = "Rega agora"
    client.chamadas["acao"] = PEDIDO
    client.chamadas["rega_resultado"] = {"fala": "Pode deixar, vou me regar agora por 5 segundos.",
                                         "resultado": "agendada", "id": "ag1"}
    r = post(client, url="/audio?debug=true")
    assert unquote(r.headers["X-Texto"]) == "Pode deixar, vou me regar agora por 5 segundos."