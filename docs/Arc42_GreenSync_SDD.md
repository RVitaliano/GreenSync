# Arc42 — Documento de Arquitetura de Software (SDD) — GreenSync

> **Versão 0.8 — 23/11/2026.** Atualizado com o firmware do WROOM funcionando (sensores reais, bomba, BLE e OTA), a rega somente por comando (ADR-031), a configuração de Wi-Fi por BLE (ADR-029), a atualização OTA (ADR-030, Seção 8.11) e a palavra de ativação no S3 (ADR-032). Versão anterior: **0.7 — 09/11/2026.** O pH passa a ser falado sempre com o valor exato (Seção 8.6, ADR-027), as rotas ganham testes contra falha real do Firestore (Seção 8.8) e entra a estratégia de testes (Seção 8.10, ADR-028, com o Plano de Testes em formato IEEE 829). Versão anterior: **0.6 — 09/11/2026.** Revisão do backend: trava de palavra também no cancelamento, publicação incerta de comando, Firestore lento tratado como "sem dados", padrões do Gemini e novas limitações conhecidas (Seções 8.5, 8.8 e 11). Versão anterior: **0.5 — 03/11/2026.** Atualizado com o backend implementado (inclui o contexto curto da conversa no Redis): contrato HTTP de áudio (Seção 8.4), contrato do tópico de comandos (8.1), esquema dos agendamentos (8.2), limites da rega (8.5), frescor dos dados, resiliência e limite de perguntas (8.7 a 8.9) e as ADR-024 a ADR-026. Atualizações anteriores: 01/10/2026 (ADR-023, display no ESP32-S3) e 21/09/2026 (ADR-014 a ADR-022). 

---

# 1. Introduction and Goals

## 1.1 Requirements Overview

O GreenSync é um vaso inteligente que monitora pH do solo, umidade do solo, temperatura e umidade do ar, controla a irrigação por comandos validados, sincroniza dados em tempo real com um aplicativo mobile e responde perguntas faladas sobre a planta. O assistente "fala como a planta" (primeira pessoa, com base nos dados reais dos sensores) e também pode agendar regas por comando de voz, sempre com validação no backend e limites no firmware.

O sistema usa **dois microcontroladores**: um ESP32-WROOM (sensores e bomba, comunicação via MQTT) e um ESP32-S3 (voz e display, comunicação via HTTP com o backend). Ver o documento SRS — Requisitos para a especificação completa e verificável.

## 1.2 Quality Goals

| Prioridade | Meta de qualidade | Motivação |
|---|---|---|
| 1 | Confiabilidade dos dados de sensor | pH e umidade alimentam a irrigação automática — dado ruim gera decisão errada (rega demais/de menos) |
| 2 | Segurança da atuação | Rega por voz ou agenda não pode alagar o vaso nem queimar a bomba: limites no backend **e** no firmware |
| 3 | Simplicidade de integração entre as três frentes | Grupo pequeno (3 pessoas), trabalho paralelo depende de contratos de interface bem definidos (MQTT/JSON, Firestore, HTTP de áudio) |
| 4 | Baixo custo operacional | Projeto acadêmico — camadas gratuitas onde possível; o único custo recorrente previsto é o serviço pago do Render (valor a confirmar, ver ADR-019) |

## 1.3 Stakeholders

| Role/Name | Contact | Expectations |
|---|---|---|
| Frente — Hardware/Firmware | Equipe GreenSync | Contratos MQTT (WROOM) e HTTP de áudio (S3) estáveis e definidos cedo, para trabalhar em paralelo |
| Frente — App/Design | Equipe GreenSync | Esquema do Firestore estável, para consumir dados corretamente no app |
| Frente — Backend | Equipe GreenSync | Visão completa da integração entre hardware, nuvem, IA e app |
| Avaliadores da demonstração | — | Ver o projeto funcionando de ponta a ponta e entender as decisões técnicas (MQTT, Redis, IA) |

---

# 2. Architecture Constraints

- Protocolo de comunicação entre o dispositivo de sensores e a nuvem é MQTT; broker **EMQX Cloud** (ADR-014).
- Dois microcontroladores: **ESP32-WROOM** (sensores, bomba) e **ESP32-S3** (voz e display) (ADR-016, ADR-023).
- Backend em Python + FastAPI, em **processo único** com `async`/`await`, **sem Celery** (ADR-013, ADR-015).
- **Redis** presente na arquitetura; usos definidos na ADR-015.
- Aplicativo em Flutter.
- Banco de dados em nuvem: Firebase (Firestore).
- LLM: Google Gemini (ADR-004, ADR-018).
- Sem armazenamento local/offline (ver ADR-010).
- Orçamento operacional: camadas gratuitas onde possível, mais um serviço pago no Render (ADR-019).
- Alimentação elétrica única em 5V, sem bateria.

---

# 3. Context and Scope

## 3.1 Business Context

O usuário final interage com o aplicativo mobile, com o "rosto" exibido no display do vaso (que alterna para os dados dos sensores ao ser feita uma pergunta, ver ADR-023) e, por voz, com o assistente ("planta que fala"). Não há interação direta do usuário com o backend, o broker MQTT, o Redis ou o Firebase — esses são componentes internos, invisíveis ao usuário final.

```
Usuário ──(usa)──> App (Flutter)
Usuário ──(observa)──> Vaso GreenSync (display OLED, no ESP32-S3)
Usuário ──(fala com)──> Vaso GreenSync (ESP32-S3: microfone e alto-falante)
```

## 3.2 Technical Context

```
ESP32-WROOM ──MQTT/TLS──> EMQX Cloud ──MQTT/TLS──> Backend (FastAPI, Render) ──> Firebase (Firestore) ──> App (Flutter)
 (sensores,      ▲                                    │   │
  bomba)         └──── comandos de rega (MQTT) ───────┘   └──> Redis (contexto, limite de perguntas)
                                                       │
ESP32-S3 ──HTTPS + X-API-Key──> Backend ──────────────┴──> Google Gemini (LLM / áudio de entrada)
 (voz, display)   <─── áudio da resposta + estado da tela ───┘   Gemini TTS (voz)
```

Os dois ESPs pertencem ao mesmo vaso lógico (`deviceId`, ex.: `vaso-01`), e o backend é o único ponto que os conecta. O app configura o Wi-Fi do WROOM por BLE (ADR-029), e o WROOM baixa as atualizações de firmware do GitHub (ADR-030).

---

# 4. Solution Strategy

A estratégia central é manter os firmwares simples e concentrar a lógica no backend. O **WROOM** só lê sensores, controla a bomba e fala MQTT; o **S3** só captura e reproduz áudio, executa a troca de tela do display e fala HTTP. Validação, persistência, orquestração de IA, agendamento, decisão de atuação e decisão do que o display mostra ficam no backend, o que desacopla as frentes de hardware das mudanças na nuvem.

Decisões que sustentam essa estratégia:

- **MQTT para sensores** (em vez de o ESP escrever direto no Firebase): é um protocolo leve, de publicação e assinatura, e tolera melhor conexões intermitentes.
- **HTTP para áudio**: áudio é grande demais para o MQTT, que é feito para mensagens pequenas (ADR-017).
- **A rega é sempre um comando validado pelo backend** (app, voz ou agenda), e o firmware aplica as próprias defesas (tempo máximo, `id` repetido ignorado). Não há irrigação automática no firmware (ADR-031).
- **Processo único** (uvicorn) com `async`/`await`, sem workers: a chamada ao LLM roda dentro da requisição e as regas agendadas viram tarefas `asyncio` persistidas no Firestore (ADR-015, ADR-021).
- **Display junto com a voz, no mesmo dispositivo (S3)**: a troca de tela acontece no mesmo momento em que o assistente responde, então fica no mesmo HTTP de áudio em vez de depender de uma segunda via de comunicação para sincronizar os dois ESPs (ADR-023).
- **Construção em camadas**: cada peça é validada isoladamente (Docker → MQTT → validação → Firestore → Redis → IA em texto → áudio) antes de a próxima ser adicionada.

