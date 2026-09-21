# Arc42 — Documento de Arquitetura de Software (SDD) — GreenSync

> **Versão 0.3 — 21/09/2026.** Atualizado com as decisões registradas nas ADR-014 a ADR-022. Itens marcados **[A DEFINIR]** dependem de confirmação do grupo, do professor ou de teste prático. Itens marcados **(proposta)** foram sugeridos, mas ainda não validados com a frente responsável.

---

# 1. Introduction and Goals

## 1.1 Requirements Overview

O GreenSync é um vaso inteligente que monitora pH do solo, umidade do solo, temperatura e umidade do ar, controla irrigação automática, sincroniza dados em tempo real com um aplicativo mobile e responde perguntas faladas sobre a planta. O assistente "fala como a planta" (primeira pessoa, com base nos dados reais dos sensores) e também pode agendar regas por comando de voz, sempre com validação no backend e limites no firmware.

O sistema usa **dois microcontroladores**: um ESP32-WROOM (sensores e bomba, comunicação via MQTT) e um ESP32-S3 (voz, comunicação via HTTP com o backend). Ver o documento SRS — Requisitos para a especificação completa e verificável.

## 1.2 Quality Goals

| Prioridade | Meta de qualidade | Motivação |
|---|---|---|
| 1 | Confiabilidade dos dados de sensor | pH e umidade alimentam a irrigação automática — dado ruim gera decisão errada (rega demais/de menos) |
| 2 | Segurança da atuação | Rega por voz ou agenda não pode alagar o vaso nem queimar a bomba: limites no backend **e** no firmware |
| 3 | Simplicidade de integração entre as três frentes | Grupo pequeno (3 pessoas), trabalho paralelo depende de contratos de interface bem definidos (MQTT/JSON, Firestore, HTTP de áudio) |
| 4 | Baixo custo operacional | Projeto acadêmico — camadas gratuitas onde possível; o único custo recorrente previsto é o serviço pago do Render (valor a confirmar, ver ADR-019) |
| 5 | Independência de rede local (V2) | Objetivo explícito de funcionar via GPRS, sem depender de Wi-Fi doméstico |

## 1.3 Stakeholders

| Role/Name | Contact | Expectations |
|---|---|---|
| Frente — Hardware/Firmware | Equipe GreenSync | Contratos MQTT (WROOM) e HTTP de áudio (S3) estáveis e definidos cedo, para trabalhar em paralelo |
| Frente — App/Design | Equipe GreenSync | Esquema do Firestore estável, para consumir dados corretamente no app |
| Frente — Backend | Equipe GreenSync | Visão completa da integração entre hardware, nuvem, IA e app |
| Professor orientador | — | Uso de MQTT e Redis (conteúdo da disciplina), projeto funcional de ponta a ponta na demonstração |

---

# 2. Architecture Constraints

- Protocolo de comunicação entre o dispositivo de sensores e a nuvem deve ser MQTT (exigência da disciplina); broker **EMQX Cloud** (ADR-014).
- Dois microcontroladores: **ESP32-WROOM** (sensores, bomba) e **ESP32-S3** (voz) (ADR-016).
- Backend em Python + FastAPI, em **processo único** com `async`/`await`, **sem Celery** (ADR-013, ADR-015).
- **Redis** presente na arquitetura, por exigência do professor; usos definidos na ADR-015.
- Aplicativo em Flutter.
- Banco de dados em nuvem: Firebase (Firestore).
- LLM: Google Gemini (ADR-004, ADR-018).
- Sem armazenamento local/offline (ver ADR-010).
- Orçamento operacional: camadas gratuitas onde possível, mais um serviço pago no Render (ADR-019).
- Alimentação elétrica única em 5V, sem bateria.

---

# 3. Context and Scope

## 3.1 Business Context

O usuário final interage com o aplicativo mobile, com o "rosto" exibido no display do vaso e, por voz, com o assistente ("planta que fala"). Não há interação direta do usuário com o backend, o broker MQTT, o Redis ou o Firebase — esses são componentes internos, invisíveis ao usuário final.

```
Usuário ──(usa)──> App (Flutter)
Usuário ──(observa)──> Vaso GreenSync (display OLED)
Usuário ──(fala com)──> Vaso GreenSync (ESP32-S3: microfone e alto-falante)
```

## 3.2 Technical Context

