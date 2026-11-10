"""Regras puras da rega: horário, limites e recusas."""
from datetime import datetime, timedelta, timezone

import pytest

from app.agenda.regras import (MOTIVO_INCERTO, Pedido, Recusa, checar_regras, conta_no_intervalo,
                               pessoa_pediu_cancelar, pessoa_pediu_rega, resolver_pedido)
from app.ai.estado import avaliar_estado
from app.config import settings

# 18:00 UTC = 15:00 em Brasília (fuso -3)
AGORA = datetime(2026, 11, 3, 18, 0, 0, tzinfo=timezone.utc)
OK = {"umidade_solo": 20, "bomba_ligada": False, "status_vaso": "online"}


def acao(**kw):
    return {"tipo": "regar", "daqui_a_s": None, "as_hora": None, "duracao_s": None, **kw}


# ---------- trava "a pessoa pediu rega" ----------

@pytest.mark.parametrize("frase", [
    "Rega a planta agora", "Pode regar daqui a 1 minuto", "Regue por favor", "Me molhe um pouco",
    "Quero irrigar o vaso", "Faz uma rega de 5 segundos", "REGA AGORA", "Regar às 15h",
])
def test_frases_que_pedem_rega(frase):
    assert pessoa_pediu_rega(frase)


@pytest.mark.parametrize("frase", [
    "Como você está?", "Qual a temperatura?", "Você está com sede?", "Preciso de água?", "", None,
    "Qual o seu pH?", "Qual o seu nome?",
])
def test_frases_que_nao_pedem_rega(frase):
    assert not pessoa_pediu_rega(frase)


# ---------- resolver_pedido: horário ----------

def test_sem_horario_e_agora():
    p = resolver_pedido(acao(), AGORA)
    assert p.atraso_s == 0 and p.quando == AGORA
    assert p.duracao_s == settings.rega_duracao_padrao_s


def test_daqui_a_segundos():
    p = resolver_pedido(acao(daqui_a_s=600), AGORA)
    assert p.quando == AGORA + timedelta(seconds=600) and p.atraso_s == 600


def test_hora_de_hoje_no_fuso_do_usuario():
    p = resolver_pedido(acao(as_hora="15:30"), AGORA)          # são 15:00 em Brasília
    assert p.quando == datetime(2026, 11, 3, 18, 30, tzinfo=timezone.utc)
    assert p.atraso_s == 1800


def test_hora_que_ja_passou_vale_amanha():
    p = resolver_pedido(acao(as_hora="14:00"), AGORA)
    assert p.quando == datetime(2026, 11, 4, 17, 0, tzinfo=timezone.utc)
    assert p.atraso_s == 23 * 3600


def test_hora_igual_a_agora_vale_amanha_e_ainda_cabe_nas_24h():
    p = resolver_pedido(acao(as_hora="15:00"), AGORA)
    assert p.atraso_s == 86400


def test_hora_sem_zero_a_esquerda():
    assert resolver_pedido(acao(as_hora="8:05"), AGORA).quando.astimezone(timezone(timedelta(hours=-3))).hour == 8


@pytest.mark.parametrize("hora", ["25:00", "12:60", "meio-dia", "15h", "15:3", "1530"])
def test_hora_invalida_recusa(hora):
    with pytest.raises(Recusa) as e:
        resolver_pedido(acao(as_hora=hora), AGORA)
    assert e.value.codigo == "hora_invalida"


def test_hora_tem_prioridade_sobre_daqui_a():
    p = resolver_pedido(acao(as_hora="15:30", daqui_a_s=5), AGORA)
    assert p.atraso_s == 1800


def test_atraso_acima_do_maximo_recusa():
    resolver_pedido(acao(daqui_a_s=settings.rega_atraso_max_s), AGORA)       # no limite: aceita
    with pytest.raises(Recusa) as e:
        resolver_pedido(acao(daqui_a_s=settings.rega_atraso_max_s + 1), AGORA)
    assert e.value.codigo == "atraso_grande"
    assert "24 horas" in e.value.fala


def test_atraso_negativo_recusa():
    with pytest.raises(Recusa) as e:
        resolver_pedido(acao(daqui_a_s=-10), AGORA)
    assert e.value.codigo == "atraso_negativo"


# ---------- resolver_pedido: duração ----------

def test_duracao_informada():
    assert resolver_pedido(acao(duracao_s=8), AGORA).duracao_s == 8


def test_duracao_no_limite_aceita_e_acima_recusa():
    resolver_pedido(acao(duracao_s=settings.rega_duracao_max_s), AGORA)
    with pytest.raises(Recusa) as e:
        resolver_pedido(acao(duracao_s=settings.rega_duracao_max_s + 1), AGORA)
    assert e.value.codigo == "duracao_grande"
    assert "10 segundos" in e.value.fala


@pytest.mark.parametrize("d", [0, -3])
def test_duracao_zero_ou_negativa_recusa(d):
    with pytest.raises(Recusa) as e:
        resolver_pedido(acao(duracao_s=d), AGORA)
    assert e.value.codigo == "duracao_invalida"


# ---------- checar_regras ----------

def pedido(atraso_s=0, quando=None):
    return Pedido(quando=quando or AGORA + timedelta(seconds=atraso_s), duracao_s=5, atraso_s=atraso_s)


