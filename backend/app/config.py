from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": variáveis do .env que ainda não estão declaradas aqui
    # (ex.: REDIS_URL, que entra depois) não derrubam o backend na inicialização.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # MQTT
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_use_tls: bool = False
    mqtt_topic_sensores: str = "greensync/+/sensores"
    mqtt_topic_status: str = "greensync/+/status"

    # Firebase
    firebase_credentials_path: str = "serviceAccountKey.json"

    # --- IA (Gemini) ---
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.1-flash-lite"
    # Reserva usada se o principal estiver sobrecarregado (503) ou lento (timeout).
    gemini_model_fallback: str = "gemini-3.5-flash-lite"
    # Tempo máximo de espera por chamada, em segundos. Acima disso, vai para o reserva.
    gemini_timeout_s: float = 8.0

    # --- Personalidade ---
    tom_planta: str = "planta"  # "planta" (divertido) ou "informativo" (mais seco)

    # --- Limiares do estado da planta (calibrar com testes reais) ---
    solo_seco_abaixo: float = 30.0       # % abaixo disso: planta com sede
    solo_encharcado_acima: float = 80.0  # % acima disso: solo encharcado
    temp_min: float = 10.0               # °C
    temp_max: float = 35.0               # °C
    ph_min: float = 5.5
    ph_max: float = 7.5

    # --- API HTTP ---
    api_key: str = ""  # se vazia, a rota fica aberta (só para desenvolvimento)

    # App
    log_level: str = "INFO"


settings = Settings()