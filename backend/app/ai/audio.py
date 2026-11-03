"""Ferramentas de áudio: montar WAV, medir duração e validar o que chega.

O S3 vai mandar WAV (16 kHz, 16 bits, mono, cabeçalho de 44 bytes). Para
testar com o celular, também aceitamos mp3/m4a/ogg/flac/aac.
"""
import io
import wave

# Tipo informado pelo cliente -> tipo que o Gemini aceita.
_MIMES = {
    "audio/wav": "audio/wav",
    "audio/x-wav": "audio/wav",
    "audio/wave": "audio/wav",
    "audio/vnd.wave": "audio/wav",
    "audio/mpeg": "audio/mp3",
    "audio/mp3": "audio/mp3",
    "audio/mp4": "audio/m4a",
    "audio/m4a": "audio/m4a",
    "audio/x-m4a": "audio/m4a",
    "audio/aac": "audio/aac",
    "audio/ogg": "audio/ogg",
    "audio/flac": "audio/flac",
    "audio/x-flac": "audio/flac",
}


class AudioInvalido(ValueError):
    """Áudio recusado (vazio, grande demais, formato não aceito, longo demais)."""


def wav_de_pcm(pcm: bytes, sample_rate: int = 16000, canais: int = 1, bits: int = 16) -> bytes:
    """Coloca o cabeçalho WAV em volta de áudio PCM cru."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(bits // 8)
        w.setframerate(sample_rate)
        w.writeframes(pcm)
    return buf.getvalue()


def info_wav(dados: bytes) -> tuple[int, int, float]:
    """(sample_rate, canais, duração_em_segundos) de um WAV. ValueError se não for WAV."""
    try:
        with wave.open(io.BytesIO(dados), "rb") as w:
            taxa = w.getframerate()
            canais = w.getnchannels()
            quadros = w.getnframes()
    except (wave.Error, EOFError) as e:
        raise ValueError(f"WAV ilegível: {e}") from e
    if taxa <= 0:
        raise ValueError("WAV com taxa de amostragem inválida")
    return taxa, canais, quadros / taxa


def duracao_wav_s(dados: bytes) -> float:
    return info_wav(dados)[2]


def normalizar_mime(content_type: str | None) -> str | None:
    """'audio/WAV; charset=x' -> 'audio/wav'. None se o formato não for aceito."""
    if not content_type:
        return None
    base = content_type.split(";")[0].strip().lower()
    return _MIMES.get(base)


def validar_audio(dados: bytes, content_type: str | None, max_bytes: int, max_s: float) -> str:
    """Confere o áudio recebido e devolve o tipo para mandar ao Gemini.

    Levanta AudioInvalido (com mensagem em português) se algo estiver errado.
    """
    if not dados:
        raise AudioInvalido("áudio vazio")
    if len(dados) > max_bytes:
        raise AudioInvalido(f"áudio grande demais (máximo {max_bytes} bytes)")

    mime = normalizar_mime(content_type)
    if mime is None:
        raise AudioInvalido(f"formato de áudio não aceito: {content_type!r}")

    if mime == "audio/wav":
        try:
            duracao = duracao_wav_s(dados)
        except ValueError as e:
            raise AudioInvalido(str(e)) from e
        if duracao > max_s:
            raise AudioInvalido(f"áudio longo demais ({duracao:.1f} s; máximo {max_s:.0f} s)")
        if duracao <= 0:
            raise AudioInvalido("áudio vazio")
    return mime