```
ESP32-WROOM ──MQTT/TLS──> EMQX Cloud ──MQTT/TLS──> Backend (FastAPI, Render) ──> Firebase (Firestore) ──> App (Flutter)
 (sensores,      ▲                                    │   │
  bomba)         └──── comandos de rega (MQTT) ───────┘   └──> Redis (contexto, limite de perguntas)
                                                       │
ESP32-S3 ──HTTPS + X-API-Key──> Backend ──────────────┴──> Google Gemini (LLM / áudio de entrada)
 (voz)   <────── áudio da resposta ─────┘                   TTS (provedor a definir)
```

Os dois ESPs pertencem ao mesmo vaso lógico (`deviceId`, ex.: `vaso-01`), e o backend é o único ponto que os conecta. Na V2, o WROOM pode usar um módulo GPRS em vez de Wi-Fi como camada de rede subjacente ao MQTT; o S3 permanece em Wi-Fi (o áudio é pesado para dados móveis).

---

# 4. Solution Strategy

A estratégia central é manter os firmwares simples e concentrar a lógica no backend. O **WROOM** só lê sensores, controla a bomba e fala MQTT; o **S3** só captura e reproduz áudio e fala HTTP. Validação, persistência, orquestração de IA, agendamento e decisão de atuação ficam no backend, o que desacopla as frentes de hardware das mudanças na nuvem.

Decisões que sustentam essa estratégia:

- **MQTT para sensores** (em vez de o ESP escrever direto no Firebase): atende ao requisito da disciplina e tolera melhor conexões intermitentes.
- **HTTP para áudio**: áudio é grande demais para o MQTT, que é feito para mensagens pequenas (ADR-017).
- **A irrigação por umidade continua no firmware**, com histerese, como regra base. Voz e agenda são camadas por cima — a planta não depende da nuvem para sobreviver.
- **Processo único** (uvicorn) com `async`/`await`, sem workers: a chamada ao LLM roda dentro da requisição e as regas agendadas viram tarefas `asyncio` persistidas no Firestore (ADR-015, ADR-021).
- **Construção em camadas**: cada peça é validada isoladamente (Docker → MQTT → validação → Firestore → Redis → IA em texto → áudio) antes de a próxima ser adicionada.

---

# 5. Building Block View

## 5.1 Whitebox Overall System

**Motivation**

O sistema é dividido em blocos alinhados às responsabilidades das três frentes: firmware (dois dispositivos), backend e app. Broker MQTT, Redis, Firebase e Gemini são serviços de terceiros configurados pelo grupo, não código próprio.

**Contained Building Blocks**

### Firmware WROOM (ESP32-WROOM)

- Purpose/Responsibility: ler sensores (pH, umidade do solo, temperatura e umidade do ar), controlar a bomba d'água, publicar leituras e status via MQTT, assinar o tópico de comandos de rega, aplicar limite de tempo máximo de bomba ligada, e permitir configurar o Wi-Fi sem regravar (portal de configuração, ADR-022). O display OLED com o "rosto" também está previsto no firmware; **[A DEFINIR]** em qual dos dois ESPs.
- Interface(s): MQTT sobre TLS (publisher e assinante).
- Fulfilled Requirements: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-007 (lado do dispositivo), REQ-FUNC-010 (V2), REQ-FUNC-011 (execução), REQ-FUNC-013.
- Open Issues/Problems/Risks: confiabilidade da sonda de pH e desgaste do sensor de solo resistivo (Seção 11); lógica não bloqueante para conviver com a conexão MQTT persistente.

### Firmware S3 (ESP32-S3)

- Purpose/Responsibility: capturar o áudio da pergunta (microfone INMP441), enviá-lo ao backend por HTTP, reproduzir o áudio da resposta no alto-falante, e oferecer mute físico do microfone. Também precisa do provisionamento de Wi-Fi.
- Interface(s): HTTPS para o backend, com `X-API-Key` (Seção 8.4).
- Fulfilled Requirements: REQ-FUNC-008, REQ-FUNC-009, REQ-FUNC-013, REQ-FUNC-014 (lado do cliente).
- Open Issues/Problems/Risks: qualidade do áudio (I2S), formato do áudio enviado e forma de acionamento (botão "falar" ou wake-word) **[A DEFINIR]**.

### Broker MQTT (EMQX Cloud)

