from app.ai.estado import calcular_estado
from app.ai.prompt import montar_dados, montar_system_prompt


def test_dado_ausente_vira_indisponivel():
    leitura = {"umidade_solo": 20, "temperatura_ar": 24}  # sem ph e sem umidade_ar
    texto = montar_dados(leitura, calcular_estado(leitura))
    assert "umidade do solo: 20%" in texto
    assert "pH do solo: indisponível" in texto
    assert "umidade do ar: indisponível" in texto


def test_estado_com_sede():
    leitura = {"umidade_solo": 20}
    texto = montar_dados(leitura, calcular_estado(leitura))
    assert "preciso de água" in texto


def test_sem_leitura():
    texto = montar_dados(None, calcular_estado(None))
    assert "sem dados dos sensores" in texto


def test_system_prompt_tem_regras_e_dados():
    leitura = {"umidade_solo": 50}
    p = montar_system_prompt(leitura, calcular_estado(leitura))
    assert "primeira pessoa" in p
    assert "umidade do solo: 50%" in p