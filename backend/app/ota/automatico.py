"""OTA automático: manda "atualizar" sozinho quando há versão nova para um vaso (OTA_AUTO).

Dois gatilhos, uma única função de despacho (`despachar_automatico`), que só decide SE vale a
pena e depois reaproveita `servico.solicitar_atualizacao` (a mesma da rota /atualizar), com todas
as recusas dela (offline, bomba_ligada, versao_igual, ota_em_curso...):

  - PUT /firmware/{alvo}: despacha para cada vaso online com versão menor;
  - status MQTT "online": confere o vaso que acabou de ficar online.

O automático só SOBE de versão (semver) e desiste de uma mesma versão depois de
OTA_AUTO_TENTATIVAS tentativas (devices/{id}.ota_auto). Nada aqui atrasa quem chamou: os dois
gatilhos rodam em segundo plano.
"""
import asyncio
import logging

from app.ai.estado import avaliar_estado
from app.config import settings
from app.firebase_client import ler_leitura_segura
from app.ota import repositorio, servico, validacao

log = logging.getLogger("greensync.ota")

_tarefas: set[asyncio.Task] = set()


def _ignorada(motivo: str) -> dict:
    return {"resultado": "ignorada", "id": None, "motivo": motivo, "versao": None}


def em_segundo_plano(coro) -> asyncio.Task:
    """Roda `coro` sem esperar. Guarda a referência (senão o loop pode descartar a tarefa)."""
    tarefa = asyncio.create_task(coro)
    _tarefas.add(tarefa)

    def _fim(t: asyncio.Task) -> None:
        _tarefas.discard(t)
        if not t.cancelled() and t.exception() is not None:
            log.error("OTA automático: erro em segundo plano: %r", t.exception())

    tarefa.add_done_callback(_fim)
    return tarefa


async def aguardar_pendentes() -> None:
    """Espera as tarefas em segundo plano terminarem (usado nos testes e ao desligar)."""
    if _tarefas:
        await asyncio.gather(*list(_tarefas), return_exceptions=True)


async def despachar_automatico(device_id: str, alvo: str, *, registro: dict | None = None,
                               dispositivo: dict | None = None) -> dict:
    """Pede a atualização de `alvo` a este vaso SE as regras do automático permitirem.

    Devolve o resultado do serviço ({"resultado": "solicitada"|"recusada"|"falhou", ...}) ou
    {"resultado": "ignorada", "motivo": ...} quando nem chegou a tentar.
    """
    if not settings.ota_auto:
        return _ignorada("ota_auto_desligado")

    if registro is None:
        registro = await repositorio.ler(alvo)
    if not registro:
        return _ignorada("sem_firmware")
    if dispositivo is None:
        dispositivo = await repositorio.ler_dispositivo(device_id) or {}

    try:
        versao = validacao.validar_versao(registro.get("versao"))
    except validacao.ErroValidacao:
        return _ignorada("firmware_invalido")
    if versao in (registro.get("bloqueadas") or []):
        return _ignorada("bloqueada")

    # Só sobe de versão. Versão instalada desconhecida ou torta: não dá para saber, não mexe.
    instalada = dispositivo.get(servico.CAMPO_VERSAO[alvo])
    try:
        if not isinstance(instalada, str) or not validacao.versao_maior(versao, instalada):
            return _ignorada("sem_versao_menor")
    except validacao.ErroValidacao:
        return _ignorada("versao_instalada_invalida")

    if repositorio.ota_em_curso(dispositivo.get("ota"), repositorio._agora(), settings.ota_timeout_s):
        return _ignorada("ota_em_curso")

    entrada = repositorio.entrada_auto(dispositivo, alvo)
    tentativas = int(entrada.get("tentativas") or 0) if entrada and entrada.get("versao") == versao else 0
    if tentativas >= settings.ota_auto_tentativas:
        return _ignorada("tentativas_esgotadas")

    leitura = await ler_leitura_segura(device_id)
    resultado = await servico.solicitar_atualizacao(device_id, alvo, leitura, avaliar_estado(leitura))

    if resultado["resultado"] == "recusada" and resultado.get("motivo") in MOTIVOS_RETENTAVEIS:
        _marcar_pendente(device_id, alvo)       # tenta de novo na próxima leitura do vaso

    # Só conta tentativa quando um comando foi mesmo publicado (ou falhou ao publicar).
    if resultado["resultado"] in ("solicitada", "falhou"):
        erro = resultado["motivo"] if resultado["resultado"] == "falhou" else None
        await repositorio.registrar_tentativa_auto(device_id, alvo, versao, erro)
    log.info("[%s] OTA automático %s %s: %s%s", device_id, alvo, versao, resultado["resultado"],
             f" ({resultado['motivo']})" if resultado.get("motivo") else "")
    return resultado


