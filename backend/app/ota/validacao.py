"""Validações puras do OTA: alvo, versão, sha256 e URL do binário.

Cada função devolve o valor (já normalizado) ou levanta ErroValidacao com uma
mensagem clara em português, própria para devolver ao administrador.
"""
import re
from urllib.parse import urlsplit

from app.config import settings

ALVOS = ("wroom", "s3")
VERSAO_MAX = 32
URL_MAX = 512
NOTAS_MAX = 500

_VERSAO = re.compile(r"^\d{1,6}\.\d{1,6}\.\d{1,6}(?:-[0-9A-Za-z]+(?:\.[0-9A-Za-z]+)*)?$")
_SHA256 = re.compile(r"^[0-9a-fA-F]{64}$")


class ErroValidacao(ValueError):
    """Valor recusado; a mensagem pode ser mostrada a quem chamou."""


def validar_alvo(alvo) -> str:
    if alvo not in ALVOS:
        raise ErroValidacao(f"alvo inválido (use um destes: {', '.join(ALVOS)})")
    return alvo


def validar_versao(versao) -> str:
    if not isinstance(versao, str) or len(versao) > VERSAO_MAX or not _VERSAO.fullmatch(versao):
        raise ErroValidacao('versão inválida (formato "1.0.0" ou "1.0.0-rc1", até 32 caracteres)')
    return versao


def versao_ou_none(valor) -> str | None:
    """Para dados que vêm do firmware: valor torto vira None em vez de erro."""
    try:
        return validar_versao(valor)
    except ErroValidacao:
        return None


def validar_sha256(valor) -> str:
    if not isinstance(valor, str) or not _SHA256.fullmatch(valor):
        raise ErroValidacao("sha256 inválido (64 caracteres hexadecimais)")
    return valor.lower()


def hosts_permitidos() -> tuple[str, ...]:
    """OTA_HOSTS_PERMITIDOS (separados por vírgula), em minúsculas."""
    return tuple(h.strip().lower() for h in settings.ota_hosts_permitidos.split(",") if h.strip())


def validar_url(valor) -> str:
    """Só https, host exatamente igual a um da lista, sem usuário:senha, até 512 caracteres."""
    if not isinstance(valor, str) or not valor or len(valor) > URL_MAX:
        raise ErroValidacao(f"url inválida (obrigatória, até {URL_MAX} caracteres)")
    if any(c.isspace() or ord(c) < 32 for c in valor):
        raise ErroValidacao("url inválida (sem espaços nem caracteres de controle)")
    try:
        partes = urlsplit(valor)
        host = (partes.hostname or "").lower()
        partes.port  # noqa: B018 - levanta ValueError se a porta for torta
    except ValueError:
        raise ErroValidacao("url inválida") from None
    if partes.scheme.lower() != "https":
        raise ErroValidacao("a url precisa usar https")
    if partes.username is not None or partes.password is not None:
        raise ErroValidacao("a url não pode ter usuário ou senha")
    if not host or host not in hosts_permitidos():
        raise ErroValidacao("o host da url não está na lista permitida")
    return valor


def validar_notas(valor) -> str | None:
    if valor is None:
        return None
    if not isinstance(valor, str) or len(valor) > NOTAS_MAX:
        raise ErroValidacao(f"notas inválidas (texto de até {NOTAS_MAX} caracteres)")
    return valor.strip() or None


def _chave_semver(versao: str) -> tuple:
    """Chave de ordenação semver: MAJOR.MINOR.PATCH numérico; "-rc1" vale MENOS que a versão final;
    entre sufixos, número < texto e prefixo menor < prefixo maior (como no semver.org)."""
    validar_versao(versao)
    nucleo, _, pre = versao.partition("-")
    numeros = tuple(int(n) for n in nucleo.split("."))
    if not pre:
        return (numeros, 1, ())
    ids = tuple((0, int(i), "") if i.isdigit() else (1, 0, i) for i in pre.split("."))
    return (numeros, 0, ids)


def comparar_versoes(a: str, b: str) -> int:
    """-1 se a < b, 0 se iguais, 1 se a > b. Levanta ErroValidacao se alguma não for versão válida."""
    ka, kb = _chave_semver(a), _chave_semver(b)
    return (ka > kb) - (ka < kb)


def versao_maior(a: str, b: str) -> bool:
    """True só se `a` é estritamente maior que `b` (atualizar nunca baixa de versão)."""
    return comparar_versoes(a, b) > 0
