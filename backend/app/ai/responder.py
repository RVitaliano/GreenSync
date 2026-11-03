"""Única porta de entrada para o LLM (ADR-018).

Todo o resto do backend chama `responder(...)` (texto) ou `responder_audio(...)`
(pergunta falada). Se um dia trocarmos Gemini por Groq, só o INTERIOR destas
funções muda. Retry, timeout e modelo reserva ficam em `resiliencia.py`.

As duas devolvem, além da resposta, `acao`: o pedido de rega/cancelamento que o
modelo entendeu (ou None). O modelo só propõe; quem valida e executa é o
backend (app/agenda).
"""
import json
import logging
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.ai.estado import avaliar_estado
from app.ai.prompt import montar_system_prompt
from app.ai.resiliencia import IAError, tentar_modelos  # IAError é re-exportado daqui
from app.config import settings

log = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Cria o cliente uma vez só e reaproveita (também usado por voz.py)."""
    global _client
    if not settings.gemini_api_key:
        raise IAError("GEMINI_API_KEY não configurada no .env")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _modelos() -> list[str]:
    """Principal primeiro, reserva depois (sem repetir)."""
    modelos = [settings.gemini_model]
    reserva = settings.gemini_model_fallback
    if reserva and reserva != settings.gemini_model:
        modelos.append(reserva)
    return modelos


async def _gerar(contents, config, timeout_s: float) -> tuple[str, str]:
    """Chama o Gemini (com retry/reserva) e devolve (texto, modelo)."""
    client = get_client()  # levanta IAError se faltar a chave

    def chamar(modelo: str):
        return client.aio.models.generate_content(
            model=modelo, contents=contents, config=config
        )

    def extrair(resp) -> str:
        return (resp.text or "").strip()

    return await tentar_modelos(_modelos(), chamar, extrair, timeout_s, "Gemini")


# ------------------------------------------------------------ saída em JSON ----

# Atenção: os campos opcionais abaixo ficam SEM valor padrão de propósito (o schema
# do Gemini não aceita `default`). As docstrings das classes são enviadas ao modelo.
class AcaoRega(BaseModel):
    """Pedido de rega ou de cancelamento feito pela pessoa."""
    tipo: Literal["nenhuma", "regar", "cancelar"]
    daqui_a_s: Optional[int]
    as_hora: Optional[str]
    duracao_s: Optional[int]


class SaidaTexto(BaseModel):
    """Formato que pedimos ao Gemini quando a pergunta chega em texto."""
    resposta: str
    acao: AcaoRega


class SaidaAudio(BaseModel):
    """Formato que pedimos ao Gemini quando a pergunta chega em áudio."""
    pergunta_ouvida: str
    resposta: str
    acao: AcaoRega


def _inteiro(valor) -> int | None:
    """Número inteiro, ou None se vier outra coisa (texto, bool, nulo...)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return None


def _ler_acao(bruta) -> dict | None:
    """Pedido de rega em dicionário limpo, ou None se não houver pedido (ou vier torto)."""
    if not isinstance(bruta, dict) or bruta.get("tipo") not in ("regar", "cancelar"):
        return None
    hora = bruta.get("as_hora")
    return {
        "tipo": bruta["tipo"],
        "daqui_a_s": _inteiro(bruta.get("daqui_a_s")),
        "as_hora": hora.strip() if isinstance(hora, str) and hora.strip() else None,
        "duracao_s": _inteiro(bruta.get("duracao_s")),
    }


def ler_saida(bruto: str) -> tuple[str, str, dict | None]:
    """Extrai (pergunta_ouvida, resposta, acao) do JSON devolvido pelo Gemini.

    Tolera cerca de markdown (```json) e, se o modelo ignorar o JSON e devolver
    só texto, usa esse texto como resposta, sem pergunta ouvida e SEM ação:
    na dúvida, a bomba não é acionada.
    """
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    try:
        dados = json.loads(texto)
    except ValueError:
        return "", bruto.strip(), None
    if not isinstance(dados, dict):
        return "", bruto.strip(), None
    pergunta = str(dados.get("pergunta_ouvida") or "").strip()
    resposta = str(dados.get("resposta") or "").strip()
    return pergunta, resposta, _ler_acao(dados.get("acao"))


# ------------------------------------------------------------------ texto -----

