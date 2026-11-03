"""Rota de áudio (ADR-017 e ADR-018, camada 2): pergunta falada -> resposta falada.

Contrato com o S3 (proposta, a confirmar com o firmware):

  POST /audio
    Cabeçalhos:  X-API-Key: <chave>
                 X-Device-Id: vaso-01
                 Content-Type: audio/wav      (WAV 16 kHz, 16 bits, mono)
    Corpo:       o áudio da pergunta (bytes do WAV)

  200  Corpo: WAV com a resposta falada (Content-Type: audio/wav)
       X-Tela:  "rosto" | "dados"   -> o que o display deve mostrar (REQ-FUNC-016)
       X-Dados: {"ph":6.4,"solo":20,"temp":24.1,"ar":58,"atuais":true}
  401  chave inválida          413  áudio grande demais
  422  áudio/cabeçalho inválido  429  limite atingido (com Retry-After)
  502  Gemini ou voz fora do ar

Rega por voz (REQ-FUNC-011): se a pessoa pedir ("regar daqui a 1 minuto"), o
backend valida e agenda; a resposta falada já traz a confirmação ou a recusa.
O S3 não precisa fazer nada de diferente.

Com ?debug=true a resposta também traz X-Ouviu, X-Texto e X-Modelo (texto com
%-encoding). Ficam desligados por padrão: cabeçalhos compridos estouram o
buffer do cliente HTTP do ESP32, e o que a pessoa falou é dado pessoal.
"""
import asyncio
import json
import logging
import re
import time
from urllib.parse import quote

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.agenda.servico import tratar_acao
from app.ai.audio import AudioInvalido, validar_audio
from app.ai.resiliencia import IAError
from app.ai.responder import responder_audio
from app.ai.tela import decidir_tela
from app.ai.voz import sintetizar
from app.config import settings
from app.contexto import ler_contexto, salvar_turno
from app.firebase_client import ler_leitura_atual
from app.limite import verificar_limite
from app.seguranca import DEVICE_ID_PADRAO, chave_valida

log = logging.getLogger("greensync.audio")
router = APIRouter()


async def _ler_corpo(request: Request, limite: int) -> bytes:
    """Lê o corpo da requisição, recusando (413) assim que passar do limite.

    Confere o Content-Length antes e também vai contando o que chega, para
    ninguém encher a memória mandando um corpo gigante sem declarar o tamanho.
    """
    declarado = request.headers.get("content-length")
    if declarado and declarado.isdigit() and int(declarado) > limite:
        raise HTTPException(status_code=413, detail=f"áudio grande demais (máximo {limite} bytes)")

    partes: list[bytes] = []
    total = 0
    async for pedaco in request.stream():
        total += len(pedaco)
        if total > limite:
            raise HTTPException(status_code=413, detail=f"áudio grande demais (máximo {limite} bytes)")
        partes.append(pedaco)
    return b"".join(partes)


def _numero(valor, casas: int):
    """Número arredondado para o display, ou None se faltar (ou não for número)."""
    if isinstance(valor, bool) or not isinstance(valor, (int, float)):
        return None
    return int(round(valor)) if casas == 0 else round(valor, casas)


def dados_para_display(leitura: dict | None, estado: dict) -> str:
    """JSON compacto (só ASCII) com o que o OLED do S3 mostra na tela de dados."""
    leitura = leitura or {}
    return json.dumps(
        {
            "ph": _numero(leitura.get("ph"), 1),
            "solo": _numero(leitura.get("umidade_solo"), 0),
            "temp": _numero(leitura.get("temperatura_ar"), 1),
            "ar": _numero(leitura.get("umidade_ar"), 0),
            # false = o vaso está offline ou a leitura é velha: o display deve avisar.
            "atuais": estado.get("dados") == "atuais",
        },
        separators=(",", ":"),
    )


@router.post("/audio")
async def audio(
    request: Request,
    x_api_key: str = Header(default=""),
    x_device_id: str = Header(default=""),
    debug: bool = False,
):
    if not chave_valida(x_api_key):
        raise HTTPException(status_code=401, detail="X-API-Key inválida")
    if not re.fullmatch(DEVICE_ID_PADRAO, x_device_id):
        raise HTTPException(status_code=422, detail="X-Device-Id ausente ou inválido")

    # Validação local e barata primeiro: áudio ruim não gasta o limite nem o Gemini.
    corpo = await _ler_corpo(request, settings.audio_max_bytes)
    try:
        mime = validar_audio(
            corpo,
            request.headers.get("content-type"),
            settings.audio_max_bytes,
            settings.audio_max_s,
        )
    except AudioInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))

    espera = await verificar_limite(x_api_key)
    if espera is not None:
        raise HTTPException(
            status_code=429,
            detail="limite de perguntas atingido, tente de novo em instantes",
            headers={"Retry-After": str(espera)},
        )

    # Dados do vaso e conversa recente, buscados ao mesmo tempo.
    leitura, historico = await asyncio.gather(
        ler_leitura_atual(x_device_id), ler_contexto(x_device_id)
    )

    t0 = time.monotonic()
    try:
        r = await responder_audio(corpo, mime, leitura, historico=historico)
    except IAError as e:
        log.error("[%s] IA falhou: %s", x_device_id, e)
        raise HTTPException(status_code=502, detail="assistente indisponível")

    # Pedido de rega por voz: o backend valida e troca a frase do modelo pela oficial.
    rega = await tratar_acao(r.get("acao"), r["pergunta_ouvida"], x_device_id, leitura, r["estado"], "voz")
    if rega:
        r["texto"] = rega["fala"]
    t_llm = time.monotonic() - t0

    t0 = time.monotonic()
    try:
        wav, modelo_tts = await sintetizar(r["texto"])
    except IAError as e:
        log.error("[%s] voz falhou: %s", x_device_id, e)
        raise HTTPException(status_code=502, detail="voz indisponível")
    t_tts = time.monotonic() - t0

    # A planta lembra desta troca (só se a pessoa disse algo; silêncio não é guardado).
    await salvar_turno(x_device_id, r["pergunta_ouvida"], r["texto"])

    tela = decidir_tela(r["pergunta_ouvida"])
    # Não registramos o que a pessoa falou (dado pessoal); só tamanhos e tempos.
    log.info("[%s] áudio %d B -> voz %d B | entender+responder %.1fs, voz %.1fs | tela=%s | rega=%s | %s, %s",
             x_device_id, len(corpo), len(wav), t_llm, t_tts, tela,
             rega["resultado"] if rega else "-", r["modelo"], modelo_tts)

    cabecalhos = {
        "X-Tela": tela,
        "X-Dados": dados_para_display(leitura, r["estado"]),
    }
    if debug:
        cabecalhos["X-Ouviu"] = quote(r["pergunta_ouvida"])
        cabecalhos["X-Texto"] = quote(r["texto"])
        cabecalhos["X-Modelo"] = f"{r['modelo']} / {modelo_tts}"
    return Response(content=wav, media_type="audio/wav", headers=cabecalhos)