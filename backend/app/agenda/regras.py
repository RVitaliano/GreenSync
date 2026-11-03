"""Regras puras da rega: transformam o pedido do LLM em um horário/duração e
recusam o que passa dos limites (SRS REQ-FUNC-011).

Nada aqui acessa Firestore, MQTT ou relógio: tudo entra por parâmetro, então
dá para testar cada regra isolada. O LLM só PROPÕE; quem decide é este módulo.
"""
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from app.config import settings

# Palavras que mostram que a PESSOA pediu para regar. É uma trava extra, independente
# do LLM: se o modelo "alucinar" uma rega numa pergunta que não pediu isso, a bomba
# não é acionada.
_PEDIU_REGA = re.compile(r"\b(reg[aeouáéêó]\w*|molh\w*|irrig\w*|rega)\b", re.IGNORECASE)
_HORA = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")

# Rega marcada/feita perto de outra conta para o intervalo mínimo.
STATUS_QUE_CONTAM = ("pendente", "executando", "concluida")


class Recusa(Exception):
    """Pedido recusado. `codigo` é para log/testes; `fala` é o que a planta diz."""

    def __init__(self, codigo: str, fala: str):
        super().__init__(codigo)
        self.codigo = codigo
        self.fala = fala


@dataclass(frozen=True)
class Pedido:
    quando: datetime        # UTC, com fuso
    duracao_s: int
    atraso_s: int           # segundos de agora até `quando`


def pessoa_pediu_rega(texto: str) -> bool:
    return bool(_PEDIU_REGA.search(texto or ""))


def fuso():
    return timezone(timedelta(hours=settings.fuso_utc_h))


def resolver_pedido(acao: dict, agora: datetime) -> Pedido:
    """Converte o que o LLM devolveu em (quando, duração) e confere os limites.

    `acao` = {"daqui_a_s": int|None, "as_hora": "HH:MM"|None, "duracao_s": int|None}.
    Levanta Recusa se estiver fora dos limites.
    """
    daqui_a = acao.get("daqui_a_s")
    as_hora = acao.get("as_hora")

    if as_hora:
        m = _HORA.match(str(as_hora).strip())
        if not m:
            raise Recusa("hora_invalida", "Não entendi o horário da rega. Pode repetir?")
        local = agora.astimezone(fuso())
        alvo = local.replace(hour=int(m.group(1)), minute=int(m.group(2)), second=0, microsecond=0)
        if alvo <= local:           # o horário de hoje já passou: vale o de amanhã
            alvo += timedelta(days=1)
        quando = alvo.astimezone(timezone.utc)
        atraso = int((quando - agora).total_seconds())
    else:
        atraso = 0 if daqui_a is None else int(daqui_a)
        if atraso < 0:
            raise Recusa("atraso_negativo", "Não consigo regar no passado. Pode repetir quando quer a rega?")
        quando = agora + timedelta(seconds=atraso)

    if atraso > settings.rega_atraso_max_s:
        horas = settings.rega_atraso_max_s // 3600
        raise Recusa("atraso_grande", f"Só consigo agendar a rega para as próximas {horas} horas.")

    duracao = acao.get("duracao_s")
    duracao = settings.rega_duracao_padrao_s if duracao is None else int(duracao)
    if duracao <= 0:
        raise Recusa("duracao_invalida", "A rega precisa durar pelo menos um segundo.")
    if duracao > settings.rega_duracao_max_s:
        raise Recusa("duracao_grande",
                     f"Uma rega pode durar no máximo {settings.rega_duracao_max_s} segundos.")

    return Pedido(quando=quando, duracao_s=duracao, atraso_s=max(atraso, 0))


def checar_regras(pedido: Pedido, leitura: dict | None, estado: dict, vizinhos: list[dict]) -> None:
    """Regras que dependem do estado do vaso e das outras regas. Levanta Recusa."""
    # Sem leitura nenhuma, o vaso nunca falou com a gente: não dá para garantir que ouve o comando.
    if leitura is None or estado.get("dados") == "sem_dados":
        raise Recusa("sem_dados", "Não tenho notícias do vaso, então não vou arriscar regar.")
    if estado.get("offline"):
        raise Recusa("offline", "Não consigo regar agora porque o vaso está desconectado.")

    # Solo encharcado e bomba ligada só importam para regas "de agora": para uma rega
    # daqui a horas, o solo de agora não diz nada (a checagem é refeita na hora de regar).
    perto = pedido.atraso_s < settings.rega_intervalo_min_s
    if perto:
        solo = leitura.get("umidade_solo")
        if isinstance(solo, (int, float)) and solo > settings.solo_encharcado_acima:
            raise Recusa("solo_encharcado", "Meu solo já está encharcado, melhor não regar agora.")
        if pedido.atraso_s == 0 and leitura.get("bomba_ligada") is True:
            raise Recusa("bomba_ligada", "Minha bomba já está ligada neste momento.")

    minimo = settings.rega_intervalo_min_s
    for v in vizinhos:
        if v.get("status") in STATUS_QUE_CONTAM:
            distancia = abs((v["quando"] - pedido.quando).total_seconds())
            if distancia < minimo:
                raise Recusa("intervalo",
                             f"Já tem uma rega perto desse horário. Preciso de pelo menos "
                             f"{minimo // 60} minutos entre uma e outra.")