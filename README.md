# GreenSync 🌱

Vaso inteligente que monitora pH do solo, umidade do solo e temperatura do ar, controla irrigação automática e sincroniza os dados em tempo real com um aplicativo mobile. Projeto acadêmico desenvolvido por um grupo de 3 pessoas.

## Visão geral

O GreenSync lê os sensores, decide quando regar a planta sozinho e envia os dados pra nuvem, de onde o aplicativo mostra tudo em tempo real. Na V2, o vaso também responde perguntas faladas sobre a planta, usando um assistente de voz com LLM (Google Gemini, camada gratuita).

### Fases

- **V1** — hardware, sensores, irrigação automática, sincronização de dados (Wi-Fi → MQTT → backend → Firebase), app básico. O módulo de orquestração de IA (chamadas ao Gemini) é desenvolvido e testado em paralelo já nessa fase, com dados reais do Firestore — mas ainda sem estar conectado ao hardware de voz.
- **V2** — integração completa do assistente de voz ao hardware (captura de áudio, STT, TTS, reprodução), e troca do Wi-Fi por conectividade GPRS.

## Arquitetura

```
ESP32-S3 ──MQTT/TLS──> HiveMQ Cloud ──MQTT/TLS──> Backend (FastAPI, Render)
                                                          │
                                                          ▼
                                                   Firebase (Firestore)
                                                          │
                                                          ▼
                                                 App (Flutter, FlutterFire)
```

O vaso só lê sensores e publica no MQTT — toda a lógica de negócio (validação, persistência, e futuramente orquestração de IA) fica no backend.

## Estrutura do repositório

| Pasta | Frente | O que tem |
|---|---|---|
| `firmware/` | Hardware/Firmware | Código do ESP32-S3 (sensores, bomba, display, MQTT) |
| `backend/` | Backend | FastAPI + assinante MQTT + gravação no Firestore + módulo de IA (Gemini) |
| `app/` | App | Aplicativo Flutter |
| `docs/` | Todos | SRS, ADR, Arc42 — documentação do projeto |

## Contrato MQTT (Firmware ↔ Backend)

- Tópico: `greensync/{deviceId}/sensores`
- Payload:
```json
  {
    "ph": 6.4,
    "umidade_solo": 42,
    "temperatura_ar": 24.1,
    "bomba_ligada": false,
    "timestamp": 1735000000
  }
```
- QoS: 1
- Last Will: `greensync/{deviceId}/status` → `{"status": "offline"}`

Detalhes completos em `docs/Arc42_-_SDD.md`, seção 8.1.

## Rodando o backend localmente

```bash
cd backend
cp .env.example .env   # preencher com as credenciais do HiveMQ e do Firebase
docker compose up
```

Sobe o backend (com hot-reload) e um broker MQTT local (Mosquitto), pra testar sem depender do HiveMQ Cloud. Detalhes em `backend/README.md`.

## Branches

- `main` — branch principal, protegida.
- Cada frente trabalha em branches próprias (ex.: `backend/mqtt-subscriber`, `firmware/leitura-sensores`) e abre PR pra `main`.