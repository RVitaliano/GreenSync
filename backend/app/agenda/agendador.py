"""Executa as regas no horário certo, sem nunca duplicar (REQ-FUNC-012).

Uma tarefa asyncio por agendamento. A ordem que garante "no máximo uma vez":

  1. reivindicar: pendente -> executando (transação; só uma tentativa passa)
  2. conferir de novo se o vaso está online e o solo não está encharcado
  3. publicar o comando MQTT
  4. executando -> concluida (ou falhou)

O status "executando" é gravado ANTES de publicar. Se o backend cair no meio,
a rega pode ser perdida (aceitável), mas nunca repetida.
"""
import asyncio
import logging
from datetime import datetime, timezone

from app.agenda.regras import MOTIVO_INCERTO, Pedido
from app.ai.estado import avaliar_estado
from app.config import settings

log = logging.getLogger("greensync.agenda")

PASSO_MAX_S = 30   # a espera é feita em passos curtos, conferindo o relógio a cada um


def _agora() -> datetime:
    return datetime.now(timezone.utc)


class Agendador:
    """`repo`, `publicar` e `ler_leitura` entram por parâmetro: nos testes são falsos."""

    def __init__(self, repo, publicar, ler_leitura, relogio=_agora):
        self.repo = repo
        self.publicar = publicar          # async (device_id, payload: dict) -> None
        self.ler_leitura = ler_leitura    # async (device_id) -> dict | None
        self.agora = relogio
        self._tarefas: dict[str, asyncio.Task] = {}
        # Serializa "conferir regras + gravar": dois pedidos ao mesmo tempo não
        # furam o intervalo mínimo um do outro.
        self.trava = asyncio.Lock()

    # ---------------------------------------------------------------- agenda --

    async def agendar(self, device_id: str, pedido: Pedido, origem: str) -> str:
        """Grava como pendente e começa a contar. Devolve o id do agendamento."""
        ag_id = await self.repo.criar(device_id, pedido.quando, pedido.duracao_s, origem)
        self._iniciar_tarefa(device_id, ag_id, pedido.quando, pedido.duracao_s)
        log.info("[%s] rega %s agendada para %s (%ds, origem=%s)",
                 device_id, ag_id, pedido.quando.isoformat(), pedido.duracao_s, origem)
        return ag_id

    async def aguardar(self, device_id: str, ag_id: str, timeout_s: float = 8.0) -> tuple[str, str | None] | None:
        """Espera uma rega "de agora" terminar. Devolve (status, motivo), ou None se demorar."""
        tarefa = self._tarefas.get(f"{device_id}/{ag_id}")
        if tarefa is None:
            return None
        try:
            return await asyncio.wait_for(asyncio.shield(tarefa), timeout_s)
        except asyncio.TimeoutError:
            return None
        except asyncio.CancelledError:
            if tarefa.cancelled():      # a rega foi cancelada enquanto esperávamos
                return None
            raise

    async def cancelar_proxima(self, device_id: str) -> tuple[dict, int] | None:
        """Cancela a rega pendente mais próxima. Devolve (agendamento, quantas ainda restam)."""
        pendentes = sorted(await self.repo.por_status(device_id, "pendente"), key=lambda a: a["quando"])
        for i, alvo in enumerate(pendentes):
            # Se a rega já foi reivindicada neste instante, mudar_status devolve False: segue para a próxima.
            if await self.repo.mudar_status(device_id, alvo["id"], ("pendente",), "cancelada"):
                tarefa = self._tarefas.pop(f"{device_id}/{alvo['id']}", None)
                if tarefa:
                    tarefa.cancel()
                log.info("[%s] rega %s cancelada", device_id, alvo["id"])
                return alvo, len(pendentes) - i - 1
        return None

    # --------------------------------------------------------------- startup --

    async def iniciar(self) -> None:
        """Recarrega as regas ao subir o backend (chamado uma vez no lifespan)."""
        for device_id in await self.repo.devices():
            # Um vaso (ou um documento) com problema não pode impedir que as regas
            # dos outros sejam recarregadas: senão elas ficariam paradas até o próximo reinício.
            try:
                await self._recarregar(device_id)
            except Exception:
                log.exception("[%s] não consegui recarregar as regas deste vaso", device_id)
        log.info("Agendador iniciado: %d rega(s) pendente(s)", len(self._tarefas))

    async def _recarregar(self, device_id: str) -> None:
        # Ficou "executando" quando o processo caiu: não sabemos se o comando saiu.
        # Marcar como falhou é o lado seguro (nunca repete).
        for ag in await self.repo.por_status(device_id, "executando"):
            await self.repo.mudar_status(device_id, ag["id"], ("executando",), "falhou",
                                         "interrompida por reinício do backend")
            log.warning("[%s] rega %s estava executando no reinício: marcada como falhou",
                        device_id, ag["id"])
        for ag in await self.repo.por_status(device_id, "pendente"):
            try:
                self._iniciar_tarefa(device_id, ag["id"], ag["quando"],
                                     ag.get("duracao_s", settings.rega_duracao_padrao_s))
            except Exception:
                log.exception("[%s] rega %s com dados inválidos, ignorada", device_id, ag.get("id"))

    async def parar(self) -> None:
        """Para as contagens (as regas continuam `pendente` no Firestore e voltam no próximo start)."""
        tarefas = list(self._tarefas.values())
        for t in tarefas:
            t.cancel()
        await asyncio.gather(*tarefas, return_exceptions=True)
        self._tarefas.clear()

    # ------------------------------------------------------------- execução ---

    def _iniciar_tarefa(self, device_id: str, ag_id: str, quando: datetime, duracao_s: int) -> None:
        chave = f"{device_id}/{ag_id}"
        if chave in self._tarefas:      # já está contando (ex.: iniciar() chamado duas vezes)
            return
        tarefa = asyncio.create_task(self._rodar(device_id, ag_id, quando, duracao_s))
        self._tarefas[chave] = tarefa

        def _limpar(t: asyncio.Task) -> None:
            if self._tarefas.get(chave) is t:
                del self._tarefas[chave]

        tarefa.add_done_callback(_limpar)

    async def _rodar(self, device_id: str, ag_id: str, quando: datetime, duracao_s: int):
        """Espera a hora, confere a tolerância e dispara. Devolve (status, motivo)."""
        try:
            while True:
                falta = (quando - self.agora()).total_seconds()
                if falta <= 0:
                    break
                await asyncio.sleep(min(falta, PASSO_MAX_S))

            atraso = (self.agora() - quando).total_seconds()
            if atraso > settings.rega_tolerancia_s:
                await self.repo.mudar_status(device_id, ag_id, ("pendente",), "expirada",
                                             f"passou {int(atraso)}s do horário")
                log.warning("[%s] rega %s expirada (atraso de %ds)", device_id, ag_id, atraso)
                return "expirada", f"passou {int(atraso)}s do horário"
            return await self._disparar(device_id, ag_id, duracao_s)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("[%s] erro inesperado na rega %s", device_id, ag_id)
            # Se o erro veio depois de reivindicar, o documento ficaria "executando" até o
            # próximo reinício (e contando para o intervalo mínimo). Antes da reivindicação
            # o status é "pendente" e esta chamada não muda nada.
            try:
                await self.repo.mudar_status(device_id, ag_id, ("executando",), "falhou", "erro interno")
            except Exception:
                log.exception("[%s] não consegui marcar a rega %s como falhou", device_id, ag_id)
            return "falhou", "erro interno"

    async def _disparar(self, device_id: str, ag_id: str, duracao_s: int) -> tuple[str, str | None]:
        # 1) Reivindica ANTES de publicar: quem perder aqui não faz nada.
        if not await self.repo.mudar_status(device_id, ag_id, ("pendente",), "executando"):
            log.info("[%s] rega %s já não está pendente (cancelada ou tratada por outro): ignorada", device_id, ag_id)
            return "ignorada", None

        # 2) Confere de novo na hora: o vaso pode ter caído ou o solo encharcado desde o pedido.
        motivo = None
        # Defesa em profundidade: a duração vem do Firestore (que o app também escreve).
        # Valor torto ou acima do limite configurado nunca vira comando para a bomba.
        if (isinstance(duracao_s, bool) or not isinstance(duracao_s, int)
                or duracao_s <= 0 or duracao_s > settings.rega_duracao_max_s):
            motivo = "a duração da rega é inválida"
            await self.repo.mudar_status(device_id, ag_id, ("executando",), "falhou", motivo)
            log.warning("[%s] rega %s não executada: duração inválida (%r)", device_id, ag_id, duracao_s)
            return "falhou", motivo

        leitura = await self.ler_leitura(device_id)
        estado = avaliar_estado(leitura)
        solo = (leitura or {}).get("umidade_solo")
        if leitura is None or estado.get("offline"):
            motivo = "o vaso está desconectado"
        elif isinstance(solo, (int, float)) and solo > settings.solo_encharcado_acima:
            motivo = "o solo já está encharcado"
        if motivo:
            await self.repo.mudar_status(device_id, ag_id, ("executando",), "falhou", motivo)
            log.warning("[%s] rega %s não executada: %s", device_id, ag_id, motivo)
            return "falhou", motivo

        # 3) Publica o comando (o firmware ainda aplica o próprio tempo máximo).
        try:
            await self.publicar(device_id, {"acao": "regar", "duracao_s": duracao_s, "id": ag_id})
        except Exception as e:
            motivo = MOTIVO_INCERTO if getattr(e, "incerta", False) else "não consegui falar com o broker"
            await self.repo.mudar_status(device_id, ag_id, ("executando",), "falhou", motivo)
            log.error("[%s] rega %s: publicação falhou: %s", device_id, ag_id, e)
            return "falhou", motivo

        log.info("[%s] rega %s: comando publicado (%ds)", device_id, ag_id, duracao_s)
        # O comando JÁ saiu. Se o Firestore falhar aqui, nunca devolvemos "falhou" (a pessoa
        # seria avisada de que não regou, e o erro genérico ainda reescreveria o status):
        # tenta de novo e, se não der, o documento fica "executando", que também conta no
        # intervalo mínimo e vira "falhou" só no próximo reinício.
        for tentativa in (1, 2):
            try:
                await self.repo.mudar_status(device_id, ag_id, ("executando",), "concluida")
                break
            except Exception:
                log.exception("[%s] rega %s: não consegui gravar 'concluida' (tentativa %d)",
                              device_id, ag_id, tentativa)
        return "concluida", None