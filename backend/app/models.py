# Validação dos payloads MQTT
#
# greensync/{deviceId}/sensores
# {"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1,
#  "umidade_ar": 58, "bomba_ligada": false, "timestamp": 1735000000}
#
# greensync/{deviceId}/status
# {"status": "online"} ou {"status": "offline"}

from typing import Literal, Optional

from pydantic import BaseModel, Field


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