---

# 5. Building Block View

## 5.1 Whitebox Overall System

**Motivation**

O sistema é dividido em blocos alinhados às responsabilidades das três frentes: firmware (dois dispositivos), backend e app. Broker MQTT, Redis, Firebase e Gemini são serviços de terceiros configurados pelo grupo, não código próprio.

**Contained Building Blocks**

### Firmware WROOM (ESP32-WROOM)

- Purpose/Responsibility: ler sensores (pH, umidade do solo, temperatura e umidade do ar), controlar a bomba d'água somente por comando, publicar leituras e status via MQTT, assinar o tópico de comandos (rega, atualização e reversão), aplicar limite de tempo máximo de bomba ligada, configurar o Wi-Fi por BLE (ADR-029) e atualizar o próprio firmware pela rede (OTA, ADR-030). Não possui display — o WROOM não tem indicação visual local (ADR-023).
- Interface(s): MQTT sobre TLS (publisher e assinante) e BLE (configuração de Wi-Fi).
- Fulfilled Requirements: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-007 (lado do dispositivo), REQ-FUNC-011 (execução), REQ-FUNC-013, REQ-FUNC-017.
- Open Issues/Problems/Risks: confiabilidade da sonda de pH e desgaste do sensor de solo resistivo (Seção 11); lógica não bloqueante para conviver com a conexão MQTT persistente; validação do certificado do broker e do download do OTA, ainda desativada na bancada (Seção 8.3).

### Firmware S3 (ESP32-S3)

- Purpose/Responsibility: capturar o áudio da pergunta (microfone INMP441), enviá-lo ao backend por HTTP, reproduzir o áudio da resposta no alto-falante, oferecer mute físico do microfone, e controlar o display OLED (SSD1306) — por padrão mostrando uma carinha que representa a personalidade da planta (ADR-021) e trocando temporariamente para os dados dos sensores quando o backend indica, ao final de uma pergunta por voz (ADR-023, REQ-FUNC-016). O firmware do S3 só executa a troca de tela; não decide sozinho quando trocar. A palavra de ativação ("Hi ESP", ADR-032) é detectada no próprio S3, e a rede Wi-Fi chega pela ponte UART com o WROOM (ADR-029).
- Interface(s): HTTPS para o backend, com `X-API-Key` (Seção 8.4).
- Fulfilled Requirements: REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-014 (lado do cliente), REQ-FUNC-016, REQ-FUNC-018.
- Open Issues/Problems/Risks: qualidade do áudio (I2S) e estabilidade da fiação do protótipo; o formato do áudio enviado e o estado da tela já estão definidos no backend (Seção 8.4), e o cliente do S3 está em desenvolvimento; o áudio de resposta tem cerca de 350 a 380 KB (24 kHz), o que cabe nos 8 MB de PSRAM do S3 (Seção 11).

### Broker MQTT (EMQX Cloud)

- Purpose/Responsibility: receber mensagens publicadas pelo WROOM e redistribuí-las ao backend assinante; entregar comandos do backend ao WROOM; publicar a mensagem de "last will" em caso de desconexão inesperada.
- Interface(s): MQTT sobre TLS (porta 8883). Alternativa contra firewall: MQTT sobre WebSocket seguro na 443.
- Fulfilled Requirements: REQ-FUNC-003, REQ-FUNC-007, REQ-FUNC-011.
- Open Issues/Problems/Risks: limites do plano serverless do EMQX Cloud (ver Seção 11).

### Backend (Python + FastAPI, Render)

- Purpose/Responsibility: assinar os tópicos MQTT, validar e gravar dados no Firestore; expor os endpoints de IA (`/perguntar` em texto, `/audio`); orquestrar Gemini e TTS; validar e agendar regas; publicar comandos MQTT; decidir o que o display do S3 deve mostrar (carinha ou dados dos sensores) a cada resposta de voz (ADR-023).
- Interface(s): cliente MQTT (assinante e publisher); SDK Admin do Firebase; API do Google Gemini (entendimento do áudio e TTS); Redis; HTTP (FastAPI) para o S3 e, se necessário, para o app.
- Fulfilled Requirements: REQ-FUNC-004, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-014, REQ-FUNC-015, REQ-FUNC-016.
- Open Issues/Problems/Risks: memória do plano Starter (512 MB) com API, assinante MQTT e IA no mesmo processo; instância única obrigatória (Seção 7).

### Redis

- Purpose/Responsibility: contexto curto da conversa por dispositivo (com expiração) e limite de perguntas por chave de API. Uso como cache da última leitura é opcional.
- Interface(s): protocolo Redis, acessado só pelo backend, via `REDIS_URL`.
- Fulfilled Requirements: REQ-FUNC-015 (e apoio ao REQ-FUNC-008).
- Open Issues/Problems/Risks: o Redis guarda só dados descartáveis (contador do limite e as últimas trocas da conversa); se faltar ou cair, o assistente segue sem limite e sem contexto; no plano gratuito do Render, o Key Value (se disponível) é só em memória e perde dados ao reiniciar — aceito, pois o conteúdo é descartável.

### Firebase (Firestore)

- Purpose/Responsibility: armazenar a leitura atual, o histórico e os agendamentos de cada dispositivo; sincronizar em tempo real com o app.
- Interface(s): SDK Admin (backend, escrita); FlutterFire (app, leitura em tempo real).
- Fulfilled Requirements: REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-012.

### App (Flutter)

- Purpose/Responsibility: exibir dados em tempo real, histórico, estado da planta e status online/offline; único meio de acompanhamento visual do usuário (sem dashboard web).
- Interface(s): FlutterFire (Firestore), HTTP (pedido de rega) e BLE (configuração de Wi-Fi do vaso).
- Fulfilled Requirements: REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007 (exibição), REQ-FUNC-013 (envio da rede).

### Name interface 1 — Tópicos MQTT (WROOM ↔ Broker ↔ Backend)

Contrato de tópicos e payload JSON entre firmware e backend. Ver Seção 8.1.

### Name interface 2 — Esquema do Firestore (Backend ↔ App)

Estrutura de coleções e documentos que o backend escreve e o app lê. Ver Seção 8.2.

### Name interface 3 — API HTTP de áudio (S3 ↔ Backend)

Contrato de endpoint, cabeçalhos e formato de áudio entre o S3 e o backend, incluindo o campo de estado da tela. Ver Seção 8.4.

## 5.2 Level 2

### White Box: Firmware WROOM

Módulos internos: leitura de sensores (com calibração do sensor de solo e descarte de leituras inválidas do DHT22), execução de comandos de rega (`id` repetido ignorado e tempo máximo de bomba), cliente MQTT (publicação, Last Will, assinatura de comandos), provisionamento de Wi-Fi por BLE e atualização OTA com rollback.

### White Box: Firmware S3

Módulos internos: captura de áudio (I2S), botão de falar e mute, cliente HTTP, reprodução de áudio (I2S), detecção da palavra de ativação, controle do display OLED (carinha/dados, ADR-023) e ponte UART com o WROOM para a rede.

### White Box: Backend

