from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": variáveis do .env que ainda não estão declaradas aqui
    # não derrubam o backend na inicialização.
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
    # Pergunta em áudio demora mais (o modelo ouve e responde), então tem prazo próprio.
    gemini_timeout_audio_s: float = 12.0

    # --- Voz (TTS): transforma o texto da resposta em áudio ---
    tts_model: str = "gemini-3.8-flash-tts"
    tts_model_fallback: str = "gemini-3.8-flash-lite-tts"
    tts_voice: str = "Kore"        # voz pré-pronta; outras: Puck, Zephyr, Aoede...
    tts_estilo: str = ""           # ex.: "simpática e carinhosa". Vazio = sem estilo
    tts_sample_rate: int = 0       # 0 = padrão do modelo (24000 Hz). Ex.: 16000
    tts_timeout_s: float = 15.0

    # --- Áudio recebido do S3 / celular (POST /audio) ---
    audio_max_bytes: int = 1_000_000   # ~30 s de WAV 16 kHz mono 16 bits
    audio_max_s: float = 15.0          # pergunta mais longa que isso é recusada

    # --- Rega por voz e agendamento (REQ-FUNC-011 e REQ-FUNC-012) ---
    # Tópico dos comandos para o vaso; {device_id} é trocado pelo id do dispositivo.
    mqtt_topic_comandos: str = "greensync/{device_id}/comandos"
    rega_atraso_max_s: int = 86400     # só agenda para as próximas 24 h
    rega_duracao_max_s: int = 10       # rega mais longa que isso é recusada
    rega_duracao_padrao_s: int = 5     # usada quando a pessoa não diz quanto tempo
    rega_intervalo_min_s: int = 600    # mínimo entre duas regas (10 min)
    rega_tolerancia_s: int = 300       # atrasou mais que isso (ex.: backend reiniciou)? expira
    # Horário local do usuário, para "às 15h". Brasil (Brasília) = -3, sem horário de verão.
    fuso_utc_h: float = -3.0

    # --- Personalidade ---
    tom_planta: str = "planta"  # "planta" (divertido) ou "informativo" (mais seco)

    # --- Limiares do estado da planta (calibrar com testes reais) ---
    solo_seco_abaixo: float = 30.0       # % abaixo disso: planta com sede
    solo_encharcado_acima: float = 80.0  # % acima disso: solo encharcado
    temp_min: float = 10.0               # °C
    temp_max: float = 35.0               # °C
    ph_min: float = 5.5
    ph_max: float = 7.5

    # Passou desse tempo sem leitura nova, o dado é tratado como velho e a planta
    # avisa em vez de falar como se fosse de agora. O firmware publica a cada
    # 10 a 30 s (Arc42 8.1); 120 s = vários envios perdidos.
    leitura_velha_apos_s: int = 120

    # --- API HTTP ---
    api_key: str = ""  # se vazia, a rota fica aberta (só para desenvolvimento)

    # --- Redis e limite de perguntas (REQ-FUNC-015) ---
    # Ex.: redis://redis:6379/0. Vazia = sem Redis, e o limite fica DESLIGADO.
    redis_url: str = ""
    limite_perguntas: int = 10   # perguntas permitidas por janela, por chave de API
    janela_limite_s: int = 60    # tamanho da janela, em segundos

    # --- Contexto curto da conversa no Redis (REQ-FUNC-008, ADR-015) ---
    contexto_turnos: int = 3        # quantas trocas (pergunta + resposta) lembrar; 0 = desliga
    contexto_ttl_s: int = 300       # esquece tudo depois de 5 min sem conversa
    contexto_max_chars: int = 300   # corta cada pergunta/resposta guardada neste tamanho

    # App
    log_level: str = "INFO"


settings = Settings()