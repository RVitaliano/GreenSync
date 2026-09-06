# Arc42 — Documento de Arquitetura de Software (SDD) — GreenSync

---

# 1. Introduction and Goals

## 1.1 Requirements Overview

O GreenSync é um vaso inteligente que monitora pH do solo, umidade do solo e temperatura do ar, controla irrigação automática, sincroniza dados em tempo real com um aplicativo mobile, e (na V2) responde perguntas faladas sobre a planta via assistente de voz. Ver o documento SRS — Requisitos para a especificação completa e verificável.

## 1.2 Quality Goals

| Prioridade | Meta de qualidade | Motivação |
|---|---|---|
| 1 | Confiabilidade dos dados de sensor | pH e umidade alimentam a irrigação automática — dado ruim gera decisão errada (rega demais/de menos) |
| 2 | Simplicidade de integração entre as três frentes | Grupo pequeno (3 pessoas), trabalho paralelo depende de contratos de interface bem definidos (MQTT/JSON, Firestore) |
| 3 | Baixo custo operacional | Projeto acadêmico, sem orçamento para serviços pagos — tudo em camada gratuita |
| 4 | Independência de rede local (V2) | Objetivo explícito de funcionar via GPRS, sem depender de Wi-Fi doméstico |

## 1.3 Stakeholders

| Role/Name | Contact | Expectations |
|---|---|---|
| Frente — Hardware/Firmware | Equipe GreenSync | Contrato de tópicos/JSON MQTT estável e definido cedo, para trabalhar em paralelo |
| Frente — App/Design | Equipe GreenSync | Esquema do Firestore estável, para consumir dados corretamente no app |
| Frente — Backend | Equipe GreenSync | Visão completa da integração entre hardware, nuvem e app |
| Professor orientador | — | Uso de MQTT (conteúdo da disciplina), projeto funcional de ponta a ponta na demonstração |

---

# 2. Architecture Constraints

- Protocolo de comunicação entre dispositivo e nuvem deve ser MQTT (exigência da disciplina).
- Microcontrolador definido: ESP32-S3 (já adquirido pelo grupo).
- Backend em Python + FastAPI.
- Aplicativo em Flutter.
- Banco de dados em nuvem: Firebase (Firestore).
- Sem armazenamento local/offline (ver ADR-010).
- Orçamento operacional: apenas camadas gratuitas ou de baixo custo.
- Alimentação elétrica única em 5V, sem bateria.

---

# 3. Context and Scope

## 3.1 Business Context

O usuário final interage apenas com o aplicativo mobile e, opcionalmente, observa o "rosto" exibido no display do próprio vaso. Não há interação direta do usuário com o backend, o broker MQTT ou o Firebase — esses são componentes internos, invisíveis ao usuário final.

```
Usuário ──(usa)──> App (Flutter)
Usuário ──(observa)──> Vaso GreenSync (display OLED)
```

## 3.2 Technical Context

```
ESP32-S3 ──MQTT/TLS──> HiveMQ Cloud (broker) ──MQTT/TLS──> Backend (FastAPI, Render)
                                                                  │
                                                                  ▼
                                                     Firebase (Firestore)
                                                                  │
                                                                  ▼
                                                        App (Flutter, FlutterFire)
```

O módulo de orquestração de IA (chamadas ao Gemini) começa a ser desenvolvido e testado já durante a V1, junto ao restante do backend, ainda que sua integração ao hardware de voz só ocorra na V2 (ver ADR-011). Na V2, o backend também se comunica com a API do **Google Gemini** (LLM, já definido — ver ADR-004) e com APIs externas de STT e TTS (provedores ainda a definir), e o ESP32-S3 pode usar um módulo GPRS em vez de Wi-Fi como camada de rede subjacente ao MQTT.

---

# 4. Solution Strategy

A estratégia central é manter o ESP32-S3 dedicado apenas à leitura de sensores, ao controle da bomba e à publicação MQTT — toda lógica de negócio (validação, persistência, e futuramente orquestração de IA) fica no backend, mantendo o firmware simples e o time de hardware/firmware desacoplado das mudanças na nuvem. O uso do MQTT como camada intermediária (em vez de o ESP32 escrever direto no Firebase) atende ao requisito pedagógico da disciplina e também melhora a tolerância a conexões intermitentes, o que é especialmente relevante para a V2 com GPRS.

