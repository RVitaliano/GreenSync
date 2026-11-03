"""Calcula o estado da planta a partir da leitura dos sensores.

Regra do projeto (ADR-021): quem decide se a planta está com sede
é o BACKEND, com limiares configuráveis. O Gemini só fala.

Este arquivo também decide se o dado é CONFIÁVEL AGORA (frescor): se o vaso
parou de enviar leituras ou está offline, o assistente não pode falar como
se o último valor ainda fosse o de agora (REQ-FUNC-007).
"""
from datetime import datetime, timezone

from app.config import settings  # ajuste se seu objeto de config tiver outro nome


def calcular_estado(leitura: dict | None) -> dict:
    """Recebe a leitura atual (campo `leitura_atual` do Firestore).

    Devolve:
      {
        "estado": "ok" | "atencao" | "sem_dados",
        "problemas": ["solo_seco", ...]   # lista de códigos
      }
    Campos ausentes (None) são ignorados, nunca inventados.
    """
    if not leitura:
        return {"estado": "sem_dados", "problemas": []}

    problemas: list[str] = []

    solo = leitura.get("umidade_solo")
    if solo is not None:
        if solo < settings.solo_seco_abaixo:
            problemas.append("solo_seco")
        elif solo > settings.solo_encharcado_acima:
            problemas.append("solo_encharcado")

    temp = leitura.get("temperatura_ar")
    if temp is not None:
        if temp < settings.temp_min:
            problemas.append("frio")
        elif temp > settings.temp_max:
            problemas.append("calor")

    ph = leitura.get("ph")
    if ph is not None and not (settings.ph_min <= ph <= settings.ph_max):
        problemas.append("ph_fora_da_faixa")

    return {
        "estado": "atencao" if problemas else "ok",
        "problemas": problemas,
    }


def _como_datetime(valor) -> datetime | None:
    """Aceita o timestamp do Firestore (datetime). Sem fuso horário = UTC."""
    if not isinstance(valor, datetime):
        return None
    return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)


def avaliar_frescor(leitura: dict | None, agora: datetime | None = None) -> dict:
    """Diz se a leitura ainda vale como "agora".

    Devolve:
      {
        "dados": "atuais" | "desatualizados" | "sem_dados",
        "idade_s": int | None,   # segundos desde a última leitura (None = não sei)
        "offline": bool,         # o broker avisou que o vaso caiu (Last Will)
      }

    Fica "desatualizados" se o vaso está offline OU se a última leitura é mais
    velha que `leitura_velha_apos_s`. Sem `updated_at` (ex.: documento escrito à
    mão no Firestore) a idade é desconhecida e o dado NÃO é marcado como velho,
    porque o backend sempre grava esse campo nas leituras reais.
    """
    if not leitura:
        return {"dados": "sem_dados", "idade_s": None, "offline": False}

    agora = agora or datetime.now(timezone.utc)
    offline = leitura.get("status_vaso") == "offline"

    quando = _como_datetime(leitura.get("updated_at"))
    # max(0, ...) porque o relógio do servidor pode estar alguns segundos
    # atrás do relógio do Firestore, o que daria idade negativa.
    idade_s = None if quando is None else max(0, int((agora - quando).total_seconds()))

    velho = offline or (idade_s is not None and idade_s > settings.leitura_velha_apos_s)
    return {
        "dados": "desatualizados" if velho else "atuais",
        "idade_s": idade_s,
        "offline": offline,
    }


def avaliar_estado(leitura: dict | None, agora: datetime | None = None) -> dict:
    """Estado da planta + frescor do dado, num dicionário só.

    É o que o `responder` usa e o que a rota devolve em `estado`.
    """
    return {**calcular_estado(leitura), **avaliar_frescor(leitura, agora)}