"""Palavra de ativação: decisão pura (sem rede, sem Redis)."""
import pytest

from app.ai.ativacao import analisar_ativacao, fala_ativada

PALAVRA = "greensync"


@pytest.mark.parametrize("fala,resto", [
    ("GreenSync, como ela está?", "como ela está?"),
    ("greensync como ela está", "como ela está"),
    ("GREENSYNC!", ""),
    ("ei greensync qual a temperatura", "qual a temperatura"),
    ("Ei, GreenSync, tudo bem?", "tudo bem?"),
    ("oi ok greensync oi", "oi"),                     # 2 palavras de enchimento
    ("e aí GreenSync tudo bem", "tudo bem"),          # "e aí" é enchimento (conta como 2)
    ("hey greensync", ""),
    ("olá greensync, regar agora", "regar agora"),
    ("green sync como ela está", "como ela está"),     # partida em duas
    ("Green-Sync: regar", "regar"),
    ("greensinc, e a umidade?", "e a umidade?"),      # erro de transcrição
    ("grin sink como estou", "como estou"),
    ("Gri en sink olá", "olá"),                       # partida em três
    ("green sink regar agora", "regar agora"),
])
def test_fala_com_a_palavra_ativa_e_o_resto_vem_sem_ela(fala, resto):
    assert fala_ativada(fala, PALAVRA) is True
    assert analisar_ativacao(fala, PALAVRA) == (True, resto)


@pytest.mark.parametrize("fala", [
    "como está o greensync",          # no meio/fim
    "bom dia pessoal",
    "como ela está, greensync?",
    "bom dia greensync",
    "",
    "   ",
    "...",
    "ei",
    "ei oi",                          # só enchimento
    "ei oi ok greensync",             # enchimento demais (3 palavras)
    "e ai e ai greensync",
    "xis greensync",                  # lixo antes da palavra
    "greenhouse effect",
    "green",
    "sync",
    "regue a planta",
    "qual a temperatura",
])
def test_fala_sem_a_palavra_no_comeco_nao_ativa(fala):
    assert fala_ativada(fala, PALAVRA) is False
    assert analisar_ativacao(fala, PALAVRA) == (False, fala)         # a fala volta como veio


def test_none_e_palavra_vazia_nao_quebram():
    assert analisar_ativacao(None, PALAVRA) == (False, "")
    assert fala_ativada("greensync oi", "") is False
    assert fala_ativada("greensync oi", None) is False


def test_acentos_maiusculas_e_pontuacao_nao_importam():
    assert fala_ativada("  ¡GRÉÉNSYNC!  ", PALAVRA)
    assert fala_ativada("Ôi, Greensync…", PALAVRA)


def test_a_palavra_configurada_vale_no_lugar_do_padrao():
    assert fala_ativada("Jardim, como estou?", "jardim")
    assert analisar_ativacao("Jardim, como estou?", "jardim") == (True, "como estou?")
    assert not fala_ativada("greensync, como estou?", "jardim")


def test_palavra_configurada_com_espaco_e_acento():
    assert fala_ativada("Planta Linda, tudo bem?", "Planta Lindá")
