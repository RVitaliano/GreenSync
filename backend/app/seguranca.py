"""Regras de segurança compartilhadas pelas rotas (/perguntar e /audio)."""
import secrets

from app.config import settings

# O device_id vira nome de documento no Firestore, então só aceitamos letras,
# números, "-" e "_" (sem "/", que abriria outros caminhos).
DEVICE_ID_PADRAO = r"^[A-Za-z0-9_-]{1,64}$"


def chave_valida(recebida: str) -> bool:
    """Compara a X-API-Key em tempo constante. Vazia no .env = rota aberta (dev)."""
    if not settings.api_key:
        return True
    # .encode() porque compare_digest com str não aceita acento.
    return secrets.compare_digest(recebida.encode(), settings.api_key.encode())