| Módulo | Responsabilidade | Estado |
|---|---|---|
| `config.py` | Variáveis de ambiente (pydantic-settings): MQTT, Firebase, Gemini, voz, limiares, rega e Redis | Implementado |
| `models.py` | Validação dos payloads MQTT (`SensorReading`, `DeviceStatus`) | Implementado |
| `mqtt_client.py` | Assinante MQTT assíncrono, reconexão, roteamento e descarte de payload inválido; `publicar_comando` (QoS 1, sem retain) pela mesma conexão | Implementado |
| `firebase_client.py` | Gravação da leitura atual + histórico e do status, em lote (batch); leitura da leitura atual junto com o status do vaso | Implementado |
| `main.py` | FastAPI, `lifespan` (Firebase, assinante MQTT, agendador, Redis) | Implementado |
| `redis_client.py`, `limite.py` | Conexão com o Redis e limite de perguntas por chave de API (janela fixa) | Implementado |
| `seguranca.py` | Validação da `X-API-Key` (tempo constante) e do `device_id` | Implementado |
| `ai/estado.py` | Estado da planta (limiares) e frescor dos dados (online/offline, leitura velha) | Implementado |
| `ai/prompt.py` | Prompt da personalidade da planta com os dados reais, o estado e as regras do pedido de rega | Implementado |
| `ai/responder.py`, `ai/resiliencia.py` | Única porta para o Gemini (`responder`, `responder_audio`), saída JSON com resposta e pedido de rega, retry e modelo reserva | Implementado |
| `ai/audio.py`, `ai/voz.py` | Validação e medição do áudio recebido; TTS do Gemini (WAV) | Implementado |
| `ai/tela.py` | Decisão do estado da tela (`rosto` ou `dados`, ADR-023) | Implementado |
| `routes/ia.py`, `routes/audio.py` | `POST /perguntar` (texto) e `POST /audio`, com `X-API-Key` | Implementado |
| `routes/dispositivos.py` | `POST /dispositivos/{id}/regar` (rega manual do app), `/atualizar` e `/reverter` | Implementado |
| `routes/firmware.py`, `ota/` | Registro de firmware (`PUT /firmware/{alvo}`, `/retirar`), validação de versão, URL e SHA-256, OTA automático opcional | Implementado |
| `agenda/regras.py`, `agenda/fala.py` | Regras de validação da rega e frases faladas de confirmação, recusa e cancelamento | Implementado |
| `agenda/repositorio.py`, `agenda/agendador.py`, `agenda/servico.py` | Persistência no Firestore, execução no horário sem duplicar, recarga no reinício e orquestração do pedido | Implementado (execução no horário ainda não confirmada com o vaso real) |
| Contexto da conversa (Redis) | Últimas 3 trocas por dispositivo, com expiração de 5 min (`app/contexto.py`) | Implementado |

## 5.3 Level 3

Não detalhado nesta versão do documento — nível de profundidade não necessário para o porte do projeto.

---

# 6. Runtime View

## 6.1 Runtime Scenario 1 — Ciclo normal de leitura e sincronização

1. O firmware WROOM lê pH, umidade do solo, temperatura e umidade do ar. Se a leitura do DHT22 falhar, não publica.
2. O firmware publica um payload JSON no tópico `greensync/{deviceId}/sensores`.
3. O broker EMQX recebe a mensagem e a repassa ao backend assinante.
4. O backend valida o payload (`SensorReading`); se for inválido, registra em log e descarta.
5. O backend grava a leitura atual (sobrescrevendo) e adiciona um registro ao histórico no Firestore, em um único lote.
6. O app, com um listener ativo no Firestore, atualiza a tela automaticamente.

## 6.2 Runtime Scenario 2 — Rega por comando (execução no firmware)

1. O backend publica `{"acao":"regar","duracao_s":N,"id":...}` em `greensync/{deviceId}/comandos` (origem: botão do app, pedido por voz ou agenda, já validado, cenário 6.4).
2. O firmware confere se o `id` já foi executado (repetido é ignorado) e limita a duração a `BOMBA_MAX_S` (15 s), mesmo que o comando peça mais.
3. O firmware liga a bomba (relé em nível baixo), publica `bomba_ligada: true` na leitura seguinte e desliga ao fim do tempo.
4. O firmware nunca rega por conta própria (ADR-031). A recusa de regas com a bomba já ligada, o intervalo mínimo e o solo encharcado são conferidos pelo backend.

## 6.3 Runtime Scenario 3 — Pergunta ao assistente de voz (V2)

1. O usuário diz a palavra de ativação ("Hi ESP", ADR-032) e faz a pergunta (nos testes, um botão pode acionar a captura). Até aqui, o display do S3 mostra a carinha da planta (padrão, ADR-023).
2. O S3 envia o áudio ao backend por `POST /audio`, com `X-API-Key` e o `deviceId`.
3. O backend valida a `X-API-Key` e o `X-Device-Id` e valida o áudio (formato, tamanho e duração); só então conta a pergunta no limite do Redis. Chave errada e áudio inválido não gastam o limite.
4. O backend lê a leitura atual do Firestore e as últimas trocas da conversa no Redis (Seção 8.9), calcula o estado da planta (limiares configuráveis) e se o dado é recente (Seção 8.7), e monta o prompt com a personalidade da planta.
5. Uma única chamada ao Gemini recebe o áudio (entrada direta, sem STT separado, validada em testes) e devolve um JSON com `pergunta_ouvida`, `resposta` e `acao` (pedido de rega, cenário 6.4). Se o modelo principal estiver lento ou fora do ar, entra o modelo reserva (Seção 8.8).
6. O texto da resposta vai ao TTS do Gemini, que gera o áudio WAV; com a voz pronta, a troca (transcrição e frase falada) é guardada no contexto da conversa. O backend decide a tela a partir da transcrição (`pergunta_ouvida`): dados dos sensores (ex.: pergunta sobre temperatura) ou carinha (ADR-023).
7. O backend devolve, na mesma requisição HTTP, o WAV da resposta e os cabeçalhos `X-Tela` e `X-Dados` (Seção 8.4). O S3 reproduz o áudio e aplica a troca de tela, voltando à carinha ao final da resposta.

## 6.4 Runtime Scenario 4 — Rega agendada por voz ("regar daqui 1 minuto")

1. O usuário pede a rega por voz (mesmo fluxo do cenário 6.3, até o Gemini).
2. O Gemini devolve, junto da resposta, o campo estruturado `acao` (`regar` ou `cancelar`, com `daqui_a_s` ou `as_hora` e, se a pessoa disser, `duracao_s`). Ele só entende o pedido: nunca aciona a bomba (ADR-025).
3. O backend confere que a fala da pessoa realmente pede rega e valida o pedido: atraso máximo, duração máxima, intervalo mínimo entre regas, vaso online e solo não encharcado (Seção 8.5). A frase falada é escrita pelo backend e informa a confirmação ou a recusa.
4. Se aceitar, o backend grava o agendamento no Firestore como `pendente` e cria uma tarefa `asyncio` em memória.
5. Na hora marcada, o backend reivindica o agendamento (`pendente` para `executando`, em transação, antes de publicar), confere de novo se o vaso está online e o solo não está encharcado, e publica o comando em `greensync/{deviceId}/comandos`.
6. O firmware WROOM liga a bomba pelo tempo pedido (limitado pelo tempo máximo do próprio firmware), desliga e publica `bomba_ligada`.
7. O backend marca o agendamento como `concluida` (comando publicado) ou `falhou` (com o `motivo`). Se o backend reiniciar, ele recarrega os `pendente` no startup: um agendamento atrasado até 5 minutos é executado uma vez; além disso vira `expirada`. Um agendamento encontrado como `executando` no startup vira `falhou` e nunca é repetido.
8. Cancelar por voz ("cancela a rega") cancela a rega pendente mais próxima. O app também pode cancelar mudando o `status` de `pendente` para `cancelada` no Firestore: o backend só executa o que ainda estiver `pendente` no momento de disparar.

## 6.5 Runtime Scenario 5 — Dispositivo offline

1. Ao conectar, o firmware WROOM publica `{"status": "online"}` em `greensync/{deviceId}/status` (com retain) e registra o Last Will `{"status": "offline"}` no mesmo tópico.
2. Se o WROOM cair sem desconexão limpa, o broker publica o Last Will.
3. O backend recebe o status e atualiza o campo `status` do dispositivo no Firestore.
4. O app exibe "offline", evitando que o usuário confunda um dado antigo com um dado atual. Como o WROOM não tem display (ADR-023), essa indicação no app é o único aviso visual de que o dispositivo de sensores está offline — mesmo que o S3 continue ligado e respondendo por voz.

## 6.6 Runtime Scenario 6 — Primeira configuração de Wi-Fi (ou troca de rede)

