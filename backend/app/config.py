from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    #MQTT

    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_use_tls: bool = False
    mqtt_topic_sensores: str = "greensync/+/sensores"
    mqtt_topic_status: str = "greensync/+/status"

    #firebase
    firebase_credentials_path: str = "serviceAccountKey.json"

    #App
    log_level: str = "INFO"

settings = Settings()