- Purpose/Responsibility: receber mensagens publicadas pelo WROOM e redistribuí-las ao backend assinante; entregar comandos do backend ao WROOM; publicar a mensagem de "last will" em caso de desconexão inesperada.
- Interface(s): MQTT sobre TLS (porta 8883). Alternativa contra firewall (MQTT sobre WebSocket seguro na 443) **[A DEFINIR]**.
- Fulfilled Requirements: REQ-FUNC-003, REQ-FUNC-007, REQ-FUNC-011.
- Open Issues/Problems/Risks: limites do plano gratuito/serverless do EMQX Cloud **[A DEFINIR]** (ver Seção 11).

### Backend (Python + FastAPI, Render)

- Purpose/Responsibility: assinar os tópicos MQTT, validar e gravar dados no Firestore; expor os endpoints de IA (`/perguntar` em texto, `/audio`); orquestrar Gemini e TTS; validar e agendar regas; publicar comandos MQTT.
- Interface(s): cliente MQTT (assinante e publisher); SDK Admin do Firebase; API do Google Gemini; TTS **[A DEFINIR]**; Redis; HTTP (FastAPI) para o S3 e, se necessário, para o app.
- Fulfilled Requirements: REQ-FUNC-004, REQ-FUNC-007, REQ-FUNC-008, REQ-FUNC-011, REQ-FUNC-012, REQ-FUNC-014, REQ-FUNC-015.
- Open Issues/Problems/Risks: memória do plano Starter (512 MB) com API, assinante MQTT e IA no mesmo processo; instância única obrigatória (Seção 7).

### Redis

- Purpose/Responsibility: contexto curto da conversa por dispositivo (com expiração) e limite de perguntas por chave de API. Uso como cache da última leitura é opcional.
- Interface(s): protocolo Redis, acessado só pelo backend, via `REDIS_URL`.
- Fulfilled Requirements: REQ-FUNC-015 (e apoio ao REQ-FUNC-008).
- Open Issues/Problems/Risks: no plano gratuito do Render, o Key Value (se disponível) é só em memória e perde dados ao reiniciar — aceito, pois o conteúdo é descartável. Expectativa exata do professor sobre o uso do Redis **[A DEFINIR]**.

### Firebase (Firestore)

- Purpose/Responsibility: armazenar a leitura atual, o histórico e os agendamentos de cada dispositivo; sincronizar em tempo real com o app.
- Interface(s): SDK Admin (backend, escrita); FlutterFire (app, leitura em tempo real).
- Fulfilled Requirements: REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-012.

### App (Flutter)

- Purpose/Responsibility: exibir dados em tempo real, histórico, estado da planta e status online/offline; único meio de acompanhamento visual do usuário (sem dashboard web).
- Interface(s): FlutterFire (Firestore).
- Fulfilled Requirements: REQ-FUNC-005, REQ-FUNC-006, REQ-FUNC-007 (exibição).

### Name interface 1 — Tópicos MQTT (WROOM ↔ Broker ↔ Backend)

Contrato de tópicos e payload JSON entre firmware e backend. Ver Seção 8.1.

### Name interface 2 — Esquema do Firestore (Backend ↔ App)

Estrutura de coleções e documentos que o backend escreve e o app lê. Ver Seção 8.2.

### Name interface 3 — API HTTP de áudio (S3 ↔ Backend)

Contrato de endpoint, cabeçalhos e formato de áudio entre o S3 e o backend. Ver Seção 8.4.

## 5.2 Level 2

### White Box: Firmware WROOM

Módulos internos: leitura de sensores (com calibração do sensor de solo e descarte de leituras inválidas do DHT22), controle de irrigação (histerese e tempo máximo de bomba), cliente MQTT (publicação, Last Will, assinatura de comandos), provisionamento de Wi-Fi.

### White Box: Firmware S3

Módulos internos: captura de áudio (I2S), botão de falar e mute, cliente HTTP, reprodução de áudio (I2S), provisionamento de Wi-Fi.

### White Box: Backend

