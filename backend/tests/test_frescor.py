"""Testa a detecção de dado velho / vaso offline (REQ-FUNC-007), sem Gemini nem Firestore."""
from datetime import datetime, timedelta, timezone

import pytest

from app import firebase_client
from app.ai.estado import avaliar_estado, avaliar_frescor
from app.ai.prompt import descrever_idade, montar_dados, montar_system_prompt
from app.config import settings

AGORA = datetime(2026, 11, 2, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def limite_120(monkeypatch):
    monkeypatch.setattr(settings, "leitura_velha_apos_s", 120)


def leitura(segundos_atras, **extra):
    """Leitura com solo seco, feita `segundos_atras` segundos antes de AGORA."""
    return {
        "umidade_solo": 20,
        "temperatura_ar": 24.1,
        "updated_at": AGORA - timedelta(seconds=segundos_atras),
        **extra,
    }


# ---------- avaliar_frescor ----------

def test_leitura_recente_e_atual():
    r = avaliar_frescor(leitura(10), AGORA)
    assert r == {"dados": "atuais", "idade_s": 10, "offline": False}


def test_leitura_velha_e_desatualizada():
    r = avaliar_frescor(leitura(600), AGORA)
    assert r == {"dados": "desatualizados", "idade_s": 600, "offline": False}


def test_no_limite_exato_ainda_e_atual():
    assert avaliar_frescor(leitura(120), AGORA)["dados"] == "atuais"
    assert avaliar_frescor(leitura(121), AGORA)["dados"] == "desatualizados"


def test_limite_vem_da_configuracao(monkeypatch):
    monkeypatch.setattr(settings, "leitura_velha_apos_s", 20)
    assert avaliar_frescor(leitura(30), AGORA)["dados"] == "desatualizados"


def test_vaso_offline_e_desatualizado_mesmo_com_leitura_recente():
    r = avaliar_frescor(leitura(5, status_vaso="offline"), AGORA)
    assert r == {"dados": "desatualizados", "idade_s": 5, "offline": True}


def test_status_online_nao_atrapalha():
    assert avaliar_frescor(leitura(5, status_vaso="online"), AGORA)["dados"] == "atuais"


def test_sem_updated_at_idade_desconhecida_nao_marca_como_velho():
    r = avaliar_frescor({"umidade_solo": 50}, AGORA)
    assert r == {"dados": "atuais", "idade_s": None, "offline": False}


def test_sem_updated_at_mas_offline_continua_desatualizado():
    r = avaliar_frescor({"umidade_solo": 50, "status_vaso": "offline"}, AGORA)
    assert r["dados"] == "desatualizados" and r["idade_s"] is None


def test_data_sem_fuso_e_tratada_como_utc():
    naive = (AGORA - timedelta(seconds=30)).replace(tzinfo=None)
    r = avaliar_frescor({"umidade_solo": 50, "updated_at": naive}, AGORA)
    assert r["idade_s"] == 30


def test_relogio_adiantado_nao_da_idade_negativa():
    futuro = {"umidade_solo": 50, "updated_at": AGORA + timedelta(seconds=5)}
    assert avaliar_frescor(futuro, AGORA)["idade_s"] == 0


def test_sem_leitura():
    assert avaliar_frescor(None, AGORA) == {"dados": "sem_dados", "idade_s": None, "offline": False}


def test_avaliar_estado_junta_estado_e_frescor():
    r = avaliar_estado(leitura(600), AGORA)
    assert r["estado"] == "atencao"
    assert r["problemas"] == ["solo_seco"]
    assert r["dados"] == "desatualizados"
    assert r["idade_s"] == 600


# ---------- descrever_idade ----------

@pytest.mark.parametrize("segundos, texto", [
    (0, "alguns segundos"),
    (59, "alguns segundos"),
    (60, "1 minuto"),
    (125, "2 minutos"),      # arredonda para baixo
    (3599, "59 minutos"),
    (3600, "1 hora"),
    (7300, "2 horas"),
    (86400, "1 dia"),
    (200000, "2 dias"),
])
def test_descrever_idade(segundos, texto):
    assert descrever_idade(segundos) == texto


# ---------- prompt ----------

def test_dado_atual_nao_menciona_desatualizado():
    l = leitura(10)
    texto = montar_dados(l, avaliar_estado(l, AGORA))
    assert texto.startswith("DADOS ATUAIS:")
    assert "DESATUALIZADOS" not in texto
    assert "preciso de água" in texto


def test_dado_velho_avisa_a_idade_e_nao_afirma_o_agora():
    l = leitura(600)
    texto = montar_dados(l, avaliar_estado(l, AGORA))
    assert texto.startswith("ÚLTIMOS DADOS RECEBIDOS (DESATUALIZADOS):")
    assert "não recebo dados dos sensores há 10 minutos" in texto
    assert "Não sei como estou agora" in texto
    assert "Na última leitura: o solo está seco" in texto
    assert "umidade do solo: 20%" in texto  # o número continua disponível, só que marcado


def test_dado_velho_com_tudo_bem_na_ultima_leitura():
    l = {"umidade_solo": 50, "updated_at": AGORA - timedelta(hours=3)}
    texto = montar_dados(l, avaliar_estado(l, AGORA))
    assert "há 3 horas" in texto
    assert "Na última leitura estava tudo bem" in texto
    assert "estou bem, sem nenhum problema" not in texto  # nunca afirma o "agora"


def test_vaso_offline_diz_que_esta_desconectado():
    l = leitura(300, status_vaso="offline")
    texto = montar_dados(l, avaliar_estado(l, AGORA))
    assert "o vaso está desconectado" in texto
    assert "o último dado chegou há 5 minutos" in texto


def test_vaso_offline_sem_horario_nao_inventa_tempo():
    l = {"umidade_solo": 50, "status_vaso": "offline"}
    texto = montar_dados(l, avaliar_estado(l, AGORA))
    assert "o vaso está desconectado." in texto
    assert " há " not in texto.split("ESTADO:")[1]


def test_system_prompt_tem_a_regra_do_dado_velho():
    l = leitura(600)
    p = montar_system_prompt(l, avaliar_estado(l, AGORA))
    assert "DESATUALIZADOS" in p
    assert "Nunca diga que está bem agora" in p


# ---------- leitura do Firestore (_read_current_sync) ----------

class FakeDoc:
    def __init__(self, dados):
        self._dados = dados
        self.exists = dados is not None

    def to_dict(self):
        return self._dados


class FakeDb:
    def __init__(self, dados):
        self._dados = dados

    def collection(self, _):
        return self

    def document(self, _):
        return self

    def get(self):
        return FakeDoc(self._dados)


def ler(monkeypatch, dados):
    monkeypatch.setattr(firebase_client, "init_firebase", lambda: FakeDb(dados))
    return firebase_client._read_current_sync("vaso-01")


def test_leitura_traz_o_status_do_vaso(monkeypatch):
    quando = AGORA - timedelta(seconds=7)
    r = ler(monkeypatch, {
        "status": "offline",
        "leitura_atual": {"umidade_solo": 20, "updated_at": quando},
    })
    assert r == {"umidade_solo": 20, "updated_at": quando, "status_vaso": "offline"}


def test_documento_inexistente_devolve_none(monkeypatch):
    assert ler(monkeypatch, None) is None


def test_documento_sem_leitura_devolve_none(monkeypatch):
    assert ler(monkeypatch, {"status": "offline"}) is None