1. Sem rede salva (ou depois de 4 falhas seguidas de conexão), o WROOM passa a anunciar o BLE `GreenSync_BLE`.
2. No app, o usuário conecta ao `GreenSync_BLE` e informa a rede e a senha, enviadas como `ssid,senha`.
3. O vaso tenta conectar e notifica o app (`conectando`, `ok` ou `erro:senha`, `erro:rede`, `erro:timeout`).
4. Só depois de conectar com sucesso as credenciais são gravadas na memória (NVS); uma senha errada não apaga a rede anterior.

## 6.7 Runtime Scenario 7 — Atualização de firmware (OTA)

1. Uma nova versão é publicada como *release* no GitHub, e a GitHub Action registra versão, URL e SHA-256 no backend (`PUT /firmware/{alvo}`).
2. O backend publica `{"acao":"atualizar", ...}` em `greensync/{deviceId}/comandos` (pela rota `/atualizar` ou automaticamente, se `OTA_AUTO` estiver ligado), depois de conferir que o vaso está online e com a bomba desligada.
3. O vaso baixa o binário por HTTPS de `github.com`, calcula o SHA-256 enquanto grava na partição inativa e publica o progresso em `greensync/{deviceId}/ota`.
4. Se o hash bater, o vaso reinicia na nova partição. O firmware novo precisa se confirmar (conectar ao MQTT); se não o fizer em 5 minutos, ou reiniciar mais de 3 vezes sem se confirmar, o vaso volta sozinho à versão anterior.
5. Uma versão ruim pode ser desfeita por `POST /dispositivos/{id}/reverter` e retirada do registro por `POST /firmware/{alvo}/retirar`, que a bloqueia.

---

# 7. Deployment View

## 7.1 Infrastructure Level 1

**Motivation**

A infraestrutura usa serviços de terceiros, com camadas gratuitas onde possível. O assinante MQTT precisa ficar sempre ativo, o que exige um serviço pago no Render (ADR-019).

**Quality and/or Performance Features**

Custo baixo (um serviço pago; valores a confirmar no site do Render antes de contratar); instância única (duas instâncias gravariam cada leitura em dobro); sem redundância geográfica.

**Mapping of Building Blocks to Infrastructure**

| Building Block | Infraestrutura |
|---|---|
| Firmware WROOM | ESP32-WROOM físico, no vaso |
| Firmware S3 | ESP32-S3 físico, no vaso (com display OLED) |
| Broker MQTT | EMQX Cloud (serverless) |
| Backend | Render — serviço web pago (Starter, 512 MB de RAM), instância única, sempre ativo |
| Redis | Render Key Value |
| Banco de dados | Firebase Firestore, região `southamerica-east1` |
| LLM / áudio de entrada | Google Gemini API (camada gratuita) |
| Binários do firmware (OTA) | GitHub Releases |
| App | Dispositivos móveis dos usuários/avaliadores |

## 7.2 Infrastructure Level 2

### Infrastructure Element 1 — Empacotamento do backend (Docker)

O backend é empacotado em uma imagem Docker (`Dockerfile`), usada tanto para o deploy no Render quanto para o desenvolvimento local (ADR-012). Localmente, um `docker-compose.yml` sobe o backend (com hot-reload) e um broker MQTT local (Eclipse Mosquitto); o Redis entra como serviço adicional:

```
docker-compose.yml (ambiente local)
├── backend      (FastAPI, hot-reload, porta 8000; monta serviceAccountKey.json como volume somente leitura)
├── mosquitto    (broker MQTT local, para desenvolver sem depender do EMQX Cloud)
└── redis        (Redis 7, só na rede interna do compose; guarda o contador do limite de perguntas)
```

A chave de serviço do Firebase fica **fora da imagem**: é montada como volume em desenvolvimento e configurada como variável/arquivo secreto no Render. Em produção roda apenas o container do backend, apontando para o EMQX Cloud, o Redis e o Firebase — sem Mosquitto.

### Infrastructure Element 2 — Processos no serviço do Render

O serviço roda **um processo** (uvicorn): API HTTP, assinante MQTT e chamadas à IA. Não há worker, `beat` nem `supervisord` (ADR-015). Gatilhos para reavaliar a arquitetura de hospedagem: uso de memória próximo dos 512 MB, reinícios por falta de memória, ou respostas de voz lentas por disputa de CPU.

### Infrastructure Element 3 — Conectividade dos dispositivos (Wi-Fi)

Os dois ESPs se conectam a uma rede Wi-Fi com acesso à internet, configurada por BLE pelo app (ADR-029), podendo ser trocada sem regravar o firmware (casa e faculdade). Redes de faculdade podem bloquear portas de saída diferentes de 80/443; a porta 8883 deve ser testada na rede real; o hotspot do celular é a alternativa.

---

# 8. Cross-cutting Concepts

## 8.1 Contrato MQTT (Firmware WROOM ↔ Backend)

**Versão 1 do contrato**, em uso entre o firmware do WROOM e o backend.

- Tópico de leituras: `greensync/{deviceId}/sensores`
- Payload (JSON):
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

| Campo | Tipo | Obrigatório | Faixa aceita | Observação |
|---|---|---|---|---|
| `ph` | número | sim | 0 a 14 | |
| `umidade_solo` | número | sim | 0 a 100 | Em %. O firmware calibra o YL-69 (leitura bruta invertida) e envia já em porcentagem |
| `temperatura_ar` | número | sim | -40 a 80 | °C (faixa do DHT22) |
| `umidade_ar` | número | não | 0 a 100 | Em %, vinda do DHT22 |
| `bomba_ligada` | booleano | sim | — | Estado atual da bomba |
| `timestamp` | inteiro | não | — | Unix, em segundos. Se ausente, o backend usa a hora do servidor |

Regras: campos extras são ignorados; payload inválido é registrado em log e descartado, sem derrubar o backend; se a leitura do DHT22 falhar (`NaN`), o firmware **não publica** aquela leitura. Intervalo de publicação: 30 s, configurável no firmware (o DHT22 exige cerca de 2 s entre leituras).

- QoS: os comandos do backend saem em QoS 1 (entrega pelo menos uma vez). As leituras do firmware saem em QoS 0, limitação da biblioteca `PubSubClient`; como chegam a cada 30 s, perder uma leitura é aceitável.
- Tópico de status: `greensync/{deviceId}/status`, payload `{"status": "online", "fw": "2.1.0"}` ou `{"status": "offline"}` (`fw` é a versão do firmware instalada).
  - O firmware publica `online` ao conectar, com retain.
  - O `offline` é o **Last Will**, publicado pelo broker em desconexão inesperada.
- Tópico de comandos (backend → WROOM): `greensync/{deviceId}/comandos`. **Implementado no backend e no firmware do WROOM.**
  - QoS 1, **sem retain** (um comando guardado no broker seria entregue de novo a quem reconectasse depois, e a bomba ligaria sem ninguém pedir).
  - Payload: `{"acao": "regar", "duracao_s": 5, "id": "<idAgendamento>"}`.

| Campo | Tipo | Observação |
|---|---|---|
| `acao` | texto | Hoje só `"regar"` |
| `duracao_s` | inteiro | De 1 a 10 s por padrão (limite configurável no backend; a demonstração usa 15 s). O firmware deve ter o próprio limite de bomba ligada |
| `id` | texto | Id do agendamento no Firestore |

  - O firmware **deve ignorar um `id` repetido**: o QoS 1 pode entregar a mesma mensagem mais de uma vez.
  - O firmware **mantém o próprio tempo máximo de bomba ligada**, independente do `duracao_s` recebido.
  - Depois de regar, o firmware publica `bomba_ligada` no tópico de sensores, como sempre. No backend, `concluida` significa "comando publicado", não "a bomba girou".
  - Outros comandos neste tópico: `{"acao":"atualizar","alvo":"wroom","id":...,"versao":...,"url":...,"sha256":...}` e `{"acao":"reverter","alvo":"wroom","id":...,"versao":...}` (Seção 8.11).