| Módulo | Responsabilidade | Estado |
|---|---|---|
| `config.py` | Variáveis de ambiente (pydantic-settings) | Implementado |
| `models.py` | Validação dos payloads MQTT (`SensorReading`, `DeviceStatus`) | Implementado |
| `mqtt_client.py` | Assinante MQTT assíncrono, reconexão, roteamento e descarte de payload inválido | Implementado |
| `firebase_client.py` | Gravação da leitura atual + histórico e do status, em lote (batch) | Implementado |
| `main.py` | FastAPI, `lifespan` (inicia Firebase e o assinante MQTT) | Implementado |
| Redis (cliente) | Contexto de conversa e limite por chave | Planejado |
| `ai/` | `responder(audio, leitura)`, prompt da planta, cálculo do estado, ferramentas (function calling) | Planejado |
| Rotas HTTP | `POST /perguntar` (texto) e `POST /audio`, com `X-API-Key` | Planejado |
| Agendamentos | Validação, tarefas `asyncio`, persistência no Firestore, publicação do comando MQTT | Planejado |

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

## 6.2 Runtime Scenario 2 — Irrigação automática (regra base, no firmware)

1. O firmware detecta, na leitura periódica, que a umidade do solo está abaixo do limiar configurado.
2. O firmware aciona a bomba d'água.
3. O firmware publica o novo estado (`bomba_ligada: true`) junto com a leitura de sensores.
4. Quando a umidade volta ao patamar adequado (considerando a histerese), o firmware desliga a bomba e publica o novo estado.
5. Independentemente de qualquer comando, o firmware limita o tempo máximo de bomba ligada.

Este cenário não depende da nuvem: funciona mesmo com backend, broker ou Gemini fora do ar.

## 6.3 Runtime Scenario 3 — Pergunta ao assistente de voz (V1)

1. O usuário aciona o microfone do S3 (botão "falar" — **[A DEFINIR]**, wake-word é alternativa) e faz a pergunta.
2. O S3 envia o áudio ao backend por `POST /audio`, com `X-API-Key` e o `deviceId`.
3. O backend valida a chave e verifica o limite de perguntas no Redis.
4. O backend lê a leitura atual do Firestore, calcula o estado da planta (ex.: "com sede") a partir dos limiares configurados e monta o prompt com a personalidade da planta.
5. O backend envia o áudio e o contexto ao Gemini. A entrada de áudio direta no Gemini (sem STT separado) é uma **proposta** a validar; se não servir, entra um STT separado (ADR-018).
6. O texto da resposta vai ao TTS, que gera o áudio.
7. O backend devolve o áudio ao S3 na mesma requisição HTTP (**proposta**, **[A DEFINIR]**), que o reproduz.

## 6.4 Runtime Scenario 4 — Rega agendada por voz ("regar daqui 1 minuto")

1. O usuário pede a rega por voz (mesmo fluxo do cenário 6.3, até o Gemini).
2. O Gemini devolve uma chamada de ferramenta (`agendar_rega`), em vez de texto livre. O Gemini nunca aciona a bomba.
3. O backend valida: atraso e duração máximos, intervalo mínimo entre regas e dispositivo online. Se recusar, a resposta falada informa a recusa.
4. Se aceitar, o backend grava o agendamento no Firestore como `pendente` e cria uma tarefa `asyncio` em memória.
5. Na hora marcada, o backend marca o agendamento como `executando` (antes de publicar, para nunca duplicar) e publica o comando em `greensync/{deviceId}/comandos`.
6. O firmware WROOM liga a bomba pelo tempo pedido (limitado pelo tempo máximo do próprio firmware), desliga e publica `bomba_ligada`.
7. O backend marca o agendamento como `concluida`. Se o backend reiniciar, ele recarrega os `pendente` do Firestore no startup; agendamentos que passaram da tolerância (**[A DEFINIR]**, sugestão: 5 minutos) viram `expirada` e não são executados.

## 6.5 Runtime Scenario 5 — Dispositivo offline

1. Ao conectar, o firmware WROOM publica `{"status": "online"}` em `greensync/{deviceId}/status` (com retain) e registra o Last Will `{"status": "offline"}` no mesmo tópico.
2. Se o WROOM cair sem desconexão limpa, o broker publica o Last Will.
3. O backend recebe o status e atualiza o campo `status` do dispositivo no Firestore.
4. O app exibe "offline", evitando que o usuário confunda um dado antigo com um dado atual.

## 6.6 Runtime Scenario 6 — Primeira configuração de Wi-Fi (ou troca de rede)

