"""Padrões de app/config.py (os testes já rodam sem o .env, ver conftest)."""
from app.config import settings


def test_modelos_do_gemini():
    assert settings.gemini_model == "gemini-3.5-flash-lite"
    assert settings.gemini_model_fallback == "gemini-3.1-flash-lite"


def test_prazo_do_audio_e_maior_que_o_do_texto():
    assert settings.gemini_timeout_audio_s == 25.0
    assert settings.gemini_timeout_audio_s > settings.gemini_timeout_s


def test_padroes_da_rega():
    assert (settings.rega_duracao_padrao_s, settings.rega_duracao_max_s) == (5, 10)


def test_prazo_do_firestore():
    assert 0 < settings.firestore_timeout_s <= 10
