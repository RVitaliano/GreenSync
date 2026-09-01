# GreenSync 🌱

Vaso inteligente que monitora pH do solo, umidade do solo e temperatura do ar, controla irrigação automática e sincroniza os dados em tempo real com um aplicativo mobile. Projeto acadêmico desenvolvido por um grupo de 3 pessoas.

## Visão geral

O GreenSync lê os sensores, decide quando regar a planta sozinho e envia os dados pra nuvem, de onde o aplicativo mostra tudo em tempo real. Na V2, o vaso também responde perguntas faladas sobre a planta, usando um assistente de voz.

### Fases

- **V1** — hardware, sensores, irrigação automática, sincronização de dados (Wi-Fi → MQTT → backend → Firebase), app básico.
- **V2** — assistente de voz (LLM em nuvem) integrado ao hardware, e troca do Wi-Fi por conectividade GPRS.

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

| Pasta | Responsável | O que tem |
|---|---|---|
| `firmware/` | Colega 1 | Código do ESP32-S3 (sensores, bomba, display, MQTT) |
| `backend/` | Você | FastAPI + assinante MQTT + gravação no Firestore |
| `app/` | Colega 2 | Aplicativo Flutter |
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

## Time

| Quem | Frente |
|---|---|
| Colega 1 | Hardware/Firmware |
| Você | Backend |
| Colega 2 | App |

## Branches

- `main` — branch principal, protegida.
- Cada frente trabalha em branches próprias (ex.: `backend/mqtt-subscriber`, `firmware/leitura-sensores`) e abre PR pra `main`.