"""Decide o que o display do S3 mostra (ADR-023): 'rosto' ou 'dados'.

Versão simples, por palavras-chave. Se a pergunta for sobre um dado dos
sensores, o display troca para os dados; senão, fica na carinha.
"""
import re

_PADRAO_DADOS = re.compile(
    r"\b(temperatura|umidade|ph|sensor|sensores|dados|graus|medida|medidas|quanto)\b",
    re.IGNORECASE,
)


def decidir_tela(pergunta: str) -> str:
    """Devolve 'dados' se a pergunta pede um número dos sensores; senão 'rosto'."""
    return "dados" if _PADRAO_DADOS.search(pergunta) else "rosto"