- Tópico de progresso do OTA (WROOM → backend): `greensync/{deviceId}/ota`, payload `{"alvo":"wroom","id":...,"estado":"baixando|aplicando|ok|falhou|revertido","versao":...,"erro":...}`; `erro` é um código curto, só em `falhou` e `revertido`.

## 8.2 Esquema do Firestore (Backend ↔ App)

```
devices/{deviceId}                      (documento)
  status: "online" | "offline"
  last_seen: timestamp
  fw, fw_s3: versão do firmware instalada (do status MQTT)
  ota: estado da atualização em curso (tipo, alvo, id, estado, versão)
  leitura_atual: {                      (campo do tipo mapa, dentro do documento)
    ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, updated_at
  }
  historico/{autoId}                    (subcoleção)
    ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, timestamp
  agendamentos/{id}                     (subcoleção)
    quando: timestamp                   (hora marcada da rega)
    duracao_s: número
    status: "pendente" | "executando" | "concluida" | "cancelada" | "expirada" | "falhou"
    origem: "voz" | "texto"
    motivo: texto                       (só quando falha ou expira)
    criado_em, atualizado_em: timestamp

firmware/{alvo}                         (documento; alvo = wroom ou s3)
  versao, url, sha256, notas
  anterior: registro da versão anterior
  bloqueadas: versões retiradas
```

`updated_at` é carimbado pelo servidor a cada leitura gravada e é a base do frescor dos dados (Seção 8.7). `leitura_atual` é um campo do próprio documento (e não uma subcoleção): o app assina um único documento e recebe status e leitura juntos. A leitura atual e o registro de histórico são gravados no mesmo lote (ou ambos, ou nenhum). Campos ausentes na leitura (ex.: `umidade_ar`) ficam ausentes ou nulos.

## 8.3 Segurança

- Conexões MQTT sempre via TLS (porta 8883); o ESP precisa do certificado da CA do broker para validar a conexão.
- O endpoint de áudio exige `X-API-Key`, guardada em variável de ambiente, para ninguém consumir a cota do Gemini; o limite de perguntas por chave fica no Redis.
- Credenciais do broker, chave de serviço do Firebase, chave do Gemini e `X-API-Key` ficam **fora do controle de versão** (`.env` local; variáveis de ambiente no Render). O `.gitignore` cobre `.env` e arquivos de chave de serviço.
- Firestore em modo produção: o backend usa o Admin SDK (ignora as regras); as regras para o app serão definidas junto com a frente do aplicativo.
- Uma chave de serviço exposta deve ser revogada e substituída imediatamente.
- Atualização de firmware (ADR-030): download só por HTTPS de hosts permitidos (`OTA_HOSTS_PERMITIDOS`, padrão `github.com`), SHA-256 conferido durante a gravação, registro só com `X-Admin-Key`, atualização recusada com a bomba ligada e rollback automático.
- BLE (ADR-029): a senha do Wi-Fi trafega sem criptografia pelo canal BLE, de alcance curto e usado só durante a configuração; o pareamento com PIN é uma melhoria possível.
- No firmware, a validação do certificado do broker e do download do OTA está desativada na bancada (`TLS_INSEGURO` e `OTA_TLS_INSEGURO`) até a CA ser configurada.

## 8.4 Contrato HTTP do assistente (S3 ↔ Backend)

**Implementado e testado no backend. O cliente do S3 está em desenvolvimento.** Qualquer mudança aqui deve ser avisada às três frentes antes (SRS, 3.5.10).

### `POST /audio` — pergunta falada, resposta falada

**Requisição**

| Item | Valor |
|---|---|
| Cabeçalho `X-API-Key` | Chave da API (obrigatória; se `API_KEY` estiver vazia no servidor, a rota fica aberta, só para desenvolvimento) |
| Cabeçalho `X-Device-Id` | `deviceId` do vaso, ex.: `vaso-01` (letras, números, `-` e `_`, de 1 a 64 caracteres) |
| Cabeçalho `Content-Type` | `audio/wav` |
| Corpo | Os bytes do WAV: **16 kHz, 16 bits, mono**, até **15 s** e **1 MB** |
| Parâmetro `?debug=true` | Opcional, só para depuração (ver abaixo) |

Para testar com o celular, o backend também aceita mp3, m4a, aac, ogg e flac. O S3 deve mandar WAV.

**Resposta 200**

| Item | Valor |
|---|---|
| `Content-Type` | `audio/wav` (a voz da resposta, **24 kHz, 16 bits, mono** por padrão; a taxa é configurável no servidor) |
| `X-Tela` | `rosto` ou `dados`: o que o display deve mostrar durante a resposta (ADR-023). Voltar à carinha ao final da fala |
| `X-Dados` | JSON pequeno, só ASCII, para a tela de dados: `{"ph":6.4,"solo":20,"temp":24.1,"ar":58,"atuais":true}`. Campo ausente vem como `null`. `atuais` é `false` quando o vaso está offline ou a leitura é velha (o display deve avisar) |

**Erros**

| Código | Quando | Observação |
|---|---|---|
| 401 | `X-API-Key` ausente ou inválida | Não gasta o limite de perguntas |
| 413 | Corpo maior que o máximo | Conferido pelo `Content-Length` e também contando o que chega |
| 422 | `X-Device-Id` inválido, ou áudio vazio, ilegível, de formato não aceito ou mais longo que o máximo | Não gasta o limite |
| 429 | Limite de perguntas atingido | Traz `Retry-After` (segundos). O S3 deve esperar esse tempo |
| 502 | Gemini ou voz indisponíveis (inclusive depois do modelo reserva) | O S3 pode avisar "tente de novo" |

**Depuração (`?debug=true`):** a resposta passa a trazer `X-Ouviu` (o que o modelo entendeu), `X-Texto` (a frase falada) e `X-Modelo`, com %-encoding. Fica desligado por padrão porque cabeçalhos compridos estouram o buffer do cliente HTTP do ESP32 e a fala da pessoa é dado pessoal.

**Para o firmware do S3:**
- Use um **timeout de pelo menos 30 s** no cliente HTTP: o caso típico medido é de cerca de 9 s (3 s para entender e responder, 5 a 6 s para gerar a voz), e o pior caso (os dois modelos esgotando o prazo de áudio de 25 s, mais a voz) passa de 60 s, então o cliente do S3 deve esperar bastante antes de desistir.
- A resposta tem cerca de 350 a 380 KB para 8 s de fala. Confirmar a memória do S3 (PSRAM) ou tocar em streaming; se faltar memória, o servidor pode gerar a voz em 16 kHz.
- Pedidos de rega por voz não mudam nada para o S3: a frase de confirmação ou recusa já vem falada no WAV.

### `POST /perguntar` — pergunta em texto

Serve para testar o assistente sem hardware e para o app, se necessário. Cabeçalho `X-API-Key`; corpo JSON `{"device_id": "vaso-01", "pergunta": "..."}` (pergunta de 1 a 500 caracteres). Responde 200 com:

```json
{
  "texto": "...",
  "estado": {"estado": "atencao", "problemas": ["solo_seco"], "dados": "atuais", "idade_s": 3, "offline": false},
  "tela": "dados",
  "modelo": "gemini-3.5-flash-lite",
  "rega": null
}
```

`rega` é `null` se não houve pedido de rega; senão traz `{"resultado": "agendada" | "recusada" | "cancelada" | "nada_a_cancelar" | "falhou" | "erro" | "ignorada", "id": "..."}`. Os códigos de erro são os mesmos do `/audio` (401, 422, 429, 502).

## 8.5 Validação e limites de atuação

O backend valida todo pedido de rega antes de agendar. Os valores abaixo são configuráveis por variável de ambiente e **continuam a calibrar com testes reais**:

| Regra | Valor atual | Variável |
|---|---|---|
| Atraso máximo | 24 h | `REGA_ATRASO_MAX_S` |
| Duração máxima | 10 s no código (a demonstração usa 15 s, definida no `.env`) | `REGA_DURACAO_MAX_S` |
| Duração padrão (a pessoa não disse) | 5 s no código (a demonstração usa 15 s, definida no `.env`) | `REGA_DURACAO_PADRAO_S` |
| Intervalo mínimo entre regas | 10 min no código (30 s na demonstração, definido no `.env`); conta regas pendentes, executando e concluídas | `REGA_INTERVALO_MIN_S` |
| Tolerância de atraso (reinício do backend) | 5 min | `REGA_TOLERANCIA_S` |
| Vaso offline ou sem nenhuma leitura | Recusa | — |
| Solo acima de 80% de umidade | Recusa a rega de agora (e confere de novo na hora de regar) | `SOLO_ENCHARCADO_ACIMA` |
| Bomba já ligada | Recusa a rega de agora | — |

Outras garantias:

- **A fala da pessoa precisa conter uma palavra de rega** (regar, molhar, irrigar). Se o modelo propuser rega sem isso, o pedido é ignorado. Silêncio ou ruído (sem transcrição) nunca vira rega.
- **Horário do relógio:** "às 15h" usa o fuso do usuário (`FUSO_UTC_H`, Brasília = -3). Se o horário de hoje já passou, vale o de amanhã.
- **Nunca duplicar:** o status `executando` é gravado, em transação, antes de publicar o comando. Duas tentativas sobre a mesma rega (ex.: duas instâncias durante um deploy) nunca passam as duas. Dois pedidos ao mesmo tempo também não furam o intervalo mínimo (trava no backend).
- **Reconferência na hora:** no horário marcado, o backend confere de novo se o vaso está online e o solo não está encharcado; se não, marca `falhou` com o motivo e não publica nada.
- **Frases verdadeiras:** a confirmação e a recusa são escritas pelo backend, com o horário e a duração realmente agendados. Numa rega "de agora", o backend espera o resultado e, se falhar, a planta diz que não conseguiu.
- O firmware tem seu próprio tempo máximo de bomba ligada (15 s) e ignora `id` repetido (defesa em profundidade).

**Travas independentes do LLM (ADR-025):**
- Rega: a fala da pessoa precisa conter uma forma de pedido (rega, regar, regue, molhar, irrigar...). "Regular", "regulamento" e "regada" não valem.
- Cancelamento: a fala precisa conter uma palavra de cancelamento (cancelar, desmarcar, desfazer, esquecer, "não precisa", "deixa pra lá"...). Sem ela, o modelo não desfaz nenhuma rega e a planta pede para repetir.
- No áudio, sem transcrição não há pedido.

**Publicação incerta:** se o comando é publicado mas o prazo de 5 s estoura, a rega fica `falhou` com o motivo "não tenho certeza se o comando chegou ao vaso", e esse caso **conta no intervalo mínimo**, para um novo pedido não regar em dobro. Falha com certeza de nada ter sido enviado (sem conexão com o broker) não conta. Se o comando saiu e só a gravação final falha, a rega nunca vira `falhou` (fica `executando`, que também conta no intervalo).

## 8.6 Assistente com personalidade

O prompt do sistema faz a planta falar em primeira pessoa, de forma curta, só sobre a planta, usando apenas os números recebidos. Se um dado faltar, ela diz que não sabe. O "estado" da planta (ex.: com sede, ok) é calculado pelo backend a partir de limiares configuráveis, e o Gemini apenas dá a voz. O tom (mais informativo ou mais "planta") é configurável. Essa mesma personalidade também aparece visualmente na carinha do display do S3, que dá lugar aos dados dos sensores enquanto a resposta é dada (ADR-021, ADR-023).

**Como os números são falados (ADR-027):** a temperatura e as umidades são arredondadas ao inteiro mais próximo ("uns 24 graus"), porque a resposta é ouvida. O **pH nunca é arredondado**: a planta diz o valor exatamente como está nos dados, com a casa decimal e sem "uns", "perto de" ou "cerca de" (6,5 é "seis vírgula cinco"). Se o pH estiver indisponível, ela diz que não sabe. A regra está no prompt (`ai/prompt.py`) e é coberta por testes do texto do prompt; o que o Gemini de fato fala só se confirma em teste real (teste manual com o Gemini real).

## 8.7 Frescor dos dados (vaso offline ou leitura velha)

O assistente não pode falar como se o último valor ainda fosse o de agora (REQ-FUNC-007).

- A cada leitura gravada, o backend carimba `leitura_atual.updated_at` com a hora do servidor e marca o `status` como `online`. O Last Will do broker marca `offline`.
- O backend classifica os dados como `atuais`, `desatualizados` (sem leitura nova há mais de `LEITURA_VELHA_APOS_S`, 120 s por padrão, ou vaso offline) ou `sem_dados`, e calcula a idade da leitura.
- Com dado velho ou vaso offline, a planta avisa em poucas palavras que são os últimos dados que recebeu e há quanto tempo, e não diz que está bem agora. Ela **não inventa a causa** (conexão, energia...) a menos que o vaso esteja marcado como desconectado.
- Se `updated_at` faltar, a idade é desconhecida e o dado não é marcado como velho (a menos que o vaso esteja offline).
- `X-Dados.atuais` leva essa informação ao display do S3 (Seção 8.4).

## 8.8 Resiliência do assistente (Gemini e voz)

- Há um modelo principal e um reserva (`GEMINI_MODEL` e `GEMINI_MODEL_FALLBACK`; na voz, `TTS_MODEL` e `TTS_MODEL_FALLBACK`).
- Erro 5xx: tenta de novo uma vez no mesmo modelo. Timeout: vai direto ao reserva. Erro 4xx ou resposta vazia: vai ao reserva. Se todos falham, a rota responde 502.
- Prazos por chamada: 8 s para texto, 25 s para entender o áudio, 15 s para a voz.
- Modelo principal padrão `gemini-3.5-flash-lite` e reserva `gemini-3.1-flash-lite`; o 3.1 como principal estourava o prazo com frequência.
- **Firestore lento ou fora do ar** (prazo de 5 s, `FIRESTORE_TIMEOUT_S`): as rotas seguem como "sem dados" (a planta diz que não sabe como está e a rega é recusada), em vez de responder erro 500. O S3 ainda recebe uma resposta falada, e o erro fica no log. Há testes das duas rotas com falha real (erro e lentidão da leitura do Firestore), confirmando 200 e "sem dados".
- Em testes reais, o modelo principal estourou o prazo ou deu 503 com frequência e o reserva respondeu; trocar a ordem no `.env` é a mitigação imediata.
- A integração fica atrás de `responder` e `responder_audio` (ADR-018): trocar de provedor mexe só no interior dessas funções.

## 8.9 Limite de perguntas e proteção dos endpoints

- **Limite (REQ-FUNC-015):** janela fixa no Redis, 10 perguntas por 60 s por chave de API (`LIMITE_PERGUNTAS`, `JANELA_LIMITE_S`). Só o hash da chave vai para o Redis. `/perguntar` e `/audio` compartilham o mesmo limite.
- **Se o Redis não estiver configurado ou cair, a pergunta passa** (e o erro é logado): preferimos o assistente no ar a derrubá-lo por causa do contador.
- **Ordem das checagens:** chave (401), `device_id` (422), áudio (413/422) e só então o limite (429). Assim, requisições inválidas não gastam o limite nem o Gemini.
- A chave é comparada em tempo constante. O `device_id` só aceita `^[A-Za-z0-9_-]{1,64}$`, porque vira nome de documento no Firestore.
- O que a pessoa falou ou escreveu **não vai para o log**; só tamanhos, tempos, a tela escolhida e o resultado da rega.
- **Contexto da conversa (REQ-FUNC-008, ADR-015):** lista `ctx:{deviceId}` no Redis com as últimas 3 trocas (`CONTEXTO_TURNOS`), cada pergunta e resposta cortada em 300 caracteres (`CONTEXTO_MAX_CHARS`) e prazo de 5 min renovado a cada troca (`CONTEXTO_TTL_S`). Só texto, nunca áudio. Entra no prompt só para entender referências ("e a umidade?"): os números vêm sempre dos dados atuais, e o prompt manda ignorar instruções vindas da conversa. Guarda-se a frase que foi **falada** (na rega, a confirmação do backend), não a proposta do modelo. Sem Redis ou com Redis fora do ar, segue sem contexto. `CONTEXTO_TURNOS=0` desliga.
- Um pedido de rega que dependa só do contexto ("e daqui a 1 hora?") não vale: a trava da rega exige uma palavra de rega na frase atual (ADR-025), e a planta pede para a pessoa repetir.

