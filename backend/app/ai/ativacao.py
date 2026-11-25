"""Palavra de ativação ("GreenSync"): decide se uma fala detectada é para o assistente.

Funções puras (só biblioteca padrão), sem rede nem Redis. A fala só vale se a palavra vier no
COMEÇO (depois de até 2 palavras de enchimento, como "ei" ou "e aí"). Compara sem acento, sem
maiúsculas, sem pontuação e sem espaços internos, com tolerância de transcrição (difflib).
"""
import re
import unicodedata
from difflib import SequenceMatcher

RAZAO_MINIMA = 0.75          # semelhança mínima entre o que foi ouvido e a palavra
MAX_PALAVRAS_ATIVACAO = 3    # "green sync", "gri en sink"...: a palavra pode vir partida em até 3
MAX_ENCHIMENTO = 2           # no máximo 2 palavras de enchimento antes dela
RAZAO_PONTAS = 0.5           # em palavra partida, a 1ª parte parece o início e a última o fim

ENCHIMENTO_UNICO = {"ei", "oi", "ola", "ok", "hey"}
ENCHIMENTO_DUPLO = (("e", "ai"),)       # "e aí" conta como 2 palavras de enchimento

_PALAVRA = re.compile(r"[^\W_]+")
_SEPARADORES = " \t\r\n,.;:!?-–—…"


def _normalizar(texto: str) -> str:
    sem_acento = "".join(c for c in unicodedata.normalize("NFD", texto) if unicodedata.category(c) != "Mn")
    return sem_acento.lower()


def _fonetica(texto: str) -> str:
    """Aproximação do SOM em inglês ("green sync" ~ "grin sink"). Aplicada aos dois lados."""
    return texto.replace("ee", "i").replace("y", "i").replace("c", "k")


def _tokens(texto: str) -> list[tuple[str, int]]:
    """(palavra normalizada, posição onde ela termina no texto original)."""
    return [(_normalizar(m.group()), m.end()) for m in _PALAVRA.finditer(texto)]


def _e_enchimento(nomes: list[str], i: int) -> bool:
    return nomes[i] in ENCHIMENTO_UNICO or tuple(nomes[i:i + 2]) in ENCHIMENTO_DUPLO


def _parece(candidato: list[str], alvo: str) -> float:
    """Semelhança do candidato (1 a 3 palavras seguidas) com a palavra de ativação; 0 se não servir."""
    junto = _fonetica("".join(candidato))
    razao = SequenceMatcher(None, junto, alvo).ratio()
    if razao < RAZAO_MINIMA:
        return 0.0
    if len(candidato) > 1:
        # Palavra partida: não pode ter lixo nas pontas ("xis greensync" não vale).
        primeira, ultima = _fonetica(candidato[0]), _fonetica(candidato[-1])
        if SequenceMatcher(None, primeira, alvo[:len(primeira) + 1]).ratio() < RAZAO_PONTAS:
            return 0.0
        if SequenceMatcher(None, ultima, alvo[-(len(ultima) + 1):]).ratio() < RAZAO_PONTAS:
            return 0.0
    return razao


def analisar_ativacao(transcricao: str, palavra: str) -> tuple[bool, str]:
    """(ativada, resto). `resto` é a fala sem a palavra de ativação e sem o enchimento antes dela
    ("GreenSync, como ela está?" -> "como ela está?"); se não ativou, é a transcrição como veio."""
    transcricao = transcricao or ""
    alvo = _fonetica("".join(t for t, _ in _tokens(palavra or "")))
    tokens = _tokens(transcricao)
    if not alvo or not tokens:
        return False, transcricao
    nomes = [t for t, _ in tokens]

    i, enchimento = 0, 0
    while i < len(nomes) and enchimento < MAX_ENCHIMENTO:
        if tuple(nomes[i:i + 2]) in ENCHIMENTO_DUPLO and enchimento + 2 <= MAX_ENCHIMENTO:
            i, enchimento = i + 2, enchimento + 2
        elif nomes[i] in ENCHIMENTO_UNICO:
            i, enchimento = i + 1, enchimento + 1
        else:
            break
    if i >= len(nomes) or _e_enchimento(nomes, i):
        return False, transcricao       # só enchimento, ou enchimento demais ("ei oi ok greensync")

    melhor = None        # (semelhança, quantas palavras da fala formam a palavra de ativação)
    for n in range(1, MAX_PALAVRAS_ATIVACAO + 1):
        if i + n > len(nomes):
            break
        razao = _parece(nomes[i:i + n], alvo)
        if razao and (melhor is None or razao > melhor[0]):
            melhor = (razao, n)
    if melhor is None:
        return False, transcricao

    fim = tokens[i + melhor[1] - 1][1]
    return True, transcricao[fim:].lstrip(_SEPARADORES).strip()


def fala_ativada(transcricao: str, palavra: str) -> bool:
    """A fala começa com a palavra de ativação (com tolerância de transcrição)?"""
    return analisar_ativacao(transcricao, palavra)[0]