1. Sem rede salva (ou com falha de conexão), o ESP abre uma rede própria (ex.: `GreenSync-Setup`).
2. O usuário conecta o celular a ela e escolhe a rede e a senha em uma página de configuração.
3. O ESP grava as credenciais na memória flash e reinicia já conectado.
4. Um botão físico, mantido pressionado, apaga a rede salva e reabre o portal.

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
| Firmware S3 | ESP32-S3 físico, no vaso |
| Broker MQTT | EMQX Cloud (plano gratuito/serverless **[A DEFINIR]**) |
| Backend | Render — serviço web pago (Starter, 512 MB de RAM), instância única, sempre ativo |
| Redis | Render Key Value (plano gratuito ou pago **[A DEFINIR]**) |
| Banco de dados | Firebase Firestore, região `southamerica-east1` |
| LLM / áudio de entrada | Google Gemini API (camada gratuita; cotas **[A DEFINIR]**) |
| App | Dispositivos móveis dos usuários/avaliadores |

## 7.2 Infrastructure Level 2

### Infrastructure Element 1 — Empacotamento do backend (Docker)

O backend é empacotado em uma imagem Docker (`Dockerfile`), usada tanto para o deploy no Render quanto para o desenvolvimento local (ADR-012). Localmente, um `docker-compose.yml` sobe o backend (com hot-reload) e um broker MQTT local (Eclipse Mosquitto); o Redis entra como serviço adicional:

```
docker-compose.yml (ambiente local)
├── backend      (FastAPI, hot-reload, porta 8000; monta serviceAccountKey.json como volume somente leitura)
├── mosquitto    (broker MQTT local, para desenvolver sem depender do EMQX Cloud)
└── redis        (planejado)
```

A chave de serviço do Firebase fica **fora da imagem**: é montada como volume em desenvolvimento e configurada como variável/arquivo secreto no Render. Em produção roda apenas o container do backend, apontando para o EMQX Cloud, o Redis e o Firebase — sem Mosquitto.

### Infrastructure Element 2 — Processos no serviço do Render

O serviço roda **um processo** (uvicorn): API HTTP, assinante MQTT e chamadas à IA. Não há worker, `beat` nem `supervisord` (ADR-015). Gatilhos para reavaliar a arquitetura de hospedagem: uso de memória próximo dos 512 MB, reinícios por falta de memória, ou respostas de voz lentas por disputa de CPU.

### Infrastructure Element 3 — Conectividade dos dispositivos (V1: Wi-Fi / V2: GPRS)

Na V1, os dois ESPs se conectam a uma rede Wi-Fi com acesso à internet, configurada por portal (ADR-022), com suporte a mais de uma rede (casa e faculdade). Na V2, o WROOM pode passar a usar um módulo GPRS/GSM com chip SIM — a camada MQTT permanece a mesma. Redes de faculdade podem bloquear portas de saída diferentes de 80/443; a porta 8883 deve ser testada na rede real **[A DEFINIR]**.

---

# 8. Cross-cutting Concepts

## 8.1 Contrato MQTT (Firmware WROOM ↔ Backend)

**Versão 1 do contrato — [A CONFIRMAR COM A FRENTE DE FIRMWARE]** (campos, unidades e intervalo de leitura).

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

Regras: campos extras são ignorados; payload inválido é registrado em log e descartado, sem derrubar o backend; se a leitura do DHT22 falhar (`NaN`), o firmware **não publica** aquela leitura. Intervalo de publicação sugerido: 10 a 30 s (o DHT22 exige cerca de 2 s entre leituras).

- QoS: 1 (entrega pelo menos uma vez).
- Tópico de status: `greensync/{deviceId}/status`, payload `{"status": "online"}` ou `{"status": "offline"}`.
  - O firmware publica `online` ao conectar, com retain.
  - O `offline` é o **Last Will**, publicado pelo broker em desconexão inesperada.
- Tópico de comandos (backend → WROOM) **(proposta)**: `greensync/{deviceId}/comandos`, QoS 1, payload por exemplo `{"acao": "regar", "duracao_s": 5, "id": "<idAgendamento>"}`. O firmware executa e aplica seu próprio limite de tempo máximo de bomba ligada.

## 8.2 Esquema do Firestore (Backend ↔ App)

```
devices/{deviceId}                      (documento)
  status: "online" | "offline"
  last_seen: timestamp
  leitura_atual: {                      (campo do tipo mapa, dentro do documento)
    ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, updated_at
  }
  historico/{autoId}                    (subcoleção)
    ph, umidade_solo, temperatura_ar, umidade_ar, bomba_ligada, timestamp
  agendamentos/{id}                     (subcoleção; planejado)
    executar_em: timestamp
    duracao_s: número
    status: "pendente" | "executando" | "concluida" | "cancelada" | "expirada" | "falhou"
    origem: "voz" | "app"
    criado_em: timestamp
```