---

# 5. Building Block View

## 5.1 Whitebox Overall System

**Motivation**

O sistema é dividido em cinco blocos principais, alinhados às responsabilidades das três frentes do grupo: firmware, backend e app — os dois blocos de infraestrutura (broker MQTT e Firebase) são serviços de terceiros configurados pelo grupo, não código próprio.

**Contained Building Blocks**

### Firmware (ESP32-S3)

- Purpose/Responsibility: ler sensores (pH, umidade do solo, temperatura), controlar a bomba d'água por relé, exibir estado no display OLED, publicar leituras via MQTT. Na V2: capturar áudio, reproduzir resposta de voz, gerenciar conectividade GPRS.
- Interface(s): MQTT (publisher) sobre TLS.
- Fulfilled Requirements: REQ-FUNC-001, REQ-FUNC-002, REQ-FUNC-003, REQ-FUNC-009, REQ-FUNC-010.
- Open Issues/Problems/Risks: confiabilidade da sonda de pH (ver Seção 11); lógica não bloqueante ainda a implementar para conviver com a conexão MQTT persistente.

### Broker MQTT (HiveMQ Cloud)

- Purpose/Responsibility: receber mensagens publicadas pelo firmware e redistribuí-las ao backend assinante; publicar mensagem de "last will" em caso de desconexão inesperada do dispositivo.
- Interface(s): MQTT sobre TLS (porta 8883).
- Fulfilled Requirements: REQ-FUNC-003, REQ-FUNC-007.

### Backend (Python + FastAPI, Render)

- Purpose/Responsibility: assinar os tópicos MQTT, validar e gravar os dados no Firestore. O módulo de orquestração de IA (chamadas ao Gemini) é desenvolvido em paralelo já na V1; na V2, esse módulo passa a orquestrar também as chamadas de STT e TTS, integradas ao hardware de voz.
- Interface(s): cliente MQTT (assinante); SDK Admin do Firebase; API do Google Gemini (LLM); APIs REST de STT/TTS (V2).
- Fulfilled Requirements: REQ-FUNC-004, REQ-FUNC-008 (V2).
- Open Issues/Problems/Risks: camada gratuita do Render "dorme" após inatividade (ver Seção 10).

### Firebase (Firestore)

- Purpose/Responsibility: armazenar a leitura atual e o histórico de cada dispositivo; sincronizar em tempo real com o app.
- Interface(s): SDK Admin (backend, escrita); FlutterFire (app, leitura em tempo real).
- Fulfilled Requirements: REQ-FUNC-004, REQ-FUNC-005, REQ-FUNC-006.

### App (Flutter)

- Purpose/Responsibility: exibir dados em tempo real e histórico; único meio de acompanhamento do usuário (sem dashboard web).
- Interface(s): FlutterFire (Firestore).
- Fulfilled Requirements: REQ-FUNC-005, REQ-FUNC-006.

### Name interface 1 — Tópicos MQTT (Firmware ↔ Broker ↔ Backend)

Contrato de nomes de tópico e payload JSON entre firmware e backend — a interface mais crítica do sistema, por conectar duas frentes de trabalho distintas do grupo. Ver Seção 8.1 para o esquema proposto.

### Name interface 2 — Esquema do Firestore (Backend ↔ App)

Estrutura de coleções/documentos que o backend escreve e o app lê. Ver Seção 8.2.

## 5.2 Level 2

### White Box: Firmware (V1)

Módulos internos: leitura de sensores (pH, umidade, temperatura), controle de irrigação (lógica de histerese), cliente MQTT, controle do display OLED.

### White Box: Backend (V1)

Módulos internos: cliente MQTT assíncrono (assinante), camada de gravação no Firestore (SDK Admin), e o módulo de orquestração de IA (chamadas ao Google Gemini), já desenvolvido e testado em paralelo desde a V1 — ver ADR-011. Na V2, esse módulo é estendido para incluir STT e TTS, e passa a ser acionado pelo firmware via hardware de voz.

## 5.3 Level 3

