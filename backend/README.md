# Backend — GreenSync

Ponte entre o vaso e o app: assina o MQTT, valida os dados, grava no Firestore e expõe o assistente de voz da planta (texto e áudio), incluindo a rega por voz com agendamento. Escrito em Python com FastAPI.

## Responsabilidade

O ESP32-WROOM só lê sensores e publica no broker MQTT; o ESP32-S3 só captura e toca áudio. Este backend é quem decide o que fazer com os dados:

- valida cada leitura e grava no Firestore (leitura atual + histórico) e detecta quando o vaso caiu (online/offline);
- responde perguntas sobre a planta, **em texto** (`POST /perguntar`) ou **em voz** (`POST /audio`), falando como a própria planta com os dados reais dos sensores;
- entende pedidos de rega ("rega daqui a 10 minutos"), valida os limites, agenda no Firestore e publica o comando no MQTT na hora marcada. **O Gemini nunca aciona a bomba**: ele só entende o pedido, e o backend decide.

## Stack

- **FastAPI** + **uvicorn** (processo único, `async`/`await`).
- **aiomqtt** — cliente MQTT assíncrono, com reconexão automática e TLS; assina sensores/status e publica os comandos.
- **Pydantic** — validação dos payloads do firmware e das configurações.
- **Firebase Admin SDK** — Firestore (síncrono, chamado com `asyncio.to_thread`).
- **google-genai** — Gemini para entender texto e áudio e para gerar a voz (TTS).
- **Redis** — limite de perguntas por chave de API.
- **Docker / Docker Compose** — ambiente local (backend + Mosquitto + Redis).

## Estrutura

```
backend/
  app/
    main.py              # FastAPI, lifespan (Firebase, MQTT, agendador, Redis)
    config.py            # todas as variáveis de ambiente (.env)
    models.py            # SensorReading, DeviceStatus (validação dos payloads MQTT)
    mqtt_client.py       # assinante MQTT (reconexão, TLS) e publicar_comando
    firebase_client.py   # Firestore: gravar leitura/status, ler leitura atual
    redis_client.py      # conexão com o Redis
    limite.py            # limite de perguntas por chave (janela fixa)
    contexto.py          # contexto curto da conversa no Redis (últimas trocas, com validade)
    seguranca.py         # X-API-Key (tempo constante) e regra do device_id
    routes/
      ia.py              # POST /perguntar
      audio.py           # POST /audio
    ai/
      estado.py          # estado da planta (limiares) e frescor dos dados
      prompt.py          # personalidade da planta + dados reais + regras da rega
      responder.py       # única porta para o Gemini (texto e áudio)
      resiliencia.py     # retry, timeout e modelo reserva
      audio.py           # validar/medir o áudio recebido
      voz.py             # TTS (texto -> WAV)
      tela.py            # decide a tela do display (rosto ou dados)
    agenda/
      regras.py          # limites e horário da rega (funções puras)
      fala.py            # frases faladas de confirmação/recusa
      repositorio.py     # agendamentos no Firestore
      agendador.py       # executa no horário, sem duplicar
      servico.py         # junta tudo: pedido do Gemini -> validar -> agendar
  tests/                 # testes automatizados (pytest) e scripts manuais
  mosquitto/mosquitto.conf
  Dockerfile
  docker-compose.yml
  .env.example
  requirements.txt
  serviceAccountKey.json # chave do Firebase (ignorada pelo git, NUNCA commitar)
```

## Rodando localmente

Pré-requisitos: Docker, Docker Compose e a chave de serviço do Firebase.

```bash
cd backend
cp .env.example .env
# edite o .env: GEMINI_API_KEY, API_KEY (gere com: openssl rand -hex 24) e, se quiser, os modelos
# salve a chave do Firebase como backend/serviceAccountKey.json (nunca commitar)
docker compose up
```

Sobe o backend com hot-reload na porta 8000, um broker MQTT local (Mosquitto) e o Redis. Depois de mudar o `requirements.txt`, rode `docker compose build backend`.

Teste rápido, publicando uma leitura simulada:

```bash
docker compose exec mosquitto mosquitto_pub -h localhost -t "greensync/vaso-01/sensores" \
  -m '{"ph": 6.4, "umidade_solo": 42, "temperatura_ar": 24.1, "umidade_ar": 58, "bomba_ligada": false}'
```

A leitura aparece no log (`leitura válida` e `leitura gravada no Firestore`) e em `devices/vaso-01` no Firestore.

Teste do assistente em texto:

```bash
curl -s -X POST http://localhost:8000/perguntar \
  -H "Content-Type: application/json" -H "X-API-Key: SUA_CHAVE" \
  -d '{"device_id":"vaso-01","pergunta":"Como você está?"}'
```

Teste da rega por voz (em texto): troque a pergunta por `"Rega a planta daqui a 1 minuto"` e, em outro terminal, escute os comandos:

```bash
docker compose exec mosquitto mosquitto_sub -t 'greensync/+/comandos' -v
```