`leitura_atual` é um campo do próprio documento (e não uma subcoleção): o app assina um único documento e recebe status e leitura juntos. A leitura atual e o registro de histórico são gravados no mesmo lote (ou ambos, ou nenhum). Campos ausentes na leitura (ex.: `umidade_ar`) ficam ausentes ou nulos.

## 8.3 Segurança

- Conexões MQTT sempre via TLS (porta 8883); o ESP precisa do certificado da CA do broker para validar a conexão.
- O endpoint de áudio exige `X-API-Key`, guardada em variável de ambiente, para ninguém consumir a cota do Gemini; o limite de perguntas por chave fica no Redis.
- Credenciais do broker, chave de serviço do Firebase, chave do Gemini e `X-API-Key` ficam **fora do controle de versão** (`.env` local; variáveis de ambiente no Render). O `.gitignore` cobre `.env` e arquivos de chave de serviço.
- Firestore em modo produção: o backend usa o Admin SDK (ignora as regras); as regras para o app serão definidas junto com a frente do aplicativo.
- Uma chave de serviço exposta deve ser revogada e substituída imediatamente.

## 8.4 Contrato HTTP de áudio (S3 ↔ Backend) — **(proposta, [A DEFINIR])**

- `POST /audio` — cabeçalhos: `X-API-Key` e identificação do dispositivo (`deviceId`). Corpo: áudio da pergunta.
- Resposta: áudio da resposta, na mesma requisição.
- **[A DEFINIR]**: formato do áudio enviado (PCM bruto ou WAV; sugestão: 16 kHz, 16 bits, mono — se vier PCM, o backend adiciona o cabeçalho WAV), formato do áudio devolvido, duração máxima da pergunta.
- `POST /perguntar` — mesma lógica, com a pergunta em texto; serve para testar o assistente sem hardware.

## 8.5 Validação e limites de atuação

O backend valida todo pedido de rega antes de agendar, com valores iniciais **a calibrar com testes reais**: atraso máximo (sugestão: 24 h), duração máxima (sugestão: 10 s), intervalo mínimo entre regas, recusa se o dispositivo estiver offline. A resposta falada reflete o resultado da validação. Se faltar duração no pedido, o backend usa um padrão calibrado. O firmware tem seu próprio tempo máximo de bomba ligada (defesa em profundidade).

## 8.6 Assistente com personalidade

O prompt do sistema faz a planta falar em primeira pessoa, de forma curta, só sobre a planta, usando apenas os números recebidos. Se um dado faltar, ela diz que não sabe. O "estado" da planta (ex.: com sede, ok) é calculado pelo backend a partir de limiares configuráveis, e o Gemini apenas dá a voz. O tom (mais informativo ou mais "planta") é configurável.

---

# 9. Architecture Decisions

Ver documento separado **ADR — Decisões — GreenSync**, que registra as decisões arquiteturais (ADR-001 a ADR-022). Decisões recentes, desta versão do documento:

| ADR | Tema |
|---|---|
| ADR-014 | Broker EMQX Cloud (substitui a ADR-002) |
| ADR-015 | Redis sem Celery (revisa a ADR-013) |
| ADR-016 | Dois microcontroladores: WROOM (sensores) e S3 (voz) (revisa a ADR-001) |
| ADR-017 | Áudio do S3 por HTTP com `X-API-Key` |
| ADR-018 | IA na V1 (revisa a ADR-011); Gemini com Groq de reserva |
| ADR-019 | Hospedagem paga no Render, instância única (revisa a ADR-003) |
| ADR-020 | Sensores DHT22 e YL-69 (substitui a ADR-008) |
| ADR-021 | Assistente com personalidade e rega por voz, agenda no Firestore |
| ADR-022 | Provisionamento de Wi-Fi por portal |

---

# 10. Quality Requirements

## 10.1 Quality Requirements Overview

Ver Seção 3.3 do documento SRS — Requisitos para os requisitos de qualidade de serviço detalhados (performance, segurança, confiabilidade, disponibilidade, observabilidade).

## 10.2 Quality Scenarios