async def despachar_para_vasos_online(alvo: str) -> None:
    """Depois de registrar uma versão nova: tenta cada vaso online (o filtro "menor" é do despacho)."""
    if not settings.ota_auto:
        return
    try:
        registro = await repositorio.ler(alvo)
        vasos = await repositorio.listar_dispositivos()
    except Exception:
        log.exception("OTA automático: não consegui listar os vasos de %s", alvo)
        return
    for device_id, dispositivo in vasos:
        if dispositivo.get("status") != "online":
            continue
        try:
            await despachar_automatico(device_id, alvo, registro=registro, dispositivo=dispositivo)
        except Exception:
            log.exception("[%s] OTA automático: erro ao despachar %s", device_id, alvo)


async def verificar_vaso_online(device_id: str) -> None:
    """O vaso acabou de ficar online: zera as tentativas se já está na versão do registro; se está
    abaixo, despacha. Chamada pelo tratamento do status MQTT (em segundo plano)."""
    if not settings.ota_auto:
        return
    try:
        dispositivo = await repositorio.ler_dispositivo(device_id) or {}
        for alvo in validacao.ALVOS:
            registro = await repositorio.ler(alvo)
            if not registro:
                continue
            try:
                versao = validacao.validar_versao(registro.get("versao"))
                instalada = dispositivo.get(servico.CAMPO_VERSAO[alvo])
                if isinstance(instalada, str) and validacao.comparar_versoes(instalada, versao) >= 0:
                    await repositorio.zerar_tentativas_auto(device_id, alvo, versao)   # alcançou a versão
                    continue
            except validacao.ErroValidacao:
                continue
            await despachar_automatico(device_id, alvo, registro=registro, dispositivo=dispositivo)
    except Exception:
        log.exception("[%s] OTA automático: erro ao verificar o vaso", device_id)


# ------------------------------------------------------------- retentativa ----
# Vaso recusado por falta de dados ou bomba ligada costuma resolver sozinho em segundos. Ele fica
# numa lista EM MEMÓRIA (id -> alvos pendentes + contador); na próxima leitura de sensores dele,
# a verificação roda de novo, até OTA_AUTO_RETENTATIVAS vezes. Vaso fora da lista não custa nada:
# a leitura de sensores só consulta este dicionário, nunca o Firestore.
MOTIVOS_RETENTAVEIS = ("sem_dados", "bomba_ligada")

_pendentes: dict[str, dict] = {}


def _marcar_pendente(device_id: str, alvo: str) -> None:
    pendente = _pendentes.get(device_id)
    if pendente is None:
        if settings.ota_auto_retentativas <= 0:
            return
        _pendentes[device_id] = {"alvos": {alvo}, "usadas": 0, "rodando": False, "renovado": True}
    else:
        pendente["alvos"].add(alvo)
        pendente["renovado"] = True        # recusou de novo: segue pendente (se ainda houver retentativas)


def retentar_se_pendente(device_id: str) -> bool:
    """Chamada a cada leitura de sensores do vaso. Só agenda a verificação se ele estiver pendente
    (e sem outra verificação em curso). Devolve True se agendou. Não toca no Firestore."""
    if not settings.ota_auto:
        return False
    pendente = _pendentes.get(device_id)
    if pendente is None or pendente["rodando"]:
        return False
    if pendente["usadas"] >= settings.ota_auto_retentativas:
        _pendentes.pop(device_id, None)    # acabaram as retentativas: desiste (um status online recomeça)
        return False
    pendente["usadas"] += 1
    pendente["rodando"] = True
    pendente["renovado"] = False
    em_segundo_plano(_rodar_retentativa(device_id))
    return True


async def _rodar_retentativa(device_id: str) -> None:
    try:
        await verificar_vaso_online(device_id)
    finally:
        pendente = _pendentes.get(device_id)
        if pendente is not None:
            pendente["rodando"] = False
            if not pendente["renovado"]:   # não recusou de novo: resolvido (despachou, ou não precisa mais)
                _pendentes.pop(device_id, None)