### Conectando no EMQX Cloud (em vez do Mosquitto local)

No `.env`, preencha host, porta (8883), usuário e senha do cluster e defina `MQTT_USE_TLS=true`. A conexão TLS usa o contexto padrão do sistema, sem certificado customizado.

## Testes

```bash
docker compose run --rm backend python -m pytest tests/ -v
```

A suíte (440 testes) roda sem Gemini, Firestore, Redis ou MQTT reais: tudo é simulado, e cada teste usa os valores padrão de `app/config.py` (o `.env` não influencia o resultado). Cobre o estado e o frescor dos dados, o prompt, a resiliência do Gemini, a validação do áudio, a voz, as duas rotas, o limite de perguntas, as regras da rega, o agendador (inclusive reinício sem duplicar), a publicação do comando e a entrada MQTT (id do vaso, timestamp, reconexão).

Scripts **manuais** (gastam cota do Gemini, por isso não rodam no pytest; precisam do `.env` com `GEMINI_API_KEY`):

| Script | O que faz |
|---|---|
| `python -m tests.manual_gemini` | Faz perguntas em texto e mostra as respostas da planta |
| `python -m tests.manual_audio` | Testa o áudio de ponta a ponta: pergunta falada, entendimento e voz de resposta (WAV) |
| `python -m tests.manual_rega` | Mostra como o Gemini entende 11 pedidos de rega e se o backend aceitaria; não grava nem aciona nada |

Rodar com `docker compose run --rm backend python -m tests.<nome>`. Gravações de voz e áudios gerados ficam em `tests/amostras/` e `tests/saida/`, que o `.gitignore` ignora: **a voz de ninguém deve ir para o GitHub**.

## API

### `POST /perguntar` (texto)

Cabeçalho `X-API-Key`. Corpo: `{"device_id": "vaso-01", "pergunta": "..."}`. Responde `{texto, estado, tela, modelo, rega}`.

### `POST /audio` (voz)

Cabeçalhos `X-API-Key`, `X-Device-Id` e `Content-Type: audio/wav`. Corpo: WAV 16 kHz, 16 bits, mono, até 15 s e 1 MB. Responde um WAV (a voz da planta) com os cabeçalhos `X-Tela` (`rosto` ou `dados`) e `X-Dados` (JSON com `ph`, `solo`, `temp`, `ar` e `atuais`). Com `?debug=true` traz também `X-Ouviu`, `X-Texto` e `X-Modelo`.

| Código | Quando |
|---|---|
| 401 | `X-API-Key` ausente ou inválida |
| 413 | corpo maior que o máximo |
| 422 | `device_id` inválido ou áudio vazio, ilegível, de formato não aceito ou longo demais |
| 429 | limite de perguntas atingido (traz `Retry-After`) |
| 502 | Gemini ou voz indisponíveis |

Contrato completo (e o que o firmware do S3 precisa saber, como o timeout de pelo menos 30 s): `docs/Arc42_GreenSync_SDD.md`, Seção 8.4.

### Rega por voz

Funciona nas duas rotas: se a pessoa pedir ("regar daqui a 1 minuto", "cancela a rega"), o backend valida e a resposta falada já traz a confirmação ou a recusa. Limites padrão: atraso máximo de 24 h, duração máxima de 10 s (padrão 5 s; a demonstração usa 15 s no `.env`), 10 min entre regas, recusa com o vaso offline ou o solo acima de 80%. Ver Seção 8.5 do Arc42.

## Contrato MQTT

Detalhes completos em `docs/Arc42_GreenSync_SDD.md`, Seção 8.1.

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
  `umidade_ar` e `timestamp` são opcionais; sem `timestamp`, o backend usa a hora do servidor.
- **Status** — `greensync/{deviceId}/status` → `{"status": "online"}` (retido, ao conectar) ou `{"status": "offline"}` (Last Will do broker).
- **Comandos** (backend → vaso) — `greensync/{deviceId}/comandos`, QoS 1, **sem retain**:
  ```json
  {"acao": "regar", "duracao_s": 5, "id": "<idAgendamento>"}
  ```
  O firmware deve assinar esse tópico, **ignorar `id` repetido** e manter o próprio tempo máximo de bomba ligada.

Payload que não bate com o modelo é logado e descartado, sem derrubar o backend.

## Firestore

```
devices/{deviceId}
  status, last_seen
  leitura_atual: { ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, updated_at }
  historico/{autoId}      ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, timestamp
  agendamentos/{id}       quando, duracao_s, status, origem, motivo, criado_em, atualizado_em
```

`leitura_atual` é sobrescrito a cada mensagem e o `historico` acumula, no mesmo batch. Os agendamentos têm status `pendente`, `executando`, `concluida`, `cancelada`, `expirada` ou `falhou` (`concluida` = comando publicado). O app pode cancelar uma rega mudando o status de `pendente` para `cancelada`.

## Variáveis de ambiente

Todas têm padrão; o `.env.example` traz as principais.

