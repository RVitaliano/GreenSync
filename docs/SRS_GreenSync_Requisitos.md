# Software Requirements Specification
## Para GreenSync

Version 0.1
Prepared by [GreenSync]
[Faculdade Nova Roma]
31 de agosto de 2026

## Table of Contents
<!-- TOC -->
* [1. Introduction](#1-introduction)
  * [1.1 Document Purpose](#11-document-purpose)
  * [1.2 Product Scope](#12-product-scope)
  * [1.3 Definitions, Acronyms, and Abbreviations](#13-definitions-acronyms-and-abbreviations)
  * [1.4 References](#14-references)
  * [1.5 Document Overview](#15-document-overview)
* [2. Product Overview](#2-product-overview)
  * [2.1 Product Perspective](#21-product-perspective)
  * [2.2 Product Functions](#22-product-functions)
  * [2.3 Product Constraints](#23-product-constraints)
  * [2.4 User Characteristics](#24-user-characteristics)
  * [2.5 Assumptions and Dependencies](#25-assumptions-and-dependencies)
  * [2.6 Apportioning of Requirements](#26-apportioning-of-requirements)
* [3. Requirements](#3-requirements)
  * [3.1 External Interfaces](#31-external-interfaces)
  * [3.2 Functional](#32-functional)
  * [3.3 Quality of Service](#33-quality-of-service)
  * [3.4 Compliance](#34-compliance)
  * [3.5 Design and Implementation](#35-design-and-implementation)
  * [3.6 AI/ML](#36-aiml)
* [4. Verification](#4-verification)
* [5. Appendixes](#5-appendixes)
<!-- TOC -->

## Revision History

| Name | Date | Reason For Changes | Version |
|------|------|--------------------|---------|
| Grupo GreenSync | 31/08/2026 | Primeira versão, consolidando decisões tomadas até a reunião com o professor orientador | 0.1 |
| Grupo GreenSync | 06/09/2026 | Unificação da terminologia do time (sem referência a integrantes individuais); definição do provedor de LLM (Google Gemini, camada gratuita); ajuste da estratégia de desenvolvimento do módulo de IA para ocorrer em paralelo com a V1 | 0.2 |

## 1. Introduction

Este documento especifica os requisitos do GreenSync, um vaso inteligente com assistente de voz, desenvolvido como projeto acadêmico. Ele cobre o escopo funcional e não funcional do sistema nas duas fases planejadas (V1 e V2), servindo como referência para as três frentes de trabalho do grupo (hardware/firmware, backend, e aplicativo/design).

### 1.1 Document Purpose

Este SRS define **o que** o sistema GreenSync deve fazer, para orientar o desenvolvimento paralelo das três frentes do projeto (hardware/firmware, backend, aplicativo) e servir de referência para a avaliação acadêmica. É usado pelo grupo para alinhar escopo antes de codar, e pelo professor orientador como critério de avaliação do que foi ou não entregue em cada fase.

### 1.2 Product Scope

O GreenSync (V1) é um vaso inteligente que monitora pH do solo, umidade do solo e temperatura do ar, controla irrigação automática por bomba d'água, e sincroniza esses dados em tempo real com um aplicativo mobile via nuvem (MQTT → backend → Firebase). Na V2, o sistema incorpora um assistente de voz (LLM em nuvem) para responder perguntas sobre a planta com base nos dados reais dos sensores, e substitui a conectividade Wi-Fi por um módulo GPRS, tornando o dispositivo independente de rede local.

**Incluído no escopo:** aquisição e envio de dados de sensores, irrigação automática, sincronização em nuvem, aplicativo de acompanhamento, assistente de voz consultivo (V2), conectividade celular (V2).

**Fora do escopo:** controle de iluminação artificial (removido do projeto), armazenamento local/offline de dados, dashboard web (o app é o único meio de acompanhamento), controle de atuadores por voz (o assistente é consultivo, não de comando), suporte a múltiplos vasos/usuários simultâneos.

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| ADC | Analog-to-Digital Converter — conversor que transforma leitura analógica de sensor em valor digital |
| API | Application Programming Interface |
| Broker MQTT | Serviço intermediário que recebe mensagens publicadas e as distribui aos assinantes de um tópico |
| Firestore | Banco de dados de documentos do Firebase, usado para sincronizar dados em tempo real com o app |
| GPRS | General Packet Radio Service — conectividade de dados via rede celular, usada na V2 |
| LLM | Large Language Model — modelo de linguagem usado pelo assistente de voz |
| MQTT | Message Queuing Telemetry Transport — protocolo leve de publicação/assinatura usado para IoT |
| QoS (MQTT) | Quality of Service — nível de garantia de entrega de uma mensagem MQTT (0, 1 ou 2) |
| SRS | Software Requirements Specification |
| STT | Speech-to-Text — conversão de voz em texto |
| TTS | Text-to-Speech — conversão de texto em voz |
| UI | User Interface |
| V1 | Primeira fase de entrega do projeto: hardware, sensores, irrigação e sincronização de dados |
| V2 | Segunda fase de entrega: assistente de voz integrado e upgrade para conectividade GPRS |

### 1.4 References

| Referência | Tipo | Local |
|---|---|---|
| Lista de Componentes de Hardware — GreenSync | Normativo | Documento do grupo (Word) |
| ADR — Decisões — GreenSync | Normativo | ADR_-_Decisões.md (este pacote) |
| Arc42 — SDD — GreenSync | Normativo | Arc42_-_SDD.md (este pacote) |
| Documentação HiveMQ Cloud | Informativo | site oficial do provedor |
| Documentação FlutterFire | Informativo | site oficial do Firebase/Flutter |

### 1.5 Document Overview

A Seção 2 dá uma visão geral do produto (contexto, funções, restrições, usuários). A Seção 3 lista os requisitos verificáveis, organizados por interface externa, função, qualidade de serviço, conformidade, implementação e IA. A Seção 4 mapeia como cada requisito será verificado. A Seção 5 traz apêndices de apoio. Requisitos ainda em aberto (dependentes de decisão futura do grupo ou do professor) estão marcados como **[A DEFINIR]**.

## 2. Product Overview

### 2.1 Product Perspective

O GreenSync é um produto novo, desenvolvido do zero como projeto acadêmico, inspirado em conversas com o professor orientador (cujo projeto pessoal usa arquitetura de IA local — decisão consciente do grupo foi seguir por um caminho de LLM em nuvem, ver ADR-004). Não há sistema legado a substituir. O sistema depende de três serviços de terceiros essenciais: HiveMQ Cloud (broker MQTT), Firebase (Firestore, sincronização e armazenamento), e provedores de LLM/STT/TTS em nuvem — o LLM já definido (Google Gemini, camada gratuita), com STT e TTS ainda a definir. Não há SLA formal contratado — todos os serviços usados são de camada gratuita ou de baixo custo.

### 2.2 Product Functions

- Medir pH do solo, umidade do solo e temperatura do ar continuamente
- Acionar automaticamente a bomba d'água quando a umidade do solo estiver abaixo do limiar configurado
- Publicar as leituras dos sensores via MQTT para a nuvem
- Persistir os dados recebidos no Firebase (leitura atual + histórico)
- Exibir os dados em tempo real e o histórico no aplicativo mobile
- Indicar visualmente o estado da planta em um display OLED no próprio vaso
- Responder perguntas faladas sobre o estado da planta usando um assistente de voz (V2)
- Permitir mudo físico do microfone por botão dedicado
- Conectar-se à internet via GPRS, sem depender de Wi-Fi local (V2)

### 2.3 Product Constraints

- O sistema **deve** usar MQTT como protocolo de comunicação entre o dispositivo e a nuvem (requisito da disciplina, definido pelo professor orientador)
- O microcontrolador **deve** ser o ESP32-S3, já definido e adquirido pelo grupo
- O backend **deve** ser implementado em Python com FastAPI
- O aplicativo **deve** ser implementado em Flutter
- O armazenamento em nuvem **deve** usar Firebase (Firestore)
- O sistema **não deve** depender de armazenamento local (sem microSD) — toda a persistência é em nuvem
- O orçamento de serviços em nuvem **deve** permanecer em camada gratuita ou de baixo custo (broker MQTT, hospedagem do backend, LLM/STT/TTS) — ver ADR e Seção 3.5.7
- A alimentação elétrica **deve** ser única, em 5V, sem uso de bateria (dispositivo estacionário, ligado à tomada)

### 2.4 User Characteristics

| Perfil | Descrição | Frequência de uso | Expectativas |
|---|---|---|---|
| Usuário doméstico | Pessoa cuidando de uma planta em casa | Diária/casual, via app | Ver o estado da planta rapidamente, sem precisar entender os dados técnicos |
| Avaliador (professor) | Avalia o projeto academicamente | Pontual, na demonstração | Ver o sistema funcionando de ponta a ponta, entender as decisões técnicas tomadas |
| Integrante do grupo (desenvolvimento) | Desenvolve/mantém uma das três frentes | Constante durante o desenvolvimento | Interfaces (MQTT, Firestore, API) bem definidas entre as frentes |

### 2.5 Assumptions and Dependencies

| Assunção/Dependência | Impacto se for falsa |
|---|---|
| O HiveMQ Cloud (free tier) atende ao volume de mensagens do projeto | Precisaria migrar de broker, atrasando a integração |
| O Render (free tier) mantém o backend disponível o suficiente para a demonstração | Backend pode "dormir" e demorar a responder na primeira requisição — ver Seção 3.3.4 |
| Existe conectividade Wi-Fi com internet no local da demonstração da V1 | Sistema não teria como sincronizar dados na demo |
| A operadora escolhida para o chip SIM (V2) oferece cobertura no local de uso | Módulo GPRS não conseguiria conectar |
| O Google Gemini (LLM já definido) e os provedores de STT/TTS (ainda a definir) têm suporte adequado a português | Respostas do assistente de voz poderiam ter qualidade baixa |
| A sonda de pH adquirida é confiável o suficiente para leituras consistentes | Maior risco técnico identificado pelo grupo — ver Seção 11 do Arc42 |

### 2.6 Apportioning of Requirements

| Área de requisito | Fase | Responsável |
|---|---|---|
| Leitura de sensores, irrigação automática, publicação MQTT | V1 | Hardware/firmware |
| Backend (assinatura MQTT, escrita no Firestore) | V1 | Backend |
| App — exibição de dados em tempo real e histórico | V1 | App/design |
| Módulo de orquestração de IA (LLM via Google Gemini) — desenvolvimento e testes com dados do Firestore | V1 (em paralelo) | Backend |
| Assistente de voz — integração do módulo de IA ao hardware (captura de áudio, STT, TTS, reprodução) | V2 | Backend + Hardware/firmware |
| Conectividade GPRS | V2 | Hardware/firmware |

## 3. Requirements

### 3.1 External Interfaces

#### 3.1.1 User Interfaces

- O aplicativo mobile (Flutter) é a única interface de usuário do sistema — não há dashboard web.
- O app deve exibir, em tela principal: pH atual, umidade do solo atual, temperatura do ar atual, estado da bomba (ligada/desligada), estado de conexão do dispositivo (online/offline).
- O app deve exibir um gráfico de histórico de pelo menos uma das grandezas monitoradas (ex.: umidade do solo ao longo do tempo).
- O vaso possui um display OLED local mostrando um "rosto" com expressões simples que refletem o estado da planta — não é interativo, só informativo.
- **[A DEFINIR]** padrão visual/acessibilidade do app (não definido formalmente pelo grupo até o momento).

#### 3.1.2 Hardware Interfaces

- Ver a Lista de Componentes de Hardware (documento separado) para o mapeamento completo de sensores, atuadores e pinagem.
- Sensores de pH e umidade do solo: interface analógica (ADC do ESP32-S3, ou ADC externo opcional ADS1115 via I2C).
- Sensor de temperatura do ar (DS18B20): interface digital de 1 fio.
- Bomba d'água: acionada via módulo relé (ou MOSFET), controlado por GPIO digital do ESP32-S3.
- Display OLED (SSD1306): interface I2C.
- Alimentação: fonte externa única de 5V; regulador de tensão reduz para 3,3V onde necessário.

#### 3.1.3 Software Interfaces

| Sistema | Direção | Protocolo | Dados trocados |
|---|---|---|---|
| Broker MQTT (HiveMQ Cloud) | ESP32-S3 → Broker | MQTT sobre TLS (porta 8883) | Leituras de sensores em JSON |
| Broker MQTT (HiveMQ Cloud) | Broker → Backend | MQTT sobre TLS (porta 8883) | Leituras de sensores em JSON (assinatura de tópico) |
| Firebase (Firestore) | Backend → Firestore | SDK Admin (gRPC/HTTPS) | Documentos de leitura atual e histórico |
| Firebase (Firestore) | Firestore → App | FlutterFire (SDK cliente) | Listeners em tempo real |
| API de LLM (nuvem) | Backend → Google Gemini API | HTTPS/REST | Pergunta do usuário + contexto de dados do sensor → resposta em texto |
| API de STT (nuvem) | Backend → Provedor **[A DEFINIR]** | HTTPS/REST | Áudio → texto |
| API de TTS (nuvem) | Backend → Provedor **[A DEFINIR]** | HTTPS/REST | Texto → áudio |

### 3.2 Functional

- ID: REQ-FUNC-001
- Title: Leitura periódica dos sensores
- Statement: O firmware do ESP32-S3 shall ler os valores de pH do solo, umidade do solo e temperatura do ar em intervalo regular configurável.
- Rationale: Base de dados para irrigação automática e para exibição no app.
- Acceptance Criteria: Os três valores são lidos e exibidos via Serial (fase de bancada) em intervalo ≤ definido pelo grupo, sem travar o loop principal.
- Verification Method: Demonstration
- More Information: Ver código de referência de leitura de sensores compartilhado pelo grupo.

- ID: REQ-FUNC-002
- Title: Irrigação automática por umidade do solo
- Statement: O sistema shall acionar a bomba d'água quando a umidade do solo estiver abaixo do limiar configurado, e desligá-la quando o limiar for atingido novamente.
- Rationale: Automatizar a rega da planta sem intervenção manual.
- Acceptance Criteria: Bomba liga em solo seco simulado e desliga ao atingir umidade adequada, com histerese suficiente para evitar acionamentos repetidos ("chattering").
- Verification Method: Test
- More Information: Limiar e histerese calibrados empiricamente pelo grupo.

- ID: REQ-FUNC-003
- Title: Publicação de dados via MQTT
- Statement: O firmware shall publicar as leituras dos sensores e o estado da bomba em um tópico MQTT definido, em formato JSON, a cada ciclo de leitura.
- Rationale: Requisito da disciplina; base para sincronização com a nuvem.
- Acceptance Criteria: Mensagem publicada no broker HiveMQ é recebida por um cliente assinante de teste, no formato JSON acordado entre hardware/firmware e backend.
- Verification Method: Test

- ID: REQ-FUNC-004
- Title: Persistência dos dados recebidos
- Statement: O backend shall assinar o(s) tópico(s) MQTT relevante(s) e gravar os dados recebidos no Firestore, atualizando o documento de leitura atual e adicionando um registro ao histórico.
- Rationale: Permitir consulta em tempo real e histórico no app.
- Acceptance Criteria: Mensagem publicada é refletida no Firestore em até [A DEFINIR] segundos; histórico acumula sem sobrescrever leituras anteriores.
- Verification Method: Test

- ID: REQ-FUNC-005
- Title: Exibição de dados em tempo real no app
- Statement: O aplicativo shall exibir os valores atuais de pH, umidade do solo, temperatura do ar e estado da bomba, atualizando automaticamente quando novos dados chegarem ao Firestore.
- Rationale: Função principal de acompanhamento do usuário.
- Acceptance Criteria: Alteração no Firestore reflete na tela do app sem necessidade de recarregar manualmente.
- Verification Method: Demonstration

- ID: REQ-FUNC-006
- Title: Exibição de histórico no app
- Statement: O aplicativo shall exibir um gráfico com a evolução de pelo menos uma grandeza monitorada ao longo do tempo.
- Rationale: Permitir ao usuário perceber tendências (ex.: solo secando ao longo do dia).
- Acceptance Criteria: Gráfico exibe pontos correspondentes aos documentos de histórico no Firestore.
- Verification Method: Demonstration

- ID: REQ-FUNC-007
- Title: Indicação de estado offline
- Statement: O sistema shall indicar no app quando o dispositivo estiver offline, usando uma mensagem MQTT de "last will" publicada automaticamente pelo broker em caso de desconexão inesperada.
- Rationale: Evitar que o usuário veja um dado antigo como se fosse atual.
- Acceptance Criteria: Ao desconectar o ESP32-S3 da energia/rede, o app exibe o status "offline" em até [A DEFINIR] segundos.
- Verification Method: Test

- ID: REQ-FUNC-008
- Title: Assistente de voz consultivo (V2)
- Statement: O sistema shall permitir que o usuário faça perguntas faladas sobre o estado da planta e receba uma resposta falada, gerada a partir dos dados reais dos sensores.
- Rationale: Diferencial do produto; objetivo central da V2.
- Acceptance Criteria: Pergunta como "como está minha planta?" resulta em resposta coerente com os dados atuais de pH/umidade/temperatura.
- Verification Method: Demonstration
- More Information: Não inclui controle de atuadores por voz — assistente é somente consultivo. LLM: Google Gemini API (ver ADR-004); módulo de orquestração desenvolvido em paralelo desde a V1, integrado ao hardware de voz somente na V2.

- ID: REQ-FUNC-009
- Title: Mute físico do microfone
- Statement: O sistema shall permitir que o usuário corte fisicamente a captura de áudio por meio de um botão/switch dedicado.
- Rationale: Privacidade — o assistente de voz não deve escutar continuamente sem controle do usuário.
- Acceptance Criteria: Com o botão acionado, nenhum áudio é capturado pelo INMP441.
- Verification Method: Inspection

- ID: REQ-FUNC-010
- Title: Conectividade via GPRS (V2)
- Statement: O sistema shall ser capaz de publicar dados via MQTT usando o módulo GPRS como conexão de rede, sem depender de Wi-Fi.
- Rationale: Tornar o dispositivo independente de rede local, ampliando os cenários de uso.
- Acceptance Criteria: Com o Wi-Fi desabilitado e o chip SIM ativo, os dados continuam sendo publicados no broker MQTT.
- Verification Method: Test

### 3.3 Quality of Service

#### 3.3.1 Performance

- A leitura dos sensores não deve bloquear a manutenção da conexão MQTT (uso de lógica não bloqueante em vez de `delay()` no firmware).
- O tempo entre a leitura de um sensor e sua exibição no app deve ser **[A DEFINIR]** (meta sugerida: poucos segundos, compatível com camadas gratuitas dos serviços usados).
- O sistema é de baixo volume de dados (um único dispositivo, poucas leituras por minuto) — não há requisito de throughput elevado.

#### 3.3.2 Security

- A conexão do ESP32-S3 e do backend com o broker MQTT deve usar TLS (porta 8883), nunca a porta não criptografada.
- Credenciais do broker MQTT e do Firebase (chave de serviço) não devem ser expostas em repositório público de código.
- Não há dados pessoais sensíveis trafegando no sistema (apenas leituras ambientais de uma planta) — requisitos de privacidade formal (ex.: LGPD) são de baixo risco, mas as boas práticas acima devem ser seguidas de qualquer forma.

#### 3.3.3 Reliability

- O sistema deve tolerar perda momentânea de conexão Wi-Fi/GPRS, retomando a publicação MQTT automaticamente quando a conexão for restabelecida.
- A lógica de irrigação deve ter histerese para evitar acionamentos repetidos da bomba por ruído de leitura do sensor (ver REQ-FUNC-002).
- O sensor de pH é reconhecido pelo grupo como o componente de maior risco de confiabilidade (sondas baratas podem ter calibração inconsistente) — recomenda-se teste isolado do componente antes da integração.

#### 3.3.4 Availability

- O backend hospedado no Render (camada gratuita) pode entrar em modo de espera após período de inatividade, levando alguns segundos para responder à primeira requisição subsequente — comportamento aceito pelo grupo para a fase de desenvolvimento e demonstração.
- Não há requisito de alta disponibilidade formal (SLA) — o projeto é acadêmico, não um serviço em produção contínua.

#### 3.3.5 Observability

- O backend deve registrar (log) as mensagens MQTT recebidas e as respectivas gravações no Firestore, para facilitar depuração durante o desenvolvimento.
- **[A DEFINIR]** ferramentas específicas de monitoramento (não definidas — provavelmente logs simples do Render nesta fase).

### 3.4 Compliance

Não há requisitos regulatórios ou contratuais formais aplicáveis a este projeto acadêmico. Os únicos "contratos" relevantes são os termos de uso das camadas gratuitas dos serviços de terceiros usados (HiveMQ Cloud, Render, Firebase, e o provedor de LLM/STT/TTS a definir), que devem ser respeitados quanto a limites de uso.

### 3.5 Design and Implementation

#### 3.5.1 Installation

- Firmware: gravado no ESP32-S3 via Arduino IDE (ou PlatformIO), USB-C.
- Backend: empacotado em imagem Docker (`Dockerfile`); implantado no Render a partir do repositório do grupo (deploy automático a partir da branch principal). Localmente, qualquer integrante sobe o backend com `docker compose up`, sem precisar configurar Python/dependências manualmente.
- Ambiente local (`docker-compose.yml`): serviço `backend` (com hot-reload, montando o código local) e, opcionalmente, um serviço `mosquitto` (broker MQTT local), para desenvolvimento sem depender do cluster do HiveMQ Cloud. O endereço do broker é configurável por variável de ambiente, alternando entre local e HiveMQ.
- App: instalado nos aparelhos de teste via build de desenvolvimento Flutter; distribuição final **[A DEFINIR]** (provavelmente APK/build local para a demonstração, sem publicação em loja).

#### 3.5.2 Build and Delivery

- Controle de versão via Git/GitHub, um repositório por frente de trabalho ou um monorepo — **[A DEFINIR]** pelo grupo.
- Backend: imagem Docker construída a partir do `Dockerfile` do repositório; deploy automático no Render a cada push na branch principal, usando essa mesma imagem.
- Variáveis sensíveis (credenciais do HiveMQ, chave de serviço do Firebase) mantidas em `.env` fora do controle de versão, injetadas como variáveis de ambiente tanto no `docker-compose` local quanto no Render.
- Firmware: sem pipeline automatizado — gravação manual durante o desenvolvimento.

#### 3.5.3 Distribution

Não aplicável em profundidade — o sistema roda em um único dispositivo físico (um vaso), um backend, e os clientes do app. Não há topologia distribuída ou replicação de dados além do que o Firebase já oferece nativamente.

#### 3.5.4 Maintainability

- Separação clara de responsabilidades entre firmware, backend e app, com o contrato MQTT/JSON como interface estável entre hardware e backend.
- Código do backend organizado por módulo (cliente MQTT, integração Firebase, e futuramente orquestração de LLM/STT/TTS).

#### 3.5.5 Reusability

O backend é desenhado para múltiplos dispositivos no futuro (estrutura `devices/{deviceId}` no Firestore), mesmo que a demonstração acadêmica use apenas um vaso.

#### 3.5.6 Portability

- Firmware é específico do ESP32-S3 (não portável a outras placas sem adaptação).
- O app em Flutter é multiplataforma (Android/iOS) por natureza da tecnologia escolhida.

#### 3.5.7 Cost

- Todos os serviços de nuvem usados devem permanecer em camada gratuita ou de baixo custo: HiveMQ Cloud (free tier), Render (free tier), Firebase (free tier do Firestore), Google Gemini API (free tier — já escolhido com esse critério, ver ADR-004), e os provedores de STT/TTS ainda a escolher com o mesmo critério.
- Custo de hardware é único (compra de componentes), não recorrente.

#### 3.5.8 Deadline

- V1 (hardware, sensores, irrigação, sincronização de dados, app básico): prazo **[A DEFINIR]** pelo grupo/professor.
- V2 (assistente de voz integrado, GPRS): prazo **[A DEFINIR]**, posterior à V1.

#### 3.5.9 Proof of Concept

- Antes da integração completa, o grupo validará isoladamente: (a) a sonda de pH, por ser o componente de maior risco; (b) o fluxo MQTT ESP32 → HiveMQ → backend, com dados simulados; (c) a leitura/escrita no Firestore a partir do backend.

#### 3.5.10 Change Management

Processo informal, adequado ao porte do grupo (3 pessoas): mudanças de contrato (tópicos MQTT, esquema JSON, estrutura do Firestore) devem ser comunicadas entre os responsáveis antes de implementadas, já que alteram a interface entre as três frentes de trabalho.

### 3.6 AI/ML

Esta seção se aplica somente à V2 (assistente de voz). Dado o porte acadêmico do projeto e o uso de uma API de LLM de terceiros hospedada (sem treinamento ou ajuste de modelo próprio), várias subseções do template completo não se aplicam e estão marcadas como tal, em vez de preenchidas artificialmente.

#### 3.6.1 Model Specification

- O modelo é a API do **Google Gemini**, escolhida por oferecer camada gratuita (critério: custo zero) com qualidade adequada em português — ver ADR-004.
- Escopo do modelo: responder perguntas sobre o estado da planta a partir dos dados reais dos sensores (contexto injetado no prompt) — não é um chatbot de propósito geral.
- Não há dataset de validação próprio nem versionamento de modelo pelo grupo — a qualidade é a fornecida pelo provedor escolhido.
- O módulo de orquestração desse LLM é desenvolvido e testado em paralelo já durante a V1 (com dados reais do Firestore, mas sem o hardware de voz ainda conectado) — ver ADR-011 e Seção 2.6.

#### 3.6.2 Data Management

- Os dados enviados ao modelo são as leituras dos sensores (pH, umidade, temperatura) e a pergunta do usuário — não há dados pessoais ou sensíveis envolvidos.
- Não há coleta, rotulagem ou treinamento de dataset próprio — não aplicável a este projeto.

#### 3.6.3 Guardrails

- O prompt enviado ao LLM deve restringir o escopo de resposta a perguntas sobre a planta/dados dos sensores, evitando que o assistente responda a perguntas fora desse domínio.
- Não há mecanismo de moderação de conteúdo adicional além do que o provedor de LLM já oferece nativamente — considerado suficiente para o escopo do projeto.

#### 3.6.4 Ethics

Não aplicável em profundidade — o sistema não toma decisões que afetam pessoas de forma consequente (é um assistente informativo sobre uma planta), portanto não há requisitos de equidade (fairness) ou explicabilidade formal além de o assistente citar os dados reais que embasam sua resposta.

#### 3.6.5 Human-in-the-Loop

Não aplicável — o assistente responde de forma totalmente automatizada, sem revisão humana antes de cada resposta, dado o baixo risco das respostas (informações sobre uma planta).

#### 3.6.6 Model Lifecycle and Operations

- Não há retreinamento ou versionamento de modelo pelo grupo — a troca de provedor de LLM (se necessária) é uma mudança de configuração no backend, não uma operação de ciclo de vida de modelo.

## 4. Verification

| Requirement ID | Verification Method | Test/Artifact Link | Status | Evidence |
|----------------|---------------------|---------------------|--------|----------|
| REQ-FUNC-001 | Demonstration | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-002 | Test | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-003 | Test | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-004 | Test | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-005 | Demonstration | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-006 | Demonstration | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-007 | Test | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-008 | Demonstration | [A DEFINIR] | Não iniciado (V2) | |
| REQ-FUNC-009 | Inspection | [A DEFINIR] | Não iniciado | |
| REQ-FUNC-010 | Test | [A DEFINIR] | Não iniciado (V2) | |

## 5. Appendixes

- Lista de Componentes de Hardware — GreenSync (documento Word separado, com tabela completa de componentes por grupo e fase V1/V2).
- ADR — Decisões — GreenSync (registro das decisões arquiteturais tomadas, ver arquivo próprio).
- Arc42 — SDD — GreenSync (documento de arquitetura de software, ver arquivo próprio).
