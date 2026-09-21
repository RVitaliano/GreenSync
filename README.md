# GreenSync 🌱

Vaso inteligente que monitora pH do solo, umidade do solo, temperatura e umidade do ar, controla irrigação automática e sincroniza os dados em tempo real com um aplicativo mobile. Um assistente de voz responde como a própria planta e pode agendar regas por comando de voz. Projeto acadêmico desenvolvido por um grupo de 3 pessoas.

## Visão geral

O GreenSync lê os sensores, decide quando regar a planta sozinho e envia os dados pra nuvem, de onde o aplicativo mostra tudo em tempo real. O vaso usa **dois microcontroladores**: um ESP32-WROOM (sensores e bomba, via MQTT) e um ESP32-S3 (voz: microfone e alto-falante, via HTTP). A voz usa o Google Gemini, e toda a lógica de negócio fica no backend.

### Fases

- **V1** — hardware, sensores (DHT22, YL-69, pH), irrigação automática, sincronização de dados (Wi-Fi → MQTT → backend → Firebase), app, **assistente de voz com personalidade da planta**, rega por voz com agenda e configuração de Wi-Fi por portal.
- **V2** — conectividade GPRS no ESP32-WROOM, tornando o dispositivo independente de rede local.

## Arquitetura

```
ESP32-WROOM ──MQTT/TLS──> EMQX Cloud ──MQTT/TLS──> Backend (FastAPI, Render) ──> Firebase (Firestore) ──> App (Flutter)
 (sensores,      ▲                                    │   │
  bomba)         └──── comandos de rega (MQTT) ───────┘   └──> Redis (contexto, limite de perguntas)
                                                       │
ESP32-S3 ──HTTPS + X-API-Key──> Backend ──────────────┴──> Google Gemini (LLM) + TTS
 (voz)   <────── áudio da resposta ─────┘
```

Os firmwares só leem sensores/áudio e falam com a nuvem — toda a lógica (validação, persistência, IA, agendamento de regas) fica no backend. A irrigação por umidade continua no firmware, com histerese, como regra base: a planta não depende da nuvem para sobreviver.

## Estrutura do repositório

| Pasta | Frente | O que tem |
|---|---|---|
| `firmware/` | Hardware/Firmware | Código do ESP32-WROOM (sensores, bomba, MQTT) e do ESP32-S3 (áudio, HTTP) |
| `backend/` | Backend | FastAPI + assinante MQTT + gravação no Firestore + módulo de IA (Gemini) |
| `app/` | App | Aplicativo Flutter |
| `docs/` | Todos | SRS, ADR, Arc42 — documentação do projeto |

## Contratos entre as frentes

Detalhes completos em `docs/Arc42_GreenSync_SDD.md`, Seção 8. Itens marcados como proposta ainda precisam da confirmação da frente de firmware.

**MQTT (ESP32-WROOM ↔ Backend)** — QoS 1

- Leituras: `greensync/{deviceId}/sensores`
  ```json
  {
    "ph": 6.4,
    "umidade_solo": 42,
    "temperatura_ar": 24.1,
    "umidade_ar": 58,
    "bomba_ligada": false,
    "timestamp": 1735000000
  }
  ```
  `umidade_ar` e `timestamp` são opcionais. `umidade_solo` já vem em % (o firmware calibra o YL-69). Se o DHT22 falhar, o firmware não publica.
- Status: `greensync/{deviceId}/status` → `{"status": "online"}` (publicado ao conectar, com retain) ou `{"status": "offline"}` (Last Will do broker).
- Comandos (proposta): `greensync/{deviceId}/comandos` → `{"acao": "regar", "duracao_s": 5, "id": "..."}`.

**HTTP de áudio (ESP32-S3 ↔ Backend)** — proposta: `POST /audio` com cabeçalho `X-API-Key`; formato do áudio ainda a definir.

**Firestore (Backend ↔ App)**

```
devices/{deviceId}
  status, last_seen
  leitura_atual: { ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, updated_at }
  historico/{autoId}     ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, timestamp
  agendamentos/{id}      executar_em, duracao_s, status, origem, criado_em   (planejado)
```

## Rodando o backend localmente

Pré-requisitos: Docker e Docker Compose, e a chave de serviço do Firebase.

```bash
cd backend
cp .env.example .env                 # ajustar as variáveis (o padrão já aponta para o Mosquitto local)
# salvar a chave de serviço do Firebase como backend/serviceAccountKey.json (nunca commitar)
docker compose up
```

Sobe o backend (com hot-reload, na porta 8000) e um broker MQTT local (Mosquitto), pra testar sem depender do EMQX Cloud. Teste rápido, com uma leitura simulada:

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -t "greensync/vaso-01/sensores" \
  -m '{"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1, "umidade_ar": 58, "bomba_ligada": false}'
```

A leitura deve aparecer no log do backend e em `devices/vaso-01` no Firestore.

> **Atenção:** se o EMQX do laboratório da disciplina estiver rodando, ele ocupa a porta 1883. Pare-o (`docker stop lab-emqx lab-postgres`) antes de subir o GreenSync.

## Estado atual do backend

| Módulo | Estado |
|---|---|
| Assinante MQTT com reconexão | Implementado |
| Validação de payload (`SensorReading`, `DeviceStatus`) | Implementado |
| Gravação no Firestore (leitura atual + histórico + status) | Implementado |
| Teste do Last Will | Pendente |
| Redis (contexto e limite de perguntas) | Planejado |
| Módulo de IA (`POST /perguntar`, `POST /audio`) | Planejado |
| Agendamento de regas e comandos MQTT | Planejado |

## Branches

- `main` — branch principal, protegida.
- Cada frente trabalha em branches próprias (ex.: `backend/mqtt-subscriber`, `firmware/leitura-sensores`) e abre PR pra `main`.
- Mudanças de contrato (tópicos MQTT, JSON, Firestore, API de áudio) devem ser avisadas às outras frentes **antes** de implementadas.
- Nunca commitar `.env` nem arquivos de chave (`serviceAccountKey.json`).