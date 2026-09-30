# Backend — GreenSync

Ponte entre o vaso e o app: assina o MQTT, valida os dados, grava no Firestore e (em breve) expõe o assistente de voz. Escrito em Python com FastAPI.

## Responsabilidade

O ESP32-WROOM só lê sensores e publica no broker MQTT. Esse backend é quem decide o que fazer com o dado: valida, grava no Firestore (leitura atual + histórico), detecta quando o vaso caiu (status online/offline) e, na Fase de IA, responde perguntas sobre a planta e agenda regas por voz.

## Stack

- **FastAPI** — serve a API HTTP (health check hoje; `/perguntar` e `/audio` na fase de IA) e gerencia o ciclo de vida do assinante MQTT em segundo plano.
- **aiomqtt** — cliente MQTT assíncrono, com reconexão automática e TLS.
- **Pydantic** — validação estrita dos payloads que chegam do firmware.
- **Firebase Admin SDK** — grava no Firestore com permissão de administrador.
- **Docker / Docker Compose** — ambiente local reprodutível (backend + broker Mosquitto).

## Estrutura

```
backend/
  app/
    main.py            # FastAPI, lifespan (sobe o assinante MQTT no startup)
    config.py           # variáveis de ambiente (.env)
    models.py           # SensorReading, DeviceStatus (validação Pydantic)
    mqtt_client.py       # conexão MQTT, parsing de tópico, reconexão, TLS
    firebase_client.py    # inicialização do Firebase e escrita no Firestore
    ai/                  # (planejado) módulo de IA — Gemini, Redis, agendamento de regas
  Dockerfile
  docker-compose.yml
  .env.example
  serviceAccountKey.json  # chave do Firebase (git-ignored, NUNCA commitar)
```

## Rodando localmente

Pré-requisitos: Docker, Docker Compose, e a chave de serviço do Firebase.

```bash
cd backend
cp .env.example .env
# ajuste o .env — o padrão já aponta para o Mosquitto local (MQTT_USE_TLS=false)
# salve a chave do Firebase como backend/serviceAccountKey.json (nunca commitar)
docker compose up
```

Sobe o backend com hot-reload na porta 8000 e um broker MQTT local (Mosquitto), pra testar sem depender do EMQX Cloud.

Teste rápido, publicando uma leitura simulada:

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -t "greensync/vaso-01/sensores" \
  -m '{"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1, "umidade_ar": 58, "bomba_ligada": false}'
```

A leitura deve aparecer no log do backend (`leitura válida` → `leitura gravada no Firestore`) e em `devices/vaso-01` no Firestore.

### Conectando no EMQX Cloud (em vez do Mosquitto local)

No `.env`, preencha host, porta (8883), usuário e senha do cluster (painel do EMQX Cloud) e defina `MQTT_USE_TLS=true`. A conexão TLS usa o contexto padrão do sistema (`ssl.create_default_context()`), sem certificado customizado.

## Variáveis de ambiente

| Variável | Descrição |
|---|---|
| `MQTT_HOST` / `MQTT_PORT` | Endereço do broker (Mosquitto local ou EMQX Cloud) |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | Credenciais do broker (vazias no Mosquitto local) |
| `MQTT_USE_TLS` | `false` local, `true` no EMQX Cloud |
| `MQTT_TOPIC_SENSORES` / `MQTT_TOPIC_STATUS` | Tópicos assinados (`greensync/+/sensores`, `greensync/+/status`) |
| `FIREBASE_CREDENTIALS_PATH` | Caminho da chave de serviço do Firebase |
| `LOG_LEVEL` | Nível de log |


## Contrato MQTT

Detalhes completos em `docs/Arc42_GreenSync_SDD.md`, Seção 8.

- **Leituras** — `greensync/{deviceId}/sensores`, QoS 1:
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
  `umidade_ar` e `timestamp` são opcionais — se faltar `timestamp`, o backend carimba com a hora do servidor.
- **Status** — `greensync/{deviceId}/status` → `{"status": "online"}` (retido, ao conectar) ou `{"status": "offline"}` (Last Will do broker, se a conexão cair sem aviso).

Payload que não bate com o modelo (`SensorReading`/`DeviceStatus`) é logado e descartado — não derruba o backend.

## Escrita no Firestore

```
devices/{deviceId}
  status, last_seen
  leitura_atual: { ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, updated_at }
  historico/{autoId}     ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, timestamp
```

`leitura_atual` é sobrescrito a cada mensagem (pro app mostrar o valor de agora); `historico` acumula um documento por leitura (pro gráfico). As duas escritas acontecem juntas, num batch.

## Estado atual

| Módulo | Estado |
|---|---|
| Assinante MQTT com reconexão + TLS | Implementado |
| Validação de payload (`SensorReading`, `DeviceStatus`) | Implementado |
| Gravação no Firestore (leitura atual + histórico + status) | Implementado |
| Teste do Last Will (offline automático) | Pendente |
| Redis (contexto e limite de perguntas da IA) | Planejado |
| Módulo de IA (`POST /perguntar`, `POST /audio`) — ver `backend/app/ai/README.md` quando existir | Planejado |
| Agendamento de regas e comandos MQTT | Planejado |
| Deploy no Render (`$PORT` dinâmico, chave do Firebase como Secret File) | Pendente |

## Rodando em Docker de produção (Render)

O `Dockerfile` builda a imagem; falta ajustar o `CMD` pra usar a variável `$PORT` do Render em vez de porta fixa, e subir a chave do Firebase como Secret File (nunca no build da imagem). As demais variáveis de ambiente (tabela acima) vão direto no painel do Render.