## 8.10 Estratégia de testes

- **Automatizados (pytest, 973 execuções):** rodam sem Gemini, Firestore, Redis ou MQTT reais, com fakes; cada teste usa os padrões de `config.py`, independentes do `.env`. Rodam só dentro do Docker: `docker compose run --rm --no-deps backend python -m pytest tests/ -q`.
- **Prova por reversão:** ao corrigir uma trava de segurança, a mudança é desfeita temporariamente para confirmar que algum teste falha, e só depois restaurada. Assim o teste prova a trava, e não apenas passa.
- **Manuais (roteiro interno do grupo):** cobrem o que os fakes não provam: Gemini real e voz, Firestore e Redis reais, Mosquitto, e depois o firmware real. Os scripts `tests/manual_*.py` gastam cota do Gemini e ficam fora do pytest.
- **Plano formal:** o documento `IEEE829_GreenSync_Plano_de_Testes.md` organiza níveis, critérios de aprovação, suspensão, ambiente e responsabilidades, apontando para os requisitos do SRS em vez de repeti-los.
- **Limite conhecido:** os testes automatizados garantem o texto do prompt e as travas do backend, não a fala do modelo; a integração com o vaso real, o TLS na rede da faculdade e o app só se provam em teste conjunto.

## 8.11 Atualização de firmware (OTA)

- **Registro:** cada versão é publicada como *release* no GitHub (tag `firmware-{alvo}-vX.Y.Z`); uma GitHub Action chama `PUT /firmware/{alvo}` (`X-Admin-Key`) e o backend guarda versão, URL, SHA-256 e a versão anterior em `firmware/{alvo}`. Só aceita `https` e hosts de `OTA_HOSTS_PERMITIDOS`; versão igual à atual dá 409; versão retirada fica em `bloqueadas`.
- **Disparo:** `POST /dispositivos/{id}/atualizar` (app) publica o comando com versão, URL e hash lidos do registro, nunca do pedido. Recusas: `sem_firmware`, `firmware_invalido`, `sem_dados`, `offline`, `bomba_ligada`, `versao_igual`, `ota_em_curso`. Com `OTA_AUTO=true`, o backend dispara sozinho quando o registro recebe uma versão maior ou quando o vaso conecta com versão menor (semver, no máximo `OTA_AUTO_TENTATIVAS` por versão).
- **No vaso:** baixa por HTTPS, calcula o SHA-256 enquanto grava na partição inativa (tabela com dois slots), recusa a atualização com a bomba ligada e publica o progresso em `greensync/{deviceId}/ota`.
- **Confirmação e rollback:** o firmware novo se confirma ao conectar ao MQTT. Sem confirmação em 5 minutos, ou depois de mais de 3 reinícios sem se confirmar, o vaso volta à partição anterior.
- **Reversão manual:** `POST /dispositivos/{id}/reverter` (`X-Admin-Key`) manda o vaso à versão do registro e bloqueia a revertida; `POST /firmware/{alvo}/retirar` retira a versão atual e restaura a anterior.
- **Regra de publicação:** a versão do registro precisa ser igual à `FW_VERSION` compilada no mesmo binário.

## 8.12 Configuração de Wi-Fi por BLE

- **Serviço:** nome `GreenSync_BLE`, serviço `4fafc201-1fb5-459e-8fcc-c5c9c331914b`, característica `beb5483e-36e1-4688-b7f5-ea07361b26a8` (escrita e notificação).
- **Escrita:** `ssid,senha`. **Notificações:** `conectando`, `ok`, `erro:senha`, `erro:rede`, `erro:timeout`.
- **Quando abre:** sem rede salva ou depois de 4 falhas seguidas de conexão. Não há botão físico.
- **Persistência:** as credenciais vão para a NVS só depois de uma conexão bem-sucedida.

---

# 9. Architecture Decisions

Ver documento separado **ADR — Decisões — GreenSync**, que registra as decisões arquiteturais (ADR-001 a ADR-033). Decisões recentes, desta versão do documento:

| ADR | Tema |
|---|---|
| ADR-014 | Broker EMQX Cloud (substitui a ADR-002) |
| ADR-015 | Redis sem Celery (revisa a ADR-013) |
| ADR-016 | Dois microcontroladores: WROOM (sensores) e S3 (voz) (revisa a ADR-001) |
| ADR-017 | Áudio do S3 por HTTP com `X-API-Key` |
| ADR-018 | Gemini com Groq de reserva |
| ADR-033 | Fases: V1 é o vaso do WROOM, V2 é a voz do S3; sem GPRS (revisa as ADR-011 e ADR-018) |
| ADR-019 | Hospedagem paga no Render, instância única (revisa a ADR-003) |
| ADR-020 | Sensores DHT22 e YL-69 (substitui a ADR-008) |
| ADR-021 | Assistente com personalidade e rega por voz, agenda no Firestore |
| ADR-022 | Provisionamento de Wi-Fi por portal (substituída pela ADR-029) |
| ADR-023 | Display no ESP32-S3, alternando entre rosto e dados dos sensores (resolve a pendência da ADR-016) |
| ADR-024 | pH simulado na demonstração |
| ADR-025 | Pedido de rega como saída estruturada, validado e confirmado pelo backend (ajusta o item 2 da ADR-021) |
| ADR-026 | Dados desatualizados e tolerância a falhas do assistente |
| ADR-027 | pH sempre falado com o valor exato |
| ADR-028 | Estratégia de testes: fakes, prova por reversão e testes manuais |
| ADR-029 | Configuração de Wi-Fi por BLE, sem botão físico (substitui a ADR-022) |
| ADR-030 | Atualização de firmware pela rede (OTA) com GitHub Releases e rollback |
| ADR-031 | Rega somente por comando; sem irrigação automática no firmware |
| ADR-032 | Palavra de ativação "Hi ESP" detectada no próprio S3 |

---

# 10. Quality Requirements

## 10.1 Quality Requirements Overview

Ver Seção 3.3 do documento SRS — Requisitos para os requisitos de qualidade de serviço detalhados (performance, segurança, confiabilidade, disponibilidade, observabilidade).

## 10.2 Quality Scenarios

| Cenário | Estímulo | Resposta esperada |
|---|---|---|
| Perda momentânea de Wi-Fi | Rede cai por alguns segundos | Firmware reconecta e retoma publicação MQTT automaticamente |
| Troca de rede (casa ↔ faculdade) | O vaso é levado para outra rede Wi-Fi | O vaso abre o BLE e o app envia a nova rede, sem regravar o firmware |
| Backend reinicia com rega agendada | Render reinicia o serviço antes da hora da rega | No startup, o backend recarrega os agendamentos `pendente` do Firestore; os vencidos além da tolerância viram `expirada` |
| Pedido de rega excessivo | Usuário pede rega repetida ou muito longa | O backend recusa pelas regras de limite, e o firmware ainda aplica o tempo máximo de bomba |
| Excesso de perguntas | Chave de API usada além do limite | O backend recusa novas perguntas até o limite liberar |
| Comando de rega repetido | O QoS 1 entrega o mesmo comando duas vezes | O firmware ignora o `id` repetido e a bomba liga uma vez |
| Leitura inválida do DHT22 | O sensor falha e devolve `NaN` | O firmware não publica; se algo inválido chegar, o backend descarta |
| Instância duplicada do backend | Duas instâncias assinam o mesmo tópico | Evitado por configuração: instância única, sem autoscaling |
| Pergunta por voz feita ao assistente | Usuário pergunta "como ela tá?" | O display do S3 troca da carinha para os dados dos sensores relevantes, e volta à carinha ao final da resposta |
| Vaso para de enviar dados | Sem leitura nova há mais de 120 s, ou Last Will recebido | O assistente avisa que são os últimos dados e há quanto tempo, sem dizer que está bem agora; `X-Dados.atuais` vem `false` |
| Pedido de rega com o vaso offline | Usuário pede "rega agora" e o vaso está offline | O backend recusa e a planta diz que não consegue regar porque o vaso está desconectado; nada é publicado |
| Modelo principal do Gemini lento ou fora do ar | Timeout ou 503 | O backend tenta o modelo reserva; só se todos falharem a rota responde 502 |
| Atualização de firmware com binário ruim | Hash errado, ou firmware novo que não conecta | O vaso recusa o binário com hash errado; se o novo não se confirmar, volta sozinho à versão anterior |
| Rede Wi-Fi com senha errada | Usuário digita a senha errada no app | O vaso notifica `erro:senha` e mantém a rede salva anterior |

