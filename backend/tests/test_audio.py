"""Testa as ferramentas de áudio (WAV, validação), sem Gemini."""
import pytest

from app.ai.audio import (
    AudioInvalido,
    duracao_wav_s,
    info_wav,
    normalizar_mime,
    validar_audio,
    wav_de_pcm,
)

SILENCIO_1S = b"\x00\x00" * 16000  # 1 s de PCM 16 kHz, 16 bits, mono


def wav(segundos=1.0, taxa=16000):
    return wav_de_pcm(b"\x00\x00" * int(taxa * segundos), sample_rate=taxa)


def test_wav_de_pcm_tem_cabecalho_e_dados():
    dados = wav_de_pcm(SILENCIO_1S)
    assert dados[:4] == b"RIFF" and dados[8:12] == b"WAVE"
    assert len(dados) == 44 + len(SILENCIO_1S)   # cabeçalho de 44 bytes


def test_info_wav():
    taxa, canais, duracao = info_wav(wav(2.5, taxa=16000))
    assert (taxa, canais) == (16000, 1)
    assert duracao == pytest.approx(2.5)


def test_duracao_wav_de_outra_taxa():
    assert duracao_wav_s(wav(1.0, taxa=24000)) == pytest.approx(1.0)


def test_info_wav_rejeita_lixo():
    with pytest.raises(ValueError):
        info_wav(b"isso nao e um wav")


@pytest.mark.parametrize("entrada, esperado", [
    ("audio/wav", "audio/wav"),
    ("audio/x-wav", "audio/wav"),
    ("AUDIO/WAV; charset=binary", "audio/wav"),
    ("audio/mpeg", "audio/mp3"),
    ("audio/mp4", "audio/m4a"),
    ("audio/ogg", "audio/ogg"),
    ("application/json", None),
    ("", None),
    (None, None),
])
def test_normalizar_mime(entrada, esperado):
    assert normalizar_mime(entrada) == esperado


def test_validar_aceita_wav_bom():
    assert validar_audio(wav(3), "audio/wav", 1_000_000, 15) == "audio/wav"


def test_validar_aceita_mp3_sem_olhar_duracao():
    # Só WAV tem a duração conferida aqui; o limite de bytes vale para todos.
    assert validar_audio(b"\xff\xfb\x90\x00" * 100, "audio/mpeg", 1_000_000, 15) == "audio/mp3"


def test_validar_recusa_vazio():
    with pytest.raises(AudioInvalido, match="vazio"):
        validar_audio(b"", "audio/wav", 1_000_000, 15)


def test_validar_recusa_grande_demais():
    with pytest.raises(AudioInvalido, match="grande demais"):
        validar_audio(wav(3), "audio/wav", 1000, 15)


def test_validar_recusa_formato_desconhecido():
    with pytest.raises(AudioInvalido, match="formato"):
        validar_audio(wav(1), "application/json", 1_000_000, 15)


def test_validar_recusa_wav_longo_demais():
    with pytest.raises(AudioInvalido, match="longo demais"):
        validar_audio(wav(20), "audio/wav", 10_000_000, 15)


def test_validar_recusa_wav_corrompido():
    with pytest.raises(AudioInvalido, match="ilegível"):
        validar_audio(b"RIFFxxxxWAVEnada", "audio/wav", 1_000_000, 15)


def test_validar_recusa_wav_sem_nenhuma_amostra():
    with pytest.raises(AudioInvalido, match="vazio"):
        validar_audio(wav_de_pcm(b""), "audio/wav", 1_000_000, 15)