Não detalhado nesta versão do documento — nível de profundidade não necessário para o porte do projeto. A ser expandido conforme o backend evoluir na V2.

---

# 6. Runtime View

## 6.1 Runtime Scenario 1 — Ciclo normal de leitura e sincronização

1. O firmware lê pH, umidade do solo e temperatura do ar.
2. O firmware publica um payload JSON no tópico MQTT correspondente.
3. O broker HiveMQ recebe a mensagem e a repassa ao backend assinante.
4. O backend grava a leitura atual (sobrescrevendo) e adiciona um registro ao histórico no Firestore.
5. O app, com um listener ativo no Firestore, atualiza a tela automaticamente.

## 6.2 Runtime Scenario 2 — Irrigação automática

1. O firmware detecta, na leitura periódica, que a umidade do solo está abaixo do limiar configurado.
2. O firmware aciona o relé, ligando a bomba d'água.
3. O firmware publica o novo estado (`bomba_ligada: true`) junto com a leitura de sensores.
4. Quando a umidade volta ao patamar adequado (considerando a histerese), o firmware desliga a bomba e publica o novo estado.

## 6.3 Runtime Scenario 3 — Pergunta ao assistente de voz (V2)

1. O usuário fala uma pergunta próxima ao vaso; o firmware detecta a wake-word e captura o áudio.
2. O áudio é enviado ao backend (canal a definir — possivelmente um tópico MQTT dedicado ou uma conexão direta).
3. O backend envia o áudio à API de STT (provedor a definir), obtendo o texto da pergunta.
4. O backend monta um prompt com a pergunta e os dados mais recentes do Firestore, e chama a API do **Google Gemini** (LLM).
5. A resposta em texto é enviada à API de TTS (provedor a definir), gerando áudio.
6. O áudio de resposta é enviado de volta ao firmware, que o reproduz no alto-falante.

---

# 7. Deployment View

## 7.1 Infrastructure Level 1

**Motivation**

A infraestrutura é inteiramente baseada em serviços de terceiros de camada gratuita, adequada ao orçamento e ao porte acadêmico do projeto.

**Quality and/or Performance Features**

Baixo custo (gratuito); disponibilidade sujeita às limitações das camadas gratuitas (ex.: "sleep" do Render); sem redundância geográfica.

**Mapping of Building Blocks to Infrastructure**

| Building Block | Infraestrutura |
|---|---|
| Firmware | ESP32-S3 físico, no vaso |
| Broker MQTT | HiveMQ Cloud (free tier) |
| Backend | Render (free tier) |
| Banco de dados | Firebase Firestore (free tier) |
| App | Dispositivos móveis dos usuários/avaliadores |

## 7.2 Infrastructure Level 2

### Infrastructure Element 1 — Empacotamento do backend (Docker)

O backend é empacotado em uma imagem Docker (`Dockerfile`), usada tanto para o deploy no Render quanto para o ambiente de desenvolvimento local (ver ADR-012). Localmente, um `docker-compose.yml` sobe o backend (com hot-reload) e, opcionalmente, um broker MQTT local (Eclipse Mosquitto), para desenvolvimento sem depender do cluster do HiveMQ Cloud:

```
docker-compose.yml (ambiente local)
├── backend      (FastAPI, hot-reload, porta 8000)
└── mosquitto    (opcional — broker MQTT local para testes offline)
```

Em produção (Render), roda apenas o container do `backend`, apontando para o broker HiveMQ Cloud e para o Firebase — não há Mosquitto em produção.

### Infrastructure Element 2 — Conectividade do dispositivo (V1: Wi-Fi / V2: GPRS)

Na V1, o ESP32-S3 se conecta a uma rede Wi-Fi com acesso à internet. Na V2, essa camada é substituída por um módulo GPRS/GSM com chip SIM, tornando o dispositivo independente de rede Wi-Fi local — a camada MQTT acima permanece a mesma, apenas a camada de rede subjacente muda.

---

# 8. Cross-cutting Concepts

## 8.1 Contrato MQTT (Firmware ↔ Backend)

**[A DEFINIR EM CONJUNTO COM O RESPONSÁVEL PELO FIRMWARE]** — proposta inicial a validar:

- Tópico: `greensync/{deviceId}/sensores`
- Payload (JSON):
  ```json
  {
    "ph": 6.4,
    "umidade_solo": 42,
    "temperatura_ar": 24.1,
    "bomba_ligada": false,
    "timestamp": 1735000000
  }
  ```
- QoS sugerido: 1 (garante entrega pelo menos uma vez).
- Last Will: tópico `greensync/{deviceId}/status`, payload `{"status": "offline"}`, publicado automaticamente pelo broker em caso de desconexão inesperada.

## 8.2 Esquema do Firestore (Backend ↔ App)

```
devices/
  {deviceId}/
    status: "online" | "offline"
    last_seen: timestamp
    leitura_atual/
      ph, umidade_solo, temperatura_ar, bomba_ligada, updated_at
    historico/ (subcoleção)
      {autoId}/ ph, umidade_solo, temperatura_ar, bomba_ligada, timestamp
```

## 8.3 Segurança

Conexões MQTT sempre via TLS (porta 8883). Credenciais do broker e do Firebase mantidas fora do controle de versão (variáveis de ambiente no Render).

---

# 9. Architecture Decisions

Ver documento separado **ADR — Decisões — GreenSync**, que registra as decisões arquiteturais tomadas (ADR-001 a ADR-012), incluindo escolha do ESP32-S3, adoção de MQTT/HiveMQ, introdução do backend, LLM em nuvem, Firestore, Flutter, empacotamento em Docker, e as simplificações de escopo (remoção de LED, troca de sensor, fonte única de 5V, remoção do armazenamento local).

---

# 10. Quality Requirements

## 10.1 Quality Requirements Overview

Ver Seção 3.3 do documento SRS — Requisitos para os requisitos de qualidade de serviço detalhados (performance, segurança, confiabilidade, disponibilidade, observabilidade).

## 10.2 Quality Scenarios

| Cenário | Estímulo | Resposta esperada |
|---|---|---|
| Perda momentânea de Wi-Fi | Rede cai por alguns segundos | Firmware reconecta e retoma publicação MQTT automaticamente |
| Backend "dormindo" no Render | App faz a primeira requisição após período ocioso | Backend acorda e responde em alguns segundos (latência aceita nesta fase) |
| Leitura ruidosa do sensor de umidade | Valor oscila perto do limiar de irrigação | Histerese evita ligar/desligar repetidamente a bomba |

---

# 11. Risks and Technical Debts

| Risco/Débito | Descrição | Mitigação |
|---|---|---|
| Confiabilidade da sonda de pH | Sondas baratas de hobby têm calibração inconsistente e degradam com o tempo | Testar o componente isoladamente antes da integração; usar soluções tampão de calibração |
| Vedação física do vaso | Separação entre câmara eletrônica seca e substrato úmido é um desafio real de fabricação | Prototipar e testar a vedação antes da montagem final |
| Backend em camada gratuita | Render pode "dormir", introduzindo latência perceptível | Aceito para o escopo acadêmico; poderia ser mitigado com um serviço pago em um cenário real |
| Contrato MQTT ainda não validado entre as frentes | Proposta na Seção 8.1 ainda não foi confirmada com o responsável pelo firmware | Validar e travar o contrato antes do desenvolvimento paralelo avançar |
| Provedor de STT/TTS não definido | V2 depende dessa escolha, ainda em aberto (LLM já definido: Google Gemini, ver ADR-004) | Decisão a ser tomada com critério de custo (gratuito/baixo custo) antes do início da V2 |

---

# 12. Glossary

| Term | Definition |
|---|---|
| Broker MQTT | Serviço intermediário que recebe mensagens publicadas e as distribui aos assinantes de um tópico |
| Firestore | Banco de dados de documentos do Firebase usado para sincronização em tempo real |
| Last Will (MQTT) | Mensagem publicada automaticamente pelo broker quando um cliente se desconecta inesperadamente |
| QoS (MQTT) | Nível de garantia de entrega de uma mensagem (0, 1 ou 2) |
| V1 | Primeira fase de entrega: hardware, sensores, irrigação e sincronização de dados |
| V2 | Segunda fase de entrega: assistente de voz integrado e conectividade GPRS |
