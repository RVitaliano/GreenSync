# GreenSync 🌱

Vaso inteligente que monitora pH do solo, umidade do solo, temperatura e umidade do ar, rega a planta por comando (app, voz ou agenda) e sincroniza os dados em tempo real com um aplicativo mobile. Um assistente de voz responde como a própria planta e pode agendar regas por comando de voz.

Projeto acadêmico do **Grupo GreenSync** (Faculdade Nova Roma), desenvolvido por 3 integrantes, uma por frente: hardware/firmware, backend e aplicativo.

## Visão geral

O GreenSync lê os sensores, envia os dados para a nuvem e mostra tudo em tempo real no aplicativo. A rega é sempre um comando validado pelo backend (botão do app, pedido por voz ou agenda), e o firmware aplica seus próprios limites de segurança. O vaso usa **dois microcontroladores**: um ESP32-WROOM (sensores e bomba, via MQTT) e um ESP32-S3 (voz: microfone e alto-falante, via HTTP). A voz usa o Google Gemini, e toda a lógica de negócio fica no backend.

### Fases

- **V1**: o vaso do ESP32-WROOM completo: sensores (DHT22, YL-69 e pH), bomba por comando, sincronização de dados (Wi-Fi → MQTT → backend → Firebase), aplicativo, configuração de Wi-Fi por Bluetooth (BLE) e atualização de firmware pela rede (OTA).
- **V2**: o ESP32-S3 com voz (microfone, alto-falante, palavra de ativação "Hi ESP") e display, com o assistente que responde como a planta e agenda regas por comando de voz.

## Arquitetura

```
ESP32-WROOM ──MQTT/TLS──> EMQX Cloud ──MQTT/TLS──> Backend (FastAPI, Render) ──> Firebase (Firestore) ──> App (Flutter)
 (sensores,      ▲                                    │   │
  bomba)         └──── comandos (regar, atualizar) ───┘   └──> Redis (contexto, limite de perguntas)
                                                       │
ESP32-S3 ──HTTPS + X-API-Key──> Backend ──────────────┴──> Google Gemini (LLM) + TTS
 (voz)   <────── áudio da resposta ─────┘

App (Flutter) ──BLE──> ESP32-WROOM (configuração de Wi-Fi)
```

Os firmwares só leem sensores/áudio e falam com a nuvem. Toda a lógica (validação, persistência, IA, agendamento de regas, atualização de firmware) fica no backend. O firmware ainda limita o tempo máximo de bomba ligada e ignora comandos repetidos, de modo que a bomba nunca fica ligada além do limite, qualquer que seja o comando.

## Estrutura do repositório

| Pasta | Frente | O que tem |
|---|---|---|
| `firmware/` | Hardware/Firmware | Código do ESP32-WROOM (sensores, bomba, MQTT, BLE, OTA) e do ESP32-S3 (áudio, HTTP) |
| `backend/` | Backend | FastAPI + assinante MQTT + gravação no Firestore + módulo de IA (Gemini) + OTA |
| `app/` | App | Aplicativo Flutter |
| `docs/` | Todos | SRS, ADR, Arc42 e Plano de Testes |

## Contratos entre as frentes

Detalhes completos em `docs/Arc42_GreenSync_SDD.md`, Seção 8.

**MQTT (ESP32-WROOM ↔ Backend)**

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
  `umidade_ar` e `timestamp` são opcionais. `umidade_solo` já vem em % (o firmware calibra o YL-69). Se o DHT22 falhar, o firmware não publica. O pH da demonstração é simulado (ADR-024).
- Status: `greensync/{deviceId}/status` → `{"status": "online", "fw": "2.1.0"}` (publicado ao conectar, com retain) ou `{"status": "offline"}` (Last Will do broker).
- Comandos (backend → vaso), `greensync/{deviceId}/comandos`, QoS 1, sem retain:
  - `{"acao": "regar", "duracao_s": 5, "id": "..."}`
  - `{"acao": "atualizar", "alvo": "wroom", "id": "...", "versao": "...", "url": "...", "sha256": "..."}`
  - `{"acao": "reverter", "alvo": "wroom", "id": "...", "versao": "..."}`
- Progresso da atualização (vaso → backend), `greensync/{deviceId}/ota` → `{"alvo", "id", "estado", "versao", "erro"}`.
- As leituras são publicadas com QoS 0 (limitação da biblioteca `PubSubClient`).

**HTTP de áudio (ESP32-S3 ↔ Backend)**: `POST /audio` com `X-API-Key` e `X-Device-Id`; WAV 16 kHz, 16 bits, mono, de até 15 s; resposta em WAV (24 kHz) com `X-Tela` e `X-Dados`.

**Bluetooth (App ↔ ESP32-WROOM)**: serviço GATT `GreenSync_BLE` para enviar `ssid,senha` e receber o estado da conexão (`conectando`, `ok` ou `erro:senha|rede|timeout`).

**Firestore (Backend ↔ App)**

```
devices/{deviceId}
  status, last_seen, fw, ota
  leitura_atual: { ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, updated_at }
  historico/{autoId}     ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, timestamp
  agendamentos/{id}      quando, duracao_s, status, origem, motivo, criado_em, atualizado_em
firmware/{alvo}          versao, url, sha256, notas, anterior, bloqueadas
```

## Rodando o backend localmente

Pré-requisitos: Docker e Docker Compose, e a chave de serviço do Firebase.

```bash
cd backend
cp .env.example .env                 # ajustar as variáveis (o padrão já aponta para o Mosquitto local)
# salvar a chave de serviço do Firebase como backend/serviceAccountKey.json (nunca commitar)
docker compose up
```

Sobe o backend (com hot-reload, na porta 8000), um broker MQTT local (Mosquitto) e o Redis, para testar sem depender do EMQX Cloud. Teste rápido, com uma leitura simulada:

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -t "greensync/vaso-01/sensores" \
  -m '{"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1, "umidade_ar": 58, "bomba_ligada": false}'
```

A leitura deve aparecer no log do backend e em `devices/vaso-01` no Firestore.

> **Atenção:** se outro broker MQTT estiver rodando na máquina, ele pode ocupar a porta 1883. Pare-o antes de subir o GreenSync.

## Estado atual

| Módulo | Estado |
|---|---|
| Backend: assinante MQTT, validação, Firestore, Redis | Implementado, em produção no Render |
| Backend: assistente (`/perguntar` e `/audio`), rega por voz, agenda e comandos MQTT | Implementado |
| Backend: OTA (registro de firmware, `/atualizar`, `/reverter`, OTA automático opcional) | Implementado |
| Firmware WROOM: DHT22 e YL-69 reais, bomba por relé, MQTT/TLS, BLE e OTA com rollback | Implementado e testado em bancada (pH simulado) |
| Firmware S3: voz (microfone, alto-falante, cliente HTTP) e display | Em desenvolvimento (testes de hardware por módulo) |
| App: dados em tempo real, histórico, provisionamento BLE | Implementado; BLE em teste em aparelho Android |
| Teste de ponta a ponta com o vaso completo | Em andamento |

## Branches

- `main`: branch principal, protegida.
- Cada frente trabalha em branches próprias (ex.: `backend/mqtt-subscriber`, `firmware/leitura-sensores`) e abre PR para a `main`.
- Mudanças de contrato (tópicos MQTT, JSON, Firestore, API de áudio) devem ser avisadas às outras frentes **antes** de implementadas.
- Nunca commitar `.env` nem arquivos de chave (`serviceAccountKey.json`, `config.h`).