| Cenário | Estímulo | Resposta esperada |
|---|---|---|
| Perda momentânea de Wi-Fi | Rede cai por alguns segundos | Firmware reconecta e retoma publicação MQTT automaticamente |
| Troca de rede (casa ↔ faculdade) | O vaso é levado para outra rede Wi-Fi | O ESP conecta a uma rede salva ou abre o portal de configuração, sem regravar o firmware |
| Backend reinicia com rega agendada | Render reinicia o serviço antes da hora da rega | No startup, o backend recarrega os agendamentos `pendente` do Firestore; os vencidos além da tolerância viram `expirada` |
| Pedido de rega excessivo | Usuário pede rega repetida ou muito longa | O backend recusa pelas regras de limite, e o firmware ainda aplica o tempo máximo de bomba |
| Excesso de perguntas | Chave de API usada além do limite | O backend recusa novas perguntas até o limite liberar |
| Leitura ruidosa do sensor de umidade | Valor oscila perto do limiar de irrigação | Histerese evita ligar/desligar repetidamente a bomba |
| Leitura inválida do DHT22 | O sensor falha e devolve `NaN` | O firmware não publica; se algo inválido chegar, o backend descarta |
| Instância duplicada do backend | Duas instâncias assinam o mesmo tópico | Evitado por configuração: instância única, sem autoscaling |

---

# 11. Risks and Technical Debts

| Risco/Débito | Descrição | Mitigação |
|---|---|---|
| Confiabilidade da sonda de pH | Sondas baratas de hobby têm calibração inconsistente e degradam com o tempo | Testar o componente isoladamente antes da integração; usar soluções tampão de calibração |
| Sensor de solo resistivo (YL-69) | Corrói com o tempo e exige calibração; a leitura bruta é invertida | Calibração seco/molhado no firmware; alimentar o sensor só durante a leitura; avaliar sensor capacitivo |
| Vedação física do vaso | Separação entre câmara eletrônica seca e substrato úmido é um desafio real de fabricação | Prototipar e testar a vedação antes da montagem final |
| Bomba e alimentação | Bomba e dois ESPs na mesma fonte de 5V; sem diodo de roda-livre e capacitor de desacoplamento, a bomba pode reiniciar o ESP ou queimar o transistor | Diodo de roda-livre, capacitor de desacoplamento e fonte com folga (ex.: 5V/3A) |
| Escopo da V1 maior | A IA e a rega por voz sobem para a V1; dois firmwares, áudio e cadeia de IA | Construir em camadas; validar o assistente em texto antes do hardware; manter a voz como camada sobre a irrigação base |
| Latência da voz | Chamadas ao Gemini e ao TTS somadas podem passar de alguns segundos | Medir cedo; respostas curtas; reduzir chamadas (áudio direto no Gemini) |
| Memória do Render (512 MB) | API, assinante MQTT, IA e Redis local disputam memória | Um processo só; monitorar; gatilhos de migração na Seção 7.2 |
| Plano do EMQX Cloud | Limites de conexões e mensagens do plano gratuito ainda não conferidos | Conferir antes de criar o cluster; Mosquitto local para desenvolvimento |
| Firewall da faculdade | Redes de faculdade podem bloquear a porta 8883 | Testar na rede real; alternativa de MQTT sobre WebSocket seguro na 443 |
| Cotas do Gemini | Limites do plano gratuito (incluindo áudio) ainda não conferidos | Conferir; isolar a chamada em `responder(audio, leitura)` para trocar de provedor |
| Contratos ainda não validados entre as frentes | Contrato MQTT, tópico de comandos e contrato HTTP de áudio ainda são propostas | Validar e travar cada contrato antes de o desenvolvimento paralelo avançar |
| Redis e a expectativa do professor | O uso definido (contexto, limite) pode não ser o esperado | Confirmar com o professor (fila, cache ou ambos) |
| Prazo | Prazos da V1 e da V2 ainda não definidos com a IA na V1 | Confirmar com o professor |

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
| Provisionamento de Wi-Fi | Configuração da rede do ESP sem regravar o firmware (portal de configuração) |
| Histerese | Margem de segurança que evita ligar/desligar repetidamente a bomba quando o valor oscila perto do limiar |
| V1 | Primeira fase de entrega: hardware, sensores, irrigação, sincronização de dados, app e assistente de voz |
| V2 | Segunda fase de entrega: conectividade GPRS |