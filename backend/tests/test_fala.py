"""Frases que a planta fala sobre a rega."""
from datetime import datetime, timezone

from app.agenda import fala

# 18:30 UTC = 15:30 em Brasília
QUANDO = datetime(2026, 11, 3, 18, 30, tzinfo=timezone.utc)


def test_agora():
    assert fala.confirmacao(QUANDO, 0, 5) == "Pode deixar, vou me regar agora por 5 segundos."


def test_segundos():
    assert fala.confirmacao(QUANDO, 30, 5) == "Combinado, vou regar daqui a 30 segundos por 5 segundos."


def test_um_segundo_fica_no_singular():
    assert "por 1 segundo." in fala.confirmacao(QUANDO, 30, 1)


def test_minutos():
    assert "daqui a 1 minuto " in fala.confirmacao(QUANDO, 60, 5)
    assert "daqui a 10 minutos " in fala.confirmacao(QUANDO, 600, 5)


def test_mais_de_uma_hora_fala_o_horario_do_relogio_local():
    assert fala.confirmacao(QUANDO, 7200, 5) == "Combinado, vou regar às 15:30 por 5 segundos."


def test_minuto_com_zero_a_esquerda():
    q = datetime(2026, 11, 3, 11, 5, tzinfo=timezone.utc)    # 8:05 em Brasília
    assert "às 8:05" in fala.confirmacao(q, 7200, 5)


def test_cancelamento_sem_restantes():
    assert fala.cancelamento(QUANDO, 0) == "Pronto, cancelei a rega das 15:30."


def test_cancelamento_com_restantes():
    assert fala.cancelamento(QUANDO, 1).endswith("Ainda tem 1 marcada.")
    assert fala.cancelamento(QUANDO, 2).endswith("Ainda têm 2 marcadas.")


def test_falha_na_hora_diz_o_motivo():
    assert "o vaso está desconectado" in fala.falha_na_hora("o vaso está desconectado")