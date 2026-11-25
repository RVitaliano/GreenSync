"""Validações puras do OTA."""
import pytest

from app.config import settings
from app.ota import validacao as v

HASH = "a" * 64


@pytest.mark.parametrize("alvo", ["wroom", "s3"])
def test_alvo_valido(alvo):
    assert v.validar_alvo(alvo) == alvo


@pytest.mark.parametrize("alvo", ["", "WROOM", "esp32", "s3 ", None, 3])
def test_alvo_invalido(alvo):
    with pytest.raises(v.ErroValidacao):
        v.validar_alvo(alvo)


@pytest.mark.parametrize("versao", ["1.0.0", "0.0.1", "12.34.56", "1.0.0-rc1", "1.0.0-beta.2", "1.0.0-" + "a" * 20])
def test_versao_valida(versao):
    assert v.validar_versao(versao) == versao


@pytest.mark.parametrize("versao", [
    "", "1", "1.0", "v1.0.0", "1.0.0.0", "1.0.0-", "1.0.0 rc1", "1.0.0-rc_1", "a.b.c",
    "1.0.0-" + "a" * 30,          # passa de 32 caracteres
    None, 1.0, "1.0.0\n",
])
def test_versao_invalida(versao):
    with pytest.raises(v.ErroValidacao):
        v.validar_versao(versao)


def test_versao_ou_none():
    assert v.versao_ou_none("1.2.3") == "1.2.3"
    assert v.versao_ou_none("lixo") is None
    assert v.versao_ou_none(5) is None


def test_sha256_valido_e_normalizado_para_minusculas():
    assert v.validar_sha256("ABCDEF0123456789" * 4) == "abcdef0123456789" * 4


@pytest.mark.parametrize("h", ["", "abc", "a" * 63, "a" * 65, "g" * 64, " " + "a" * 63, "a" * 64 + "\n", None, 123])
def test_sha256_invalido(h):
    with pytest.raises(v.ErroValidacao):
        v.validar_sha256(h)


URL_OK = "https://github.com/org/repo/releases/download/v1/firmware.bin"


def test_url_valida():
    assert v.validar_url(URL_OK) == URL_OK
    assert v.validar_url("https://GitHub.com/x.bin")        # host sem diferenciar maiúsculas


@pytest.mark.parametrize("url", [
    "http://github.com/x.bin",                    # sem https
    "ftp://github.com/x.bin",
    "//github.com/x.bin",
    "https://evil.com/x.bin",                     # host fora da lista
    "https://github.com.evil.com/x.bin",
    "https://sub.github.com/x.bin",               # subdomínio não vale
    "https://user:senha@github.com/x.bin",        # credenciais embutidas
    "https://user@github.com/x.bin",
    "https://github.com:abc/x.bin",               # porta torta
    "https://github.com/x .bin",
    "https://github.com/x.bin\n",
    "https:///x.bin",
    "", None, 5,
    "https://github.com/" + "a" * 520,            # maior que 512
])
def test_url_invalida(url):
    with pytest.raises(v.ErroValidacao):
        v.validar_url(url)


def test_url_no_limite_de_512_passa():
    url = "https://github.com/" + "a" * (512 - len("https://github.com/"))
    assert len(url) == 512 and v.validar_url(url) == url


def test_hosts_vem_da_configuracao_separados_por_virgula(monkeypatch):
    monkeypatch.setattr(settings, "ota_hosts_permitidos", " Github.com , cdn.exemplo.com ,")
    assert v.hosts_permitidos() == ("github.com", "cdn.exemplo.com")
    assert v.validar_url("https://cdn.exemplo.com/f.bin")
    with pytest.raises(v.ErroValidacao):
        v.validar_url("https://outro.com/f.bin")


def test_padrao_dos_hosts_e_so_github():
    assert v.hosts_permitidos() == ("github.com",)


def test_lista_de_hosts_vazia_recusa_tudo(monkeypatch):
    monkeypatch.setattr(settings, "ota_hosts_permitidos", "")
    with pytest.raises(v.ErroValidacao):
        v.validar_url(URL_OK)


def test_notas():
    assert v.validar_notas(None) is None
    assert v.validar_notas("  corrige bug  ") == "corrige bug"
    assert v.validar_notas("   ") is None
    assert v.validar_notas("a" * 500) == "a" * 500
    with pytest.raises(v.ErroValidacao):
        v.validar_notas("a" * 501)
    with pytest.raises(v.ErroValidacao):
        v.validar_notas(5)