async def responder(pergunta: str, leitura: dict | None) -> dict:
    """Responde `pergunta` (texto) como a planta, com base na `leitura` atual.

    Devolve {"texto", "acao", "estado", "modelo"}; `acao` é o pedido de rega
    entendido (dict) ou None. Levanta IAError se todos os modelos falharem.
    """
    # Estado da planta + se o dado ainda vale como "agora" (vaso offline / leitura velha).
    estado = avaliar_estado(leitura)
    config = types.GenerateContentConfig(
        system_instruction=montar_system_prompt(leitura, estado),
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=SaidaTexto,
        # Sem max_output_tokens de propósito: em modelos com "thinking",
        # um limite baixo pode consumir tudo no raciocínio e vir vazio.
    )
    bruto, modelo = await _gerar(pergunta, config, settings.gemini_timeout_s)

    _, texto, acao = ler_saida(bruto)
    if not texto:
        raise IAError(f"{modelo}: resposta vazia")
    return {"texto": texto, "acao": acao, "estado": estado, "modelo": modelo}


# ------------------------------------------------------------------ áudio -----

async def responder_audio(audio: bytes, mime: str, leitura: dict | None) -> dict:
    """Entende uma pergunta FALADA e responde como a planta (ADR-018, camada 2).

    O Gemini ouve o áudio direto (sem STT separado) e devolve o que ouviu, a
    resposta e o pedido de rega, se houver.

    Devolve {"texto", "pergunta_ouvida", "acao", "estado", "modelo"}.
    Levanta IAError se todos os modelos falharem ou se a resposta vier vazia.
    """
    estado = avaliar_estado(leitura)
    config = types.GenerateContentConfig(
        system_instruction=montar_system_prompt(leitura, estado, audio=True),
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=SaidaAudio,
    )
    contents = [
        types.Part.from_bytes(data=audio, mime_type=mime),
        "Responda à pergunta falada neste áudio.",
    ]
    bruto, modelo = await _gerar(contents, config, settings.gemini_timeout_audio_s)
"""Única porta de entrada para o LLM (ADR-018).

Todo o resto do backend chama `responder(...)` (texto) ou `responder_audio(...)`
(pergunta falada). Se um dia trocarmos Gemini por Groq, só o INTERIOR destas
funções muda. Retry, timeout e modelo reserva ficam em `resiliencia.py`.

As duas devolvem, além da resposta, `acao`: o pedido de rega/cancelamento que o
modelo entendeu (ou None). O modelo só propõe; quem valida e executa é o
backend (app/agenda).
"""
import json
import logging
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel

from app.ai.estado import avaliar_estado
from app.ai.prompt import montar_system_prompt
from app.ai.resiliencia import IAError, tentar_modelos  # IAError é re-exportado daqui
from app.config import settings

log = logging.getLogger(__name__)

_client: genai.Client | None = None


def get_client() -> genai.Client:
    """Cria o cliente uma vez só e reaproveita (também usado por voz.py)."""
    global _client
    if not settings.gemini_api_key:
        raise IAError("GEMINI_API_KEY não configurada no .env")
    if _client is None:
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def _modelos() -> list[str]:
    """Principal primeiro, reserva depois (sem repetir)."""
    modelos = [settings.gemini_model]
    reserva = settings.gemini_model_fallback
    if reserva and reserva != settings.gemini_model:
        modelos.append(reserva)
    return modelos


async def _gerar(contents, config, timeout_s: float) -> tuple[str, str]:
    """Chama o Gemini (com retry/reserva) e devolve (texto, modelo)."""
    client = get_client()  # levanta IAError se faltar a chave

    def chamar(modelo: str):
        return client.aio.models.generate_content(
            model=modelo, contents=contents, config=config
        )

    def extrair(resp) -> str:
        return (resp.text or "").strip()

    return await tentar_modelos(_modelos(), chamar, extrair, timeout_s, "Gemini")


# ------------------------------------------------------------ saída em JSON ----

# Atenção: os campos opcionais abaixo ficam SEM valor padrão de propósito (o schema
# do Gemini não aceita `default`). As docstrings das classes são enviadas ao modelo.
class AcaoRega(BaseModel):
    """Pedido de rega ou de cancelamento feito pela pessoa."""
    tipo: Literal["nenhuma", "regar", "cancelar"]
    daqui_a_s: Optional[int]
    as_hora: Optional[str]
    duracao_s: Optional[int]


class SaidaTexto(BaseModel):
    """Formato que pedimos ao Gemini quando a pergunta chega em texto."""
    resposta: str
    acao: AcaoRega


class SaidaAudio(BaseModel):
    """Formato que pedimos ao Gemini quando a pergunta chega em áudio."""
    pergunta_ouvida: str
    resposta: str
    acao: AcaoRega


def _inteiro(valor) -> int | None:
    """Número inteiro, ou None se vier outra coisa (texto, bool, nulo...)."""
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    if isinstance(valor, float) and valor.is_integer():
        return int(valor)
    return None