---

# 11. Risks and Technical Debts

| Risco/Débito | Descrição | Mitigação |
|---|---|---|
| Confiabilidade da sonda de pH | Sondas baratas de hobby têm calibração inconsistente e degradam com o tempo | Testar o componente isoladamente antes da integração; usar soluções tampão de calibração |
| Sensor de solo resistivo (YL-69) | Corrói com o tempo e exige calibração; a leitura bruta é invertida | Calibração seco/molhado no firmware; alimentar o sensor só durante a leitura; avaliar sensor capacitivo |
| Vedação física do vaso | Separação entre câmara eletrônica seca e substrato úmido é um desafio real de fabricação | Prototipar e testar a vedação antes da montagem final |
| Bomba e alimentação | Bomba e dois ESPs na mesma fonte de 5V; sem diodo de roda-livre e capacitor de desacoplamento, a bomba pode reiniciar o ESP ou queimar o transistor | Diodo de roda-livre, capacitor de desacoplamento e fonte com folga (ex.: 5V/3A) |
| Escopo da V2 maior | Dois firmwares, áudio e cadeia de IA | Construir em camadas; validar o assistente em texto antes do hardware; a voz é uma camada sobre a V1, que funciona sozinha |
| Latência da voz | Chamadas ao Gemini e ao TTS somadas podem passar de alguns segundos | Medir cedo; respostas curtas; reduzir chamadas (áudio direto no Gemini) |
| Memória do Render (512 MB) | API, assinante MQTT, IA e Redis local disputam memória | Um processo só; monitorar; gatilhos de migração na Seção 7.2 |
| Plano do EMQX Cloud | Limites de conexões e mensagens do plano serverless | Acompanhar o uso; Mosquitto local para desenvolvimento |
| Firewall da faculdade | Redes de faculdade podem bloquear a porta 8883 | Testar na rede real; alternativa de MQTT sobre WebSocket seguro na 443 |
| Cotas do Gemini | Limites do plano gratuito (incluindo áudio) | Acompanhar o uso; isolar a chamada em `responder(audio, leitura)` para trocar de provedor |
| Contrato de áudio ainda não validado com o S3 | O contrato MQTT está validado com o WROOM; o cliente HTTP de áudio do S3 está em desenvolvimento (Seção 8.4) | Testar o S3 com o backend; qualquer mudança de contrato é avisada antes |
| Hardware do S3 | Montagem instável (fios soltos, mau contato no microfone) em protoboard | Soldar as ligações, usar fios curtos e testar cada módulo isoladamente |
| TLS sem validação no firmware | Na bancada, o certificado do broker e o do download do OTA não são validados | Configurar a CA no firmware e desligar `TLS_INSEGURO` e `OTA_TLS_INSEGURO` antes da entrega final |
| Senha do Wi-Fi sem criptografia no BLE | A credencial trafega em claro durante a configuração | Alcance curto e janela curta; pareamento com PIN como melhoria |
| Alto-falante de 1 W | Tom contínuo em volume alto pode queimar a bobina | Limitar o volume do firmware; a voz tem picos curtos |
| Tamanho da resposta de áudio no S3 | A voz chega em WAV de 24 kHz, cerca de 350 a 380 KB para 8 s | O S3 tem 8 MB de PSRAM, suficientes para guardar a resposta; se faltar memória, tocar em streaming ou gerar a voz em 16 kHz |
| Modelo principal do Gemini instável | Em testes, estourou o prazo ou deu 503 com frequência | Modelo reserva automático (Seção 8.8); trocar a ordem dos modelos no `.env` |
| pH simulado | O pH da demonstração não é medido (ADR-024) | Dizer isso na apresentação; trocar pela sonda real mexe só no firmware |
| Rega depende do backend | Sem irrigação automática no firmware (ADR-031), a planta só é regada se backend, broker e rede estiverem no ar | Agendar regas com folga e manter o backend sempre ativo (ADR-019); uma regra local com histerese é uma evolução possível |
| Chave de API única | Quem tem a chave consulta e rega qualquer `deviceId`; a chave fica embutida no firmware do S3 | Aceito para o projeto; uma chave por vaso mudaria o contrato. Trocar a chave se vazar |
| Recarga das regas na subida sem nova tentativa | Se o Firestore estiver fora quando o backend sobe, as regas pendentes só voltam no próximo reinício e podem expirar (tolerância de 5 min) | Raro; repetir a recarga em segundo plano é melhoria futura |
| Regas com gravação incerta | Se o Firestore cair logo depois de o comando sair, a rega pode ficar `executando` até o próximo reinício | Continua contando no intervalo mínimo; no reinício vira `falhou` e nunca repete |
| Testes com fakes não provam o mundo real | A suíte (973 execuções) usa fakes; o Gemini, o Firestore, a bomba e a rede da faculdade só se provam em teste real | Testes manuais do grupo e Plano de Testes; testar com o firmware em grupo antes da demonstração |

---

# 12. Glossary

| Term | Definition |
|---|---|
| Broker MQTT | Serviço intermediário que recebe mensagens publicadas e as distribui aos assinantes de um tópico |
| EMQX Cloud | Broker MQTT gerenciado na nuvem, usado no projeto (ADR-014) |
| Firestore | Banco de dados de documentos do Firebase usado para sincronização em tempo real |
| Last Will (MQTT) | Mensagem publicada automaticamente pelo broker quando um cliente se desconecta inesperadamente |
| QoS (MQTT) | Nível de garantia de entrega de uma mensagem (0, 1 ou 2) |
| Retain (MQTT) | Marca que faz o broker guardar a última mensagem de um tópico e entregá-la a novos assinantes |
| Redis | Banco de dados em memória; no projeto guarda contexto de conversa e limites de uso |
| Function calling | Recurso em que o LLM devolve um pedido de ação estruturado (ex.: agendar rega) em vez de texto livre; quem executa a ação é o backend |
| DHT22 | Sensor digital de temperatura e umidade do ar |
| YL-69 | Sensor resistivo de umidade do solo, de duas hastes; exige calibração |
| Provisionamento de Wi-Fi | Configuração da rede do ESP sem regravar o firmware (por BLE) |
| BLE | Bluetooth Low Energy; o app o usa para enviar a rede Wi-Fi ao vaso |
| OTA | Atualização de firmware pela rede (Seção 8.11) |
| Rollback | Volta automática do vaso à versão anterior do firmware quando a nova não se confirma |
| Display OLED (SSD1306) | Tela do ESP32-S3 que mostra, por padrão, a carinha da planta e troca para os dados dos sensores durante uma resposta de voz (ADR-023) |
| Frescor (dos dados) | Se a leitura é recente o bastante para ser tratada como "agora" (Seção 8.7) |
| V1 | Primeira fase de entrega: vaso do ESP32-WROOM (sensores, bomba, sincronização de dados, app, BLE e OTA) |
| V2 | Segunda fase de entrega: voz e display no ESP32-S3 |