| Variável | Descrição |
|---|---|
| `MQTT_HOST` / `MQTT_PORT` | Endereço do broker (Mosquitto local ou EMQX Cloud) |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | Credenciais do broker (vazias no Mosquitto local) |
| `MQTT_USE_TLS` | `false` local, `true` no EMQX Cloud |
| `MQTT_TOPIC_SENSORES` / `MQTT_TOPIC_STATUS` | Tópicos assinados |
| `MQTT_TOPIC_COMANDOS` | Tópico dos comandos (`greensync/{device_id}/comandos`) |
| `FIREBASE_CREDENTIALS_PATH` | Caminho da chave de serviço do Firebase |
| `GEMINI_API_KEY` | Chave da API do Gemini |
| `GEMINI_MODEL` / `GEMINI_MODEL_FALLBACK` | Modelo principal (padrão `gemini-3.5-flash-lite`) e reserva (`gemini-3.1-flash-lite`, usada se o principal der timeout ou 5xx) |
| `TTS_MODEL` / `TTS_MODEL_FALLBACK` | Modelos da voz (opcionais) |
| `TTS_VOICE` / `TTS_ESTILO` / `TTS_SAMPLE_RATE` | Voz, estilo de fala e taxa de amostragem da resposta (opcionais) |
| `API_KEY` | Chave exigida no `X-API-Key` (vazia = rotas abertas, só para desenvolvimento) |
| `REDIS_URL` | Ex.: `redis://redis:6379/0` (vazia = limite de perguntas desligado) |
| `LIMITE_PERGUNTAS` / `JANELA_LIMITE_S` | Perguntas permitidas por janela (padrão 10 por 60 s) |
| `CONTEXTO_TURNOS` / `CONTEXTO_TTL_S` / `CONTEXTO_MAX_CHARS` | Trocas lembradas (padrão 3; 0 desliga), validade em segundos (300) e tamanho máximo de cada fala guardada (300) |
| `LEITURA_VELHA_APOS_S` | Segundos sem leitura para os dados serem tratados como velhos (padrão 120) |
| `REGA_ATRASO_MAX_S`, `REGA_DURACAO_MAX_S`, `REGA_DURACAO_PADRAO_S`, `REGA_INTERVALO_MIN_S`, `REGA_TOLERANCIA_S` | Limites da rega por voz |
| `FUSO_UTC_H` | Fuso para "às 15h" (Brasília = -3) |
| `GEMINI_TIMEOUT_S` / `GEMINI_TIMEOUT_AUDIO_S` / `TTS_TIMEOUT_S` | Prazo por chamada ao Gemini, em segundos: texto (padrão 8), áudio (25) e voz (15) |
| `FIRESTORE_TIMEOUT_S` | Prazo para ler os dados do vaso no Firestore (padrão 5 s); passou disso, a pergunta segue como "sem dados" |
| `AUDIO_MAX_BYTES` / `AUDIO_MAX_S` | Tamanho (padrão 1000000 bytes) e duração (15 s) máximos do áudio recebido |
| `TOM_PLANTA` | `planta` (divertido, padrão) ou `informativo` |
| `SOLO_SECO_ABAIXO` / `SOLO_ENCHARCADO_ACIMA` / `TEMP_MIN` / `TEMP_MAX` / `PH_MIN` / `PH_MAX` | Limiares do estado da planta (padrão 30 %, 80 %, 10 °C, 35 °C, 5,5 e 7,5) |
| `LOG_LEVEL` | Nível de log (`DEBUG`, `INFO`, `WARNING`...; valor desconhecido vale `INFO`) |

## Estado atual

| Módulo | Estado |
|---|---|
| Assinante MQTT com reconexão + TLS | Implementado |
| Validação de payload e gravação no Firestore (leitura atual + histórico + status) | Implementado |
| Dados velhos e vaso offline tratados no assistente | Implementado |
| Limite de perguntas no Redis (429 + `Retry-After`) | Implementado |
| `POST /perguntar` e `POST /audio` (Gemini + voz) | Implementado |
| Rega por voz, agendamento persistente e comando MQTT | Implementado (execução no horário com o vaso real ainda não testada) |
| Teste do Last Will com o firmware | Pendente |
| Contexto curto da conversa no Redis (últimas 3 trocas, 5 min) | Implementado |
| Deploy no Render (`$PORT` dinâmico, chave do Firebase como Secret File, EMQX no lugar do Mosquitto) | Pendente |
| Teste de ponta a ponta com firmware e app | Pendente |

## Produção (Render)

O `Dockerfile` builda a imagem; falta ajustar o `CMD` para usar a variável `$PORT` do Render em vez de porta fixa e subir a chave do Firebase como Secret File (nunca no build da imagem). Em produção, use o Redis do Render (Key Value), o broker EMQX Cloud no lugar do Mosquitto e uma `API_KEY` aleatória (`openssl rand -hex 24`). O backend deve rodar em **instância única** (duas instâncias gravariam cada leitura em dobro). As demais variáveis de ambiente vão direto no painel do Render.