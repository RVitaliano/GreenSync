from app.ai.estado import calcular_estado


def test_solo_seco():
    r = calcular_estado({"umidade_solo": 20, "temperatura_ar": 24, "ph": 6.4})
    assert r == {"estado": "atencao", "problemas": ["solo_seco"]}


def test_tudo_ok():
    r = calcular_estado({"umidade_solo": 50, "temperatura_ar": 24, "ph": 6.4})
    assert r == {"estado": "ok", "problemas": []}


def test_sem_dados():
    assert calcular_estado(None) == {"estado": "sem_dados", "problemas": []}


def test_campo_ausente_nao_inventa():
    # sem umidade_ar, sem ph: só avalia o que existe
    r = calcular_estado({"umidade_solo": 50})
    assert r == {"estado": "ok", "problemas": []}