# Validação dos payloads MQTT
#
# greensync/{deviceId}/sensores
# {"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1,
#  "umidade_ar": 58, "bomba_ligada": false, "timestamp": 1735000000}
#
# greensync/{deviceId}/status
# {"status": "online"} ou {"status": "offline"}

import logging
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

from app.ota.validacao import versao_ou_none

logger = logging.getLogger("greensync.models")


class SensorReading(BaseModel):
    """Payload publicado pelo ESP32-WROOM."""

    ph: float = Field(..., ge=0, le=14, description="pH do solo")
    umidade_solo: float = Field(..., ge=0, le=100, description="Umidade do solo em %")
    temperatura_ar: float = Field(..., ge=-40, le=80, description="Temperatura do ar em °C (faixa do DHT22)")
    umidade_ar: Optional[float] = Field(None, ge=0, le=100, description="Umidade do ar em %")
    bomba_ligada: bool = Field(..., description="Estado atual da bomba d'água")
    timestamp: Optional[int] = Field(None, description="Unix timestamp (s); se faltar, o backend carimba")


class DeviceStatus(BaseModel):
    """Payload de status (Last Will é publicado pelo broker)."""

    status: Literal["online", "offline"]
    # Versão do firmware de cada placa (opcional; o Last Will não traz). Valor fora do
    # formato vira None e não derruba o status.
    fw: Optional[str] = None
    fw_s3: Optional[str] = None

    @field_validator("fw", "fw_s3", mode="before")
    @classmethod
    def _versao_valida(cls, v, info):
        if v is None:
            return None
        valida = versao_ou_none(v)
        if valida is None:
            logger.warning("versão de firmware inválida em %s, ignorada", info.field_name)
        return valida