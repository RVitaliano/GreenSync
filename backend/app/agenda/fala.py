"""Frases que a planta fala ao confirmar, recusar ou cancelar uma rega.

São escritas pelo backend (não pelo LLM) de propósito: a confirmação precisa
dizer exatamente o que foi agendado (horário e duração reais) e a recusa precisa
ser verdadeira. O LLM só entende o pedido.
"""
from datetime import datetime

from app.agenda.regras import fuso


def _plural(n: int, singular: str, plural: str) -> str:
    return f"{n} {singular if n == 1 else plural}"


def falar_duracao(seg: int) -> str:
    return _plural(seg, "segundo", "segundos")


def _hora_local(quando: datetime) -> str:
    """'15:30' no horário do usuário, sem zero à esquerda na hora ('8:05')."""
    l = quando.astimezone(fuso())
    return f"{l.hour}:{l.minute:02d}"


def falar_quando(quando: datetime, atraso_s: int) -> str:
    """'agora', 'daqui a 5 minutos' ou 'às 15:30' (para mais de 1 hora)."""
    if atraso_s < 5:
        return "agora"
    if atraso_s < 60:
        return "daqui a " + _plural(atraso_s, "segundo", "segundos")
    if atraso_s < 3600:
        return "daqui a " + _plural(round(atraso_s / 60), "minuto", "minutos")
    return "às " + _hora_local(quando)


def confirmacao(quando: datetime, atraso_s: int, duracao_s: int) -> str:
    quando_txt = falar_quando(quando, atraso_s)
    if quando_txt == "agora":
        return f"Pode deixar, vou me regar agora por {falar_duracao(duracao_s)}."
    return f"Combinado, vou regar {quando_txt} por {falar_duracao(duracao_s)}."


def cancelamento(quando: datetime, restantes: int) -> str:
    texto = f"Pronto, cancelei a rega das {_hora_local(quando)}."
    if restantes > 0:
        texto += " Ainda " + ("tem" if restantes == 1 else "têm") + f" {restantes} " + \
                 ("marcada." if restantes == 1 else "marcadas.")
    return texto


NADA_A_CANCELAR = "Não tem nenhuma rega marcada para cancelar."
NAO_ENTENDI = "Não entendi se você queria me regar. Pode repetir o pedido?"
NAO_ENTENDI_CANCELAR = "Não entendi se você queria cancelar a rega. Pode repetir o pedido?"
ERRO ="Não consegui marcar a rega agora. Tente de novo em instantes."


def falha_na_hora(motivo: str) -> str:
    return f"Tentei me regar, mas não consegui: {motivo}."