def checar(leitura=OK, atraso_s=0, vizinhos=()):
    return checar_regras(pedido(atraso_s), leitura, avaliar_estado(leitura), list(vizinhos))


def test_tudo_certo_passa():
    checar()


def test_sem_leitura_recusa():
    with pytest.raises(Recusa) as e:
        checar_regras(pedido(), None, avaliar_estado(None), [])
    assert e.value.codigo == "sem_dados"


def test_vaso_offline_recusa():
    with pytest.raises(Recusa) as e:
        checar(leitura={**OK, "status_vaso": "offline"})
    assert e.value.codigo == "offline"
    assert "desconectado" in e.value.fala


def test_solo_encharcado_recusa_rega_de_agora():
    with pytest.raises(Recusa) as e:
        checar(leitura={**OK, "umidade_solo": 85})
    assert e.value.codigo == "solo_encharcado"


def test_solo_encharcado_nao_barra_rega_para_daqui_a_horas():
    checar(leitura={**OK, "umidade_solo": 85}, atraso_s=7200)    # reconferido na hora de regar


def test_solo_no_limite_ainda_passa():
    checar(leitura={**OK, "umidade_solo": settings.solo_encharcado_acima})


def test_bomba_ligada_recusa_rega_imediata():
    with pytest.raises(Recusa) as e:
        checar(leitura={**OK, "bomba_ligada": True})
    assert e.value.codigo == "bomba_ligada"


def test_bomba_ligada_nao_barra_rega_agendada():
    checar(leitura={**OK, "bomba_ligada": True}, atraso_s=120)


def test_vizinha_pendente_dentro_do_intervalo_recusa():
    viz = [{"status": "pendente", "quando": AGORA + timedelta(seconds=300)}]
    with pytest.raises(Recusa) as e:
        checar(vizinhos=viz)
    assert e.value.codigo == "intervalo"
    assert "10 minutos" in e.value.fala


def test_rega_recente_concluida_conta_para_o_intervalo():
    viz = [{"status": "concluida", "quando": AGORA - timedelta(seconds=120)}]
    with pytest.raises(Recusa):
        checar(vizinhos=viz)


def test_vizinha_fora_do_intervalo_passa():
    viz = [{"status": "pendente", "quando": AGORA + timedelta(seconds=settings.rega_intervalo_min_s)}]
    checar(vizinhos=viz)


@pytest.mark.parametrize("status", ["cancelada", "expirada", "falhou"])
def test_vizinha_que_nao_aconteceu_nao_conta(status):
    viz = [{"status": status, "quando": AGORA + timedelta(seconds=60)}]
    checar(vizinhos=viz)

# ---------- trava de rega e de cancelamento (palavras) ----------

@pytest.mark.parametrize("fala", [
    "Rega daqui a pouco", "Pode me regar?", "Regue-me por favor", "Regá-la agora",
    "Me molha um pouco", "Irrigue o vaso", "Quero que você se regue", "Vai regando",
])
def test_frases_que_pedem_rega_passam(fala):
    assert pessoa_pediu_rega(fala)


@pytest.mark.parametrize("fala", [
    "Pode regular a temperatura?", "Qual o regulamento?", "Você foi regada hoje?",
    "O solo está molhado?", "Que região você é?", "Já foi regado?", "", None,
])
def test_frases_que_nao_pedem_rega_nao_passam(fala):
    assert not pessoa_pediu_rega(fala)


@pytest.mark.parametrize("fala", [
    "Cancela a rega", "Desmarca a rega", "Esquece isso", "Não precisa mais",
    "Deixa pra lá", "Melhor não", "Desfaz isso",
])
def test_frases_que_pedem_cancelar_passam(fala):
    assert pessoa_pediu_cancelar(fala)


@pytest.mark.parametrize("fala", ["Qual a temperatura?", "Rega agora", "", None])
def test_frases_que_nao_pedem_cancelar_nao_passam(fala):
    assert not pessoa_pediu_cancelar(fala)


# ---------- falha incerta conta no intervalo ----------

@pytest.mark.parametrize("ag,esperado", [
    ({"status": "pendente"}, True),
    ({"status": "executando"}, True),
    ({"status": "concluida"}, True),
    ({"status": "falhou", "motivo": MOTIVO_INCERTO}, True),
    ({"status": "falhou", "motivo": "o vaso está desconectado"}, False),
    ({"status": "falhou"}, False),
    ({"status": "cancelada"}, False),
    ({}, False),
])
def test_conta_no_intervalo(ag, esperado):
    assert conta_no_intervalo(ag) is esperado


def test_falha_incerta_vizinha_recusa_por_intervalo():
    viz = [{"status": "falhou", "motivo": MOTIVO_INCERTO, "quando": AGORA - timedelta(seconds=60)}]
    with pytest.raises(Recusa) as e:
        checar(vizinhos=viz)
    assert e.value.codigo == "intervalo"


def test_falha_comum_vizinha_nao_recusa():
    viz = [{"status": "falhou", "motivo": "o vaso está desconectado", "quando": AGORA - timedelta(seconds=60)}]
    checar(vizinhos=viz)
