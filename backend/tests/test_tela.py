from app.ai.tela import decidir_tela


def test_pergunta_sobre_dado_mostra_dados():
    assert decidir_tela("Qual a temperatura?") == "dados"
    assert decidir_tela("Como está o seu pH?") == "dados"
    assert decidir_tela("Quanto de umidade você tem?") == "dados"


def test_pergunta_geral_fica_no_rosto():
    assert decidir_tela("Como você está?") == "rosto"
    assert decidir_tela("Você gosta de sol?") == "rosto"


def test_palavra_parecida_nao_dispara():
    # "ph" só conta como palavra inteira (não dentro de "telefone" ou "graph")
    assert decidir_tela("Você viu o geographic?") == "rosto"