def _ler_acao(bruta) -> dict | None:
    """Pedido de rega em dicionário limpo, ou None se não houver pedido (ou vier torto)."""
    if not isinstance(bruta, dict) or bruta.get("tipo") not in ("regar", "cancelar"):
        return None
    hora = bruta.get("as_hora")
    return {
        "tipo": bruta["tipo"],
        "daqui_a_s": _inteiro(bruta.get("daqui_a_s")),
        "as_hora": hora.strip() if isinstance(hora, str) and hora.strip() else None,
        "duracao_s": _inteiro(bruta.get("duracao_s")),
    }


def ler_saida(bruto: str) -> tuple[str, str, dict | None]:
    """Extrai (pergunta_ouvida, resposta, acao) do JSON devolvido pelo Gemini.

    Tolera cerca de markdown (```json) e, se o modelo ignorar o JSON e devolver
    só texto, usa esse texto como resposta, sem pergunta ouvida e SEM ação:
    na dúvida, a bomba não é acionada.
    """
    texto = bruto.strip()
    if texto.startswith("```"):
        texto = texto.strip("`")
        if texto.lower().startswith("json"):
            texto = texto[4:]
        texto = texto.strip()
    try:
        dados = json.loads(texto)
    except ValueError:
        return "", bruto.strip(), None
    if not isinstance(dados, dict):
        return "", bruto.strip(), None
    pergunta = str(dados.get("pergunta_ouvida") or "").strip()
    resposta = str(dados.get("resposta") or "").strip()
    return pergunta, resposta, _ler_acao(dados.get("acao"))


# ------------------------------------------------------------------ texto -----

async def responder(pergunta: str, leitura: dict | None, historico: list[dict] | None = None) -> dict:
    """Responde `pergunta` (texto) como a planta, com base na `leitura` atual.

    `historico` = últimas trocas da conversa (app/contexto.py), só para entender referências.

    Devolve {"texto", "acao", "estado", "modelo"}; `acao` é o pedido de rega
    entendido (dict) ou None. Levanta IAError se todos os modelos falharem.
    """
    # Estado da planta + se o dado ainda vale como "agora" (vaso offline / leitura velha).
    estado = avaliar_estado(leitura)
    config = types.GenerateContentConfig(
        system_instruction=montar_system_prompt(leitura, estado, historico=historico),
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=SaidaTexto,
        # Sem max_output_tokens de propósito: em modelos com "thinking",
        # um limite baixo pode consumir tudo no raciocínio e vir vazio.
    )
    bruto, modelo = await _gerar(pergunta, config, settings.gemini_timeout_s)

    _, texto, acao = ler_saida(bruto)
    if not texto:
        raise IAError(f"{modelo}: resposta vazia")
    return {"texto": texto, "acao": acao, "estado": estado, "modelo": modelo}


# ------------------------------------------------------------------ áudio -----

async def responder_audio(audio: bytes, mime: str, leitura: dict | None,
                          historico: list[dict] | None = None) -> dict:
    """Entende uma pergunta FALADA e responde como a planta (ADR-018, camada 2).

    O Gemini ouve o áudio direto (sem STT separado) e devolve o que ouviu, a
    resposta e o pedido de rega, se houver.

    Devolve {"texto", "pergunta_ouvida", "acao", "estado", "modelo"}.
    Levanta IAError se todos os modelos falharem ou se a resposta vier vazia.
    """
    estado = avaliar_estado(leitura)
    config = types.GenerateContentConfig(
        system_instruction=montar_system_prompt(leitura, estado, audio=True, historico=historico),
        temperature=0.7,
        response_mime_type="application/json",
        response_schema=SaidaAudio,
    )
    contents = [
        types.Part.from_bytes(data=audio, mime_type=mime),
        "Responda à pergunta falada neste áudio.",
    ]
    bruto, modelo = await _gerar(contents, config, settings.gemini_timeout_audio_s)

    pergunta, texto, acao = ler_saida(bruto)
    if not texto:
        raise IAError(f"{modelo}: resposta vazia")
    if not pergunta:
        acao = None   # sem fala transcrita não existe pedido: nunca age sobre ruído/silêncio
    return {"texto": texto, "pergunta_ouvida": pergunta, "acao": acao, "estado": estado, "modelo": modelo}
    pergunta, texto, acao = ler_saida(bruto)
    if not texto:
        raise IAError(f"{modelo}: resposta vazia")
    if not pergunta:
        acao = None   # sem fala transcrita não existe pedido: nunca age sobre ruído/silêncio
    return {"texto": texto, "pergunta_ouvida": pergunta, "acao": acao, "estado": estado, "modelo": modelo}