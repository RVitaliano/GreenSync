"""Prontidão para o Render: /health sem dependências e recusa de configuração insegura."""
import logging

import pytest
from fastapi.testclient import TestClient

from app import firebase_client, main, mqtt_client, redis_client
from app.config import settings

CHAVE_BOA = "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6"


# ------------------------------------------------------------- /health ----

def test_health_responde_sem_tocar_em_firestore_mqtt_nem_redis(monkeypatch):
    def proibido(*a, **kw):
        raise AssertionError("/health não pode acessar serviços externos")

    monkeypatch.setattr(firebase_client, "init_firebase", proibido)
    monkeypatch.setattr(firebase_client, "ler_leitura_atual", proibido)
    monkeypatch.setattr(redis_client, "get_redis", proibido)
    monkeypatch.setattr(mqtt_client, "publicar_comando", proibido)
    monkeypatch.setattr(mqtt_client, "_cliente", None)          # MQTT "caído"
    c = TestClient(main.app)                                    # sem `with`: o lifespan não roda
    r = c.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_health_nao_pede_chave(monkeypatch):
    monkeypatch.setattr(settings, "api_key", CHAVE_BOA)
    assert TestClient(main.app).get("/health").status_code == 200


def test_rota_raiz_continua_igual():
    assert TestClient(main.app).get("/").json() == {"status": "ok"}


# --------------------------------------------------------- em produção ----

@pytest.mark.parametrize("valor,esperado", [("true", True), ("True", True), ("1", True),
                                            ("", False), ("false", False), ("0", False)])
def test_em_producao_vem_da_variavel_render(monkeypatch, valor, esperado):
    monkeypatch.setenv("RENDER", valor)
    assert main.em_producao() is esperado


def test_sem_a_variavel_render_nao_e_producao(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    assert main.em_producao() is False


@pytest.mark.parametrize("chave", ["", "1234", "senha", "ADMIN", "changeme", "curta", "sua_chave_aqui", "12345678901"])
def test_api_key_vazia_ou_fraca_e_problema(monkeypatch, chave):
    monkeypatch.setattr(settings, "api_key", chave)
    problemas = main.problemas_de_producao()
    assert any(p.startswith("API_KEY") for p in problemas)
    assert chave not in " ".join(problemas) or chave == ""          # nunca repete o valor


def test_api_key_boa_nao_e_problema(monkeypatch):
    monkeypatch.setattr(settings, "api_key", CHAVE_BOA)
    assert main.problemas_de_producao() == []


def test_admin_vazia_e_segura_mas_admin_fraca_nao(monkeypatch):
    monkeypatch.setattr(settings, "api_key", CHAVE_BOA)
    monkeypatch.setattr(settings, "admin_api_key", "")
    assert main.problemas_de_producao() == []                       # rota de firmware só fica desligada
    monkeypatch.setattr(settings, "admin_api_key", "1234")
    assert any(p.startswith("ADMIN_API_KEY") for p in main.problemas_de_producao())
    monkeypatch.setattr(settings, "admin_api_key", CHAVE_BOA[::-1])
    assert main.problemas_de_producao() == []


def test_no_render_com_chave_insegura_nao_sobe(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "api_key", "")
    with pytest.raises(RuntimeError) as e:
        main.validar_producao()
    assert "API_KEY" in str(e.value)


def test_a_mensagem_de_erro_nao_vaza_a_chave(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "api_key", CHAVE_BOA)
    monkeypatch.setattr(settings, "admin_api_key", "fraca1234")
    with pytest.raises(RuntimeError) as e:
        main.validar_producao()
    assert "fraca1234" not in str(e.value) and CHAVE_BOA not in str(e.value)


def test_localmente_chave_vazia_continua_permitida(monkeypatch):
    monkeypatch.delenv("RENDER", raising=False)
    monkeypatch.setattr(settings, "api_key", "")
    main.validar_producao()                                         # não levanta


def test_no_render_com_tudo_certo_sobe_e_avisa_do_mqtt(monkeypatch, caplog):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "api_key", CHAVE_BOA)
    monkeypatch.setattr(settings, "mqtt_use_tls", False)
    monkeypatch.setattr(settings, "mqtt_host", "localhost")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.validar_producao()
    assert "MQTT_USE_TLS=false" in caplog.text and "broker local" in caplog.text


def test_no_render_com_mqtt_tls_e_host_real_nao_avisa(monkeypatch, caplog):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "api_key", CHAVE_BOA)
    monkeypatch.setattr(settings, "mqtt_use_tls", True)
    monkeypatch.setattr(settings, "mqtt_host", "abc123.emqxsl.com")
    with caplog.at_level(logging.WARNING, logger="greensync"):
        main.validar_producao()
    assert caplog.text == ""


@pytest.mark.anyio
async def test_lifespan_valida_antes_de_abrir_o_firebase(monkeypatch):
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setattr(settings, "api_key", "")
    aberto = []
    monkeypatch.setattr(main, "init_firebase", lambda: aberto.append(1))
    with pytest.raises(RuntimeError):
        async with main.lifespan(main.app):
            pass
    assert aberto == []
