"""Teste manual do áudio (gasta cota do Gemini, por isso não vai no pytest).

Rodar (na pasta backend/):

  # 1) Autoteste: a própria voz do Gemini "pergunta", sem precisar gravar nada
  docker compose run --rm backend python -m tests.manual_audio

  # 2) Com uma gravação sua (celular ou, depois, o S3)
  docker compose run --rm backend python -m tests.manual_audio tests/amostras/pergunta.wav

Os áudios gerados ficam em backend/tests/saida/ para você ouvir.
"""
import asyncio
import sys
import time
from pathlib import Path

from app.ai.audio import info_wav, validar_audio, wav_de_pcm
from app.ai.resiliencia import IAError
from app.ai.responder import responder_audio
from app.ai.tela import decidir_tela
from app.ai.voz import sintetizar
from app.config import settings

SAIDA = Path(__file__).parent / "saida"

# Planta com sede: a resposta deve falar disso quando perguntarem como ela está.
LEITURA = {"umidade_solo": 20, "temperatura_ar": 24.1, "bomba_ligada": False}

# Tipo de áudio pelo final do nome do arquivo.
MIME_POR_EXTENSAO = {
    ".wav": "audio/wav", ".mp3": "audio/mpeg", ".m4a": "audio/mp4",
    ".ogg": "audio/ogg", ".flac": "audio/flac", ".aac": "audio/aac",
}

PAUSA_S = 6  # respeita o limite por minuto do plano gratuito


def salvar(nome: str, wav: bytes) -> Path:
    SAIDA.mkdir(exist_ok=True)
    caminho = SAIDA / nome
    caminho.write_bytes(wav)
    return caminho


async def perguntar(titulo: str, audio: bytes, mime: str, nome_saida: str) -> None:
    """Manda o áudio da pergunta, mostra a resposta e grava a voz da resposta."""
    print(f"=== {titulo} ===")
    try:
        mime = validar_audio(audio, mime, settings.audio_max_bytes, settings.audio_max_s)
    except ValueError as e:
        print(f"  ÁUDIO RECUSADO: {e}\n")
        return

    t = time.time()
    try:
        r = await responder_audio(audio, mime, LEITURA)
    except IAError as e:
        print(f"  [{time.time() - t:.1f}s] ERRO ao entender/responder: {e}\n")
        return
    print(f"  [{time.time() - t:.1f}s] ({r['modelo']})")
    print(f"  ouviu:    {r['pergunta_ouvida']!r}")
    print(f"  resposta: {r['texto']}")
    print(f"  tela:     {decidir_tela(r['pergunta_ouvida'])}")

    await asyncio.sleep(PAUSA_S)
    t = time.time()
    try:
        wav, modelo_tts = await sintetizar(r["texto"])
    except IAError as e:
        print(f"  [{time.time() - t:.1f}s] ERRO na voz: {e}\n")
        return
    taxa, canais, duracao = info_wav(wav)
    caminho = salvar(nome_saida, wav)
    print(f"  [{time.time() - t:.1f}s] voz ({modelo_tts}): {duracao:.1f} s, {taxa} Hz, "
          f"{canais} canal, {len(wav) // 1024} KB -> {caminho}\n")


async def main(argumentos: list[str]) -> None:
    print(f"Modelo: {settings.gemini_model} (reserva {settings.gemini_model_fallback})")
    print(f"Voz: {settings.tts_model} / {settings.tts_voice} "
          f"(reserva {settings.tts_model_fallback})")
    print(f"Chave configurada: {'sim' if settings.gemini_api_key else 'NÃO'}\n")

    if argumentos:
        caminho = Path(argumentos[0])
        mime = MIME_POR_EXTENSAO.get(caminho.suffix.lower())
        if mime is None:
            print(f"Extensão não reconhecida: {caminho.suffix}")
            return
        await perguntar(f"Sua gravação: {caminho.name}", caminho.read_bytes(), mime,
                        "resposta_gravacao.wav")
    else:
        # Autoteste: a voz sintética faz a pergunta e o Gemini tem que ouvir e responder.
        for i, frase in enumerate(["Como você está?", "Qual é a temperatura?"], start=1):
            try:
                wav, _ = await sintetizar(frase)
            except IAError as e:
                print(f"Não consegui gerar a pergunta de teste ({e}). A voz (TTS) está funcionando?")
                return
            salvar(f"pergunta_{i}.wav", wav)
            await asyncio.sleep(PAUSA_S)
            await perguntar(f"Autoteste {i}: {frase!r}", wav, "audio/wav", f"resposta_{i}.wav")
            await asyncio.sleep(PAUSA_S)

    # Silêncio: a planta NÃO pode inventar uma pergunta; tem que pedir para repetir.
    silencio = wav_de_pcm(b"\x00\x00" * 16000 * 2, sample_rate=16000)  # 2 s
    await perguntar("Silêncio (2 s)", silencio, "audio/wav", "resposta_silencio.wav")


if __name__ == "__main__":  # só roda se chamado de propósito, nunca pelo pytest
    asyncio.run(main(sys.argv[1:]))