#validacao payload

#greensync/{devideID}/sensores
#payload: {"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1, "bomba_ligada": false, "timestamp": 1735000000}

from pydantic import BaseModel, Field

class SensorReading(BaseModel):
    #payload publicado pelo esp32
    
    ph: float = Field(..., ge=0, le=14, description="pH do solo")
    umidade_solo: float = Field(..., ge=0, le=100, description="Umidade do solo em %")
    temperatura_ar: float = Field(..., description="Temperatura do ar em °C")
    bomba_ligada: bool = Field(..., description="Estado atual da bomba d'água")
    timestamp: int = Field(..., description="Unix timestamp (segundos) da leitura")

class DeviceStatus(BaseModel):
    #payload Last Will, (automatico pelo broker)

    status: str = Field(..., description='"Online" ou "Offline"')