"""Calcula o estado da planta a partir da leitura dos sensores.

Regra do projeto (ADR-021): quem decide se a planta está com sede
é o BACKEND, com limiares configuráveis. O Gemini só fala.
"""
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