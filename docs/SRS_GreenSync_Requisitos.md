# Software Requirements Specification
## Para GreenSync

Version 0.7
Prepared by [GreenSync]
[Faculdade Nova Roma]
09 de novembro de 2026

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
| Grupo GreenSync | 31/08/2026 | Primeira versão, consolidando as decisões iniciais do projeto | 0.1 |
| Grupo GreenSync | 06/09/2026 | Unificação da terminologia do time (sem referência a integrantes individuais); definição do provedor de LLM (Google Gemini, camada gratuita); ajuste da estratégia de desenvolvimento do módulo de IA para ocorrer em paralelo com a V1 | 0.2 |
| Grupo GreenSync | 21/09/2026 | Incorporação das decisões de arquitetura: dois microcontroladores (WROOM e S3), assistente de voz na V1, EMQX Cloud, Redis sem Celery, hospedagem paga no Render, sensores DHT22 e YL-69, assistente com personalidade e rega por voz com agenda, provisionamento de Wi-Fi (ADR-014 a ADR-022); novos requisitos REQ-FUNC-011 a REQ-FUNC-015 | 0.3 |
| Grupo GreenSync | 01/10/2026 | Definição de que o display OLED fica no ESP32-S3 (junto com a voz) e alterna entre a carinha da planta e os dados dos sensores ao ser feita uma pergunta — resolve a pendência deixada em aberto pela ADR-016 (ADR-023); novo requisito REQ-FUNC-016 | 0.4 |
| Grupo GreenSync | 03/11/2026 | Backend implementado: contrato HTTP de áudio definido (`X-Tela`, `X-Dados`, códigos de erro), limites da rega e do limite de perguntas definidos, TTS pelo Gemini, pedido de rega por saída estruturada (ADR-024 a ADR-026), tabela de verificação atualizada com os testes | 0.5 |
| Grupo GreenSync | 09/11/2026 | Revisão do backend: trava de palavra também no cancelamento, publicação incerta do comando, Firestore lento tratado como "sem dados", padrões do Gemini e duração da rega de 15 s na demonstração (ADR-025 e ADR-026, Arc42 8.5 e 8.8) | 0.6 |
| Grupo GreenSync | 09/11/2026 | pH falado sempre com o valor exato (ADR-027); testes das rotas contra falha real do Firestore; estratégia de testes (ADR-028) e novo Plano de Testes em formato IEEE 829; suíte com 448 testes | 0.7 |
| Grupo GreenSync | 23/11/2026 | Fases redefinidas: V1 é o vaso do WROOM, V2 é a voz do S3, sem GPRS (ADR-033; REQ-FUNC-010 retirado); firmware do WROOM funcionando (sensores reais, bomba, BLE e OTA); rega somente por comando (ADR-031); configuração de Wi-Fi por BLE (ADR-029); atualização OTA (ADR-030); palavra de ativação no S3 (ADR-032); novos requisitos REQ-FUNC-017 e REQ-FUNC-018; metas de desempenho definidas; suíte com 973 testes | 0.8 |

## 1. Introduction

Este documento especifica os requisitos do GreenSync, um vaso inteligente com assistente de voz, desenvolvido como projeto acadêmico. Ele cobre o escopo funcional e não funcional do sistema nas duas fases do projeto (V1 e V2), servindo como referência para as três frentes de trabalho do grupo (hardware/firmware, backend, e aplicativo/design).

### 1.1 Document Purpose

Este SRS define **o que** o sistema GreenSync deve fazer, para orientar o desenvolvimento paralelo das três frentes do projeto (hardware/firmware, backend, aplicativo) e servir de referência para a avaliação do que foi entregue em cada fase. É usado pelo grupo para alinhar escopo antes de codar e pelos avaliadores da demonstração.

### 1.2 Product Scope

O GreenSync é um vaso inteligente que monitora pH do solo, umidade do solo, temperatura e umidade do ar, controla irrigação automática por bomba d'água, e sincroniza esses dados em tempo real com um aplicativo mobile via nuvem (MQTT → backend → Firebase). O sistema usa dois microcontroladores: um ESP32-WROOM (sensores e bomba, comunicação via MQTT) e um ESP32-S3 (voz e display, comunicação via HTTP com o backend).

Na V2, o sistema inclui também um assistente de voz (LLM em nuvem, Google Gemini) que responde como a própria planta, com base nos dados reais dos sensores, e pode agendar regas por comando de voz, com validação no backend.

**Incluído no escopo:** aquisição e envio de dados de sensores, rega por comando, sincronização em nuvem, aplicativo de acompanhamento, configuração de Wi-Fi por BLE e atualização de firmware pela rede (OTA), sem regravar por cabo (V1), assistente de voz com personalidade da planta (V2), display com carinha da planta que alterna para os dados dos sensores ao ser perguntado (V2), rega por comando de voz com agendamento validado (V2).

**Fora do escopo:** controle de iluminação artificial (removido do projeto), armazenamento local/offline de dados, dashboard web (o app é o único meio de acompanhamento), controle por voz de qualquer atuador além da rega pela bomba, configuração de Wi-Fi pelo aplicativo via Bluetooth (melhoria futura), suporte a múltiplos vasos/usuários simultâneos.

### 1.3 Definitions, Acronyms, and Abbreviations

| Term | Definition |
|------|------------|
| ADC | Analog-to-Digital Converter — conversor que transforma leitura analógica de sensor em valor digital |
| API | Application Programming Interface |
| Broker MQTT | Serviço intermediário que recebe mensagens publicadas e as distribui aos assinantes de um tópico |
| DHT22 | Sensor digital de temperatura e umidade do ar |
| EMQX Cloud | Broker MQTT gerenciado na nuvem, usado no projeto (ADR-014) |
| Firestore | Banco de dados de documentos do Firebase, usado para sincronizar dados em tempo real com o app |
| Function calling | Recurso em que o LLM devolve um pedido de ação estruturado (ex.: agendar rega) em vez de texto livre; quem executa é o backend |
| Histerese | Margem de segurança que evita ligar/desligar repetidamente a bomba quando o valor oscila perto do limiar |
| Last Will (MQTT) | Mensagem publicada automaticamente pelo broker quando um cliente se desconecta inesperadamente |
| LLM | Large Language Model — modelo de linguagem usado pelo assistente de voz |
| MQTT | Message Queuing Telemetry Transport — protocolo leve de publicação/assinatura usado para IoT |
| Provisionamento de Wi-Fi | Configuração da rede do ESP sem regravar o firmware (por BLE) |
| BLE | Bluetooth Low Energy; o app o usa para enviar a rede Wi-Fi ao vaso |
| OTA | Atualização de firmware pela rede |
| QoS (MQTT) | Quality of Service — nível de garantia de entrega de uma mensagem MQTT (0, 1 ou 2) |
| Redis | Banco de dados em memória; no projeto guarda contexto de conversa e limites de uso |
| Retain (MQTT) | Marca que faz o broker guardar a última mensagem de um tópico e entregá-la a novos assinantes |
| SRS | Software Requirements Specification |
| STT | Speech-to-Text — conversão de voz em texto |
| TTS | Text-to-Speech — conversão de texto em voz |
| UI | User Interface |
| V1 | Primeira fase de entrega: vaso do ESP32-WROOM (sensores, bomba, sincronização de dados, app, BLE e OTA) |
| V2 | Segunda fase de entrega: voz e display no ESP32-S3 |
| YL-69 | Sensor resistivo de umidade do solo, de duas hastes; exige calibração |

### 1.4 References

| Referência | Tipo | Local |
|---|---|---|
| Lista de Componentes de Hardware — GreenSync | Normativo | Documento do grupo (Word) |
| ADR — Decisões — GreenSync | Normativo | `docs/ADR_GreenSync_Decisões.md` |
| Arc42 — SDD — GreenSync | Normativo | `docs/Arc42_GreenSync_SDD.md` |
| Plano de Testes — GreenSync (IEEE 829) | Normativo | `docs/IEEE829_GreenSync_Plano_de_Testes.md` |
| Documentação EMQX Cloud | Informativo | site oficial do provedor |
| Documentação Render | Informativo | site oficial do provedor |
| Documentação Google Gemini API | Informativo | site oficial do provedor |
| Documentação FlutterFire | Informativo | site oficial do Firebase/Flutter |

### 1.5 Document Overview

A Seção 2 dá uma visão geral do produto (contexto, funções, restrições, usuários). A Seção 3 lista os requisitos verificáveis, organizados por interface externa, função, qualidade de serviço, conformidade, implementação e IA. A Seção 4 mapeia como cada requisito será verificado. A Seção 5 traz apêndices de apoio.

## 2. Product Overview

### 2.1 Product Perspective

O GreenSync é um produto novo, desenvolvido do zero como projeto acadêmico. O grupo escolheu um LLM em nuvem, em vez de IA local (ver ADR-004). Não há sistema legado a substituir. O sistema depende de serviços de terceiros: EMQX Cloud (broker MQTT), Firebase (Firestore), Render (hospedagem do backend e do Redis) e Google Gemini (LLM, com entrada de áudio a validar), além do TTS do próprio Gemini. Não há SLA formal contratado. Os serviços são de camada gratuita, com exceção do serviço web pago do Render (ADR-019).

### 2.2 Product Functions

- Medir pH do solo, umidade do solo, temperatura e umidade do ar continuamente
- Acionar automaticamente a bomba d'água quando a umidade do solo estiver abaixo do limiar configurado (regra base, no firmware)
- Publicar as leituras dos sensores via MQTT para a nuvem
- Persistir os dados recebidos no Firebase (leitura atual + histórico)
- Exibir os dados em tempo real e o histórico no aplicativo mobile
- Indicar visualmente o estado da planta em um display OLED no ESP32-S3, alternando entre uma carinha (personalidade da planta) e os dados dos sensores quando o usuário pergunta algo por voz
- Responder perguntas faladas sobre o estado da planta, como se fosse a própria planta, usando um assistente de voz (V2)
- Agendar e executar regas pedidas por voz, com validação no backend e limites no firmware (V2)
- Permitir mudo físico do microfone por botão dedicado
- Permitir configurar o Wi-Fi dos dispositivos sem regravar o firmware (V1)

### 2.3 Product Constraints

- O sistema **deve** usar MQTT como protocolo de comunicação entre o dispositivo de sensores e a nuvem com broker EMQX Cloud (ADR-014)
- O sistema **deve** usar dois microcontroladores: ESP32-WROOM (sensores e bomba) e ESP32-S3 (voz e display) (ADR-016, ADR-023)
- O backend **deve** ser implementado em Python com FastAPI, em processo único, sem Celery (ADR-015)
- O sistema **deve** incluir o Redis; seus usos estão definidos na ADR-015
- O aplicativo **deve** ser implementado em Flutter
- O armazenamento em nuvem **deve** usar Firebase (Firestore)
- O sistema **não deve** depender de armazenamento local (sem microSD) — toda a persistência é em nuvem
- O orçamento de serviços em nuvem **deve** permanecer em camada gratuita ou de baixo custo, com o serviço pago do Render como única exceção prevista — ver ADR-019 e Seção 3.5.7
- A alimentação elétrica **deve** ser única, em 5V, sem uso de bateria (dispositivo estacionário, ligado à tomada)

### 2.4 User Characteristics

| Perfil | Descrição | Frequência de uso | Expectativas |
|---|---|---|---|
| Usuário doméstico | Pessoa cuidando de uma planta em casa | Diária/casual, via app | Ver o estado da planta rapidamente, sem precisar entender os dados técnicos |
| Avaliador | Avalia o projeto | Pontual, na demonstração | Ver o sistema funcionando de ponta a ponta, entender as decisões técnicas tomadas |
| Integrante do grupo (desenvolvimento) | Desenvolve/mantém uma das três frentes | Constante durante o desenvolvimento | Interfaces (MQTT, Firestore, API) bem definidas entre as frentes |

### 2.5 Assumptions and Dependencies

| Assunção/Dependência | Impacto se for falsa |
|---|---|
| O plano serverless do EMQX Cloud atende ao volume de mensagens do projeto | Precisaria de outro plano ou broker, atrasando a integração |
| O Render pago (Starter, 512 MB) comporta API, assinante MQTT e chamadas de IA em um único processo | Seria preciso migrar para serviços separados — ver ADR-019 |
| Existe conectividade Wi-Fi com internet no local da demonstração, e a rede libera a porta 8883 (MQTT/TLS) | O WROOM conectaria ao Wi-Fi, mas o MQTT falharia; alternativa: MQTT sobre WebSocket seguro na 443 ou hotspot do celular |
| O Google Gemini aceita áudio de entrada com qualidade adequada em português, e o TTS do Gemini tem voz adequada (validado em testes de bancada; falta testar voz de celular e ruído de fundo) | Seria preciso um STT separado, ou trocar de provedor (ADR-018) |
| As cotas do plano gratuito do Gemini (inclusive para áudio) atendem ao uso do projeto | O assistente poderia ser limitado ou exigir plano pago |
| A sonda de pH adquirida é confiável o suficiente para leituras consistentes | Maior risco técnico identificado pelo grupo — ver Seção 11 do Arc42 |
| O sensor de solo YL-69 (resistivo) suporta o período de uso do projeto e pode ser calibrado | Leituras derivariam com a corrosão; alternativa: sensor capacitivo |
| O uso definido para o Redis (contexto de conversa e limite de perguntas) atende ao projeto | Seria preciso ajustar o uso (fila, cache ou ambos) |
| O GitHub (Releases) fica acessível ao vaso para o download do OTA | A atualização de firmware falharia; o vaso continuaria funcionando na versão atual |

### 2.6 Apportioning of Requirements

| Área de requisito | Fase | Responsável |
|---|---|---|
| Leitura de sensores, publicação MQTT, execução de comandos de rega (ESP32-WROOM) | V1 | Hardware/firmware |
| Captura e reprodução de áudio, palavra de ativação, display (rosto/dados), botão de mute, envio HTTP (ESP32-S3) | V2 | Hardware/firmware |
| Configuração de Wi-Fi por BLE e atualização OTA (ESP32-WROOM) | V1 | Hardware/firmware, Backend e App |
| Backend (assinatura MQTT, validação, escrita no Firestore) | V1 | Backend |
| Módulo de IA (Gemini, personalidade, pedido de rega por saída estruturada, estado da tela), endpoints de áudio e texto, Redis | V2 | Backend |
| Agendamento e validação de regas, comandos MQTT | V1 e V2 | Backend + Hardware/firmware |
| App — exibição de dados em tempo real, histórico e, se possível, agendamentos | V1 | App/design |

## 3. Requirements

### 3.1 External Interfaces

#### 3.1.1 User Interfaces

- O aplicativo mobile (Flutter) é a única interface visual de acompanhamento do sistema — não há dashboard web.
- O app deve exibir, em tela principal: pH atual, umidade do solo atual, temperatura do ar atual, umidade do ar atual, estado da bomba (ligada/desligada), estado de conexão do dispositivo (online/offline).
- O app deve exibir um gráfico de histórico de pelo menos uma das grandezas monitoradas (ex.: umidade do solo ao longo do tempo).
- O app pode exibir as regas agendadas e permitir cancelá-las, lendo os agendamentos do Firestore (desejável).
- O vaso possui um display OLED no ESP32-S3 mostrando, por padrão, um "rosto" com expressões simples que refletem a personalidade e o estado da planta. Ao ser feita uma pergunta por voz, o display troca temporariamente para mostrar os dados do sensor relevantes (ex.: temperatura, umidade, pH), voltando à carinha ao final da resposta — não é interativo, só informativo (ver REQ-FUNC-016).
- O usuário interage por voz com a planta por meio do microfone e do alto-falante do ESP32-S3, com botão físico de mute e palavra de ativação ("Hi ESP", ADR-032).
- O app configura o Wi-Fi do vaso por BLE quando não há rede salva (REQ-FUNC-013). O vaso anuncia `GreenSync_BLE`; o app envia `ssid,senha` e recebe o estado da conexão.
- O app segue as diretrizes do Material Design (padrão do Flutter); não há requisito formal de acessibilidade.

#### 3.1.2 Hardware Interfaces

- Ver a Lista de Componentes de Hardware (documento separado) para o mapeamento completo de sensores, atuadores e pinagem.
- **ESP32-WROOM:**
  - Sensor de umidade do solo (YL-69, resistivo): interface analógica, em pino do ADC1 (o ADC2 não funciona junto com o Wi-Fi); calibração no firmware.
  - Sensor de pH: interface analógica (ADC1 do ESP32, ou ADC externo opcional ADS1115 via I2C).
  - Sensor de temperatura e umidade do ar (DHT22): interface digital de 1 fio (protocolo próprio do DHT).
  - Bomba d'água: acionada por módulo relé de 2 canais, em nível baixo (GPIO 23), com diodo de roda-livre na bomba. A bomba usa fonte de 5 V separada.
- **ESP32-S3:** microfone INMP441 (I2S), alto-falante via amplificador (I2S), display OLED (SSD1306, interface I2C) mostrando a carinha da planta ou os dados dos sensores (ADR-023), botão físico de mute. A palavra de ativação dispensa o botão de falar.
- O WROOM não tem botão físico de Wi-Fi: o BLE abre sozinho quando não há rede salva ou depois de 4 falhas seguidas de conexão.
- Alimentação: fonte externa única de 5V, dimensionada com folga para os dois ESPs e a bomba (sugestão: 5V/3A); regulador de tensão reduz para 3,3V onde necessário; capacitor de desacoplamento para evitar reinícios quando a bomba liga.

#### 3.1.3 Software Interfaces

| Sistema | Direção | Protocolo | Dados trocados |
|---|---|---|---|
| Broker MQTT (EMQX Cloud) | ESP32-WROOM → Broker | MQTT sobre TLS (porta 8883) | Leituras de sensores e status em JSON |
| Broker MQTT (EMQX Cloud) | Broker → Backend | MQTT sobre TLS (porta 8883) | Leituras e status (assinatura de tópico) |
| Broker MQTT (EMQX Cloud) | Backend → Broker → ESP32-WROOM | MQTT sobre TLS (porta 8883) | Comandos de rega em JSON (tópico `comandos`, **proposta**) |
| Backend | ESP32-S3 ↔ Backend | HTTPS, cabeçalho `X-API-Key` | Áudio da pergunta → áudio da resposta + estado da tela (cabeçalhos `X-Tela` e `X-Dados`, Arc42 8.4) |
| Firebase (Firestore) | Backend → Firestore | SDK Admin (gRPC/HTTPS) | Leitura atual, histórico, status e agendamentos |
| Firebase (Firestore) | Firestore → App | FlutterFire (SDK cliente) | Listeners em tempo real |
| Redis | Backend → Redis | Protocolo Redis (`REDIS_URL`) | Contexto de conversa e contadores de limite |
| API de LLM (nuvem) | Backend → Google Gemini | HTTPS/REST | Áudio ou texto da pergunta + contexto dos sensores → texto da resposta e pedido de ação (saída estruturada, ADR-025) |
| API de TTS (nuvem) | Backend → Google Gemini (TTS) | HTTPS/REST | Texto → áudio |

### 3.2 Functional

- ID: REQ-FUNC-001
- Title: Leitura periódica dos sensores
- Statement: O firmware do ESP32-WROOM shall ler os valores de pH do solo, umidade do solo (calibrada, em %), temperatura do ar e umidade do ar (DHT22) em intervalo regular configurável.
- Rationale: Base de dados para a validação da rega pelo backend e para exibição no app.
- Acceptance Criteria: Os valores são lidos e exibidos via Serial (fase de bancada) em intervalo ≤ definido pelo grupo, sem travar o loop principal. Quando a leitura do DHT22 falha (`NaN`), a leitura não é publicada.
- Verification Method: Demonstration
- More Information: DHT22 em GPIO 27, YL-69 em GPIO 33 (calibrado em %). O pH está simulado na demonstração (ADR-024); o GPIO 34 fica reservado. O DHT22 exige cerca de 2 s entre leituras.

- ID: REQ-FUNC-002
- Title: Execução segura da rega no firmware
- Statement: O firmware do ESP32-WROOM shall acionar a bomba somente ao receber um comando de rega, limitar o tempo contínuo de bomba ligada e ignorar comandos com `id` repetido.
- Rationale: A decisão de regar é do backend (app, voz ou agenda, ADR-031); o firmware garante que nenhum comando, repetido ou exagerado, deixe a bomba ligada além do limite.
- Acceptance Criteria: Um comando com `duracao_s` maior que o limite liga a bomba só até o limite (`BOMBA_MAX_S`, 15 s). Um comando repetido com o mesmo `id` não liga a bomba de novo. Sem comando, a bomba nunca liga, mesmo com o solo seco.
- Verification Method: Test
- More Information: Relé em GPIO 23, nível baixo. O firmware não tem irrigação automática; uma regra local com histerese é uma evolução possível.

- ID: REQ-FUNC-003
- Title: Publicação de dados via MQTT
- Statement: O firmware do ESP32-WROOM shall publicar as leituras dos sensores e o estado da bomba em um tópico MQTT definido, em formato JSON, a cada ciclo de leitura.
- Rationale: Base para a sincronização com a nuvem.
- Acceptance Criteria: Mensagem publicada no broker EMQX é recebida por um cliente assinante de teste, no formato JSON acordado entre hardware/firmware e backend (Arc42, Seção 8.1).
- Verification Method: Test
- More Information: Campos: `ph`, `umidade_solo`, `temperatura_ar`, `bomba_ligada` (obrigatórios); `umidade_ar`, `timestamp` (opcionais).

- ID: REQ-FUNC-004
- Title: Validação e persistência dos dados recebidos
- Statement: O backend shall assinar o(s) tópico(s) MQTT relevante(s), validar cada payload, descartar (com log) os inválidos e gravar os válidos no Firestore, atualizando o documento de leitura atual e adicionando um registro ao histórico.
- Rationale: Permitir consulta em tempo real e histórico no app, sem que um sensor com defeito contamine os dados.
- Acceptance Criteria: Mensagem válida é refletida no Firestore em até 10 segundos; histórico acumula sem sobrescrever leituras anteriores; mensagem fora das faixas ou com JSON inválido é descartada sem derrubar o backend. Se o payload não trouxer `timestamp`, o backend usa a hora do servidor.
- Verification Method: Test

- ID: REQ-FUNC-005
- Title: Exibição de dados em tempo real no app
- Statement: O aplicativo shall exibir os valores atuais de pH, umidade do solo, temperatura do ar, umidade do ar e estado da bomba, atualizando automaticamente quando novos dados chegarem ao Firestore.
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
- Statement: O sistema shall indicar no app quando o dispositivo estiver offline, usando uma mensagem MQTT de "last will" publicada automaticamente pelo broker em caso de desconexão inesperada, e uma mensagem `online` publicada pelo firmware ao conectar.
- Rationale: Evitar que o usuário veja um dado antigo como se fosse atual.
- Acceptance Criteria: Ao desconectar o ESP32-WROOM da energia/rede, o app exibe o status "offline" em até 60 segundos; ao reconectar, volta a "online".
- Verification Method: Test

- ID: REQ-FUNC-008
- Title: Assistente de voz com personalidade da planta (V2)
- Statement: O sistema shall permitir que o usuário faça perguntas faladas sobre o estado da planta e receba uma resposta falada, em primeira pessoa, como se fosse a própria planta, gerada a partir dos dados reais dos sensores.
- Rationale: Diferencial do produto; objetivo central da entrega.
- Acceptance Criteria: Pergunta como "como está minha planta?" resulta em resposta coerente com os dados atuais de pH/umidade/temperatura; se um dado faltar, a resposta diz que não sabe, sem inventar valores. O pH é dito com o valor exato, com a casa decimal (6,5 não vira "uns 7"); temperatura e umidades podem ser arredondadas ao inteiro.
- Verification Method: Demonstration
- More Information: Entrada de áudio direta no Gemini (sem STT separado) validada em testes; TTS pelo Gemini (ADR-018). O estado da planta (ex.: com sede) é calculado pelo backend a partir de limiares configuráveis; o LLM apenas dá a voz. O contexto curto da conversa (últimas 3 trocas, 5 min de validade) fica no Redis e só ajuda a entender referências; os números vêm sempre dos dados atuais. Se o dado estiver velho ou o vaso offline, a planta avisa em vez de falar como se fosse de agora (Arc42, 8.7). Pedidos de rega seguem o REQ-FUNC-011. A troca de tela do display segue o REQ-FUNC-016.

- ID: REQ-FUNC-009
- Title: Mute físico do microfone
- Statement: O sistema shall permitir que o usuário corte fisicamente a captura de áudio por meio de um botão/switch dedicado no ESP32-S3.
- Rationale: Privacidade — o assistente de voz não deve escutar continuamente sem controle do usuário.
- Acceptance Criteria: Com o botão acionado, nenhum áudio é capturado pelo INMP441.
- Verification Method: Inspection


- ID: REQ-FUNC-011
- Title: Rega por comando de voz
- Statement: O sistema shall permitir que o usuário peça por voz uma rega imediata ou agendada (ex.: "regar daqui 1 minuto"), executada pela bomba somente após validação pelo backend.
- Rationale: Dar ao usuário controle direto sobre a rega, sem abrir mão da segurança da atuação.
- Acceptance Criteria: Um pedido válido resulta em bomba ligada na hora marcada, pelo tempo pedido. Um pedido fora dos limites (atraso ou duração máximos, intervalo mínimo entre regas, dispositivo offline) é recusado, e a resposta falada informa a recusa. A bomba nunca permanece ligada além do tempo máximo do firmware.
- Verification Method: Test
- More Information: O LLM apenas devolve um pedido estruturado (saída JSON, ADR-025); nunca aciona a bomba. Comando entregue ao WROOM pelo tópico `greensync/{deviceId}/comandos` (Arc42, 8.1). Limites: atraso máximo de 24 h, duração máxima de 10 s, duração padrão de 5 s, intervalo mínimo de 10 min entre regas, recusa com o vaso offline ou o solo acima de 80%; valores configuráveis, a calibrar com testes reais (Arc42, 8.5); a demonstração usa 15 s de duração e intervalo mínimo de 30 s entre regas (`.env`: `REGA_INTERVALO_MIN_S=30`). Pedido de rega e cancelamento só valem se a fala da pessoa contiver uma palavra do pedido (ADR-025).

- ID: REQ-FUNC-012
- Title: Agendamento persistente de regas
- Statement: O backend shall gravar cada rega agendada no Firestore, com status (`pendente`, `executando`, `concluida`, `cancelada`, `expirada`, `falhou`), recarregar os agendamentos pendentes ao reiniciar e nunca executar a mesma rega duas vezes.
- Rationale: O serviço pode reiniciar antes da hora da rega; perder uma rega é aceitável, duplicá-la não.
- Acceptance Criteria: Ao reiniciar o backend com um agendamento pendente ainda dentro da tolerância, a rega é executada uma vez; fora da tolerância, o agendamento vira `expirada` e não há rega. O status `executando` é gravado antes de publicar o comando.
- Verification Method: Test
- More Information: Tolerância de 5 minutos (`REGA_TOLERANCIA_S`). Um agendamento encontrado como `executando` no reinício vira `falhou` e nunca é repetido. Cancelamento por voz ou pelo app altera o status para `cancelada`.

- ID: REQ-FUNC-013
- Title: Configuração de Wi-Fi por BLE, sem regravar o firmware
- Statement: O ESP32-WROOM shall anunciar o serviço BLE `GreenSync_BLE` quando não houver rede salva ou depois de 4 falhas seguidas de conexão, receber `ssid,senha` do app, notificar o resultado (`conectando`, `ok` ou `erro:senha`, `erro:rede`, `erro:timeout`) e gravar as credenciais na memória (NVS) somente depois de conectar com sucesso.
- Rationale: A equipe alterna entre redes (casa e faculdade); regravar o firmware a cada troca é inviável.
- Acceptance Criteria: O vaso é levado de uma rede para outra e volta a conectar sem regravar o firmware, pelo BLE. Com a senha errada, o vaso notifica `erro:senha` e mantém a rede anterior.
- Verification Method: Demonstration
- More Information: Ver ADR-029. Serviço `4fafc201-1fb5-459e-8fcc-c5c9c331914b`, característica `beb5483e-36e1-4688-b7f5-ea07361b26a8`. A senha trafega sem criptografia no BLE (Arc42, 8.3). Hotspot do celular é o plano B.

- ID: REQ-FUNC-014
- Title: Endpoint de áudio autenticado
- Statement: O backend shall receber o áudio da pergunta do ESP32-S3 por HTTP somente com uma `X-API-Key` válida e devolver o áudio da resposta.
- Rationale: Impedir que terceiros consumam a cota do LLM; manter o áudio fora do MQTT (ADR-017).
- Acceptance Criteria: Requisição sem chave ou com chave inválida é recusada; com chave válida, retorna a resposta em áudio.
- Verification Method: Test
- More Information: Contrato definido no Arc42, Seção 8.4: entrada em WAV 16 kHz, 16 bits, mono (até 15 s e 1 MB), com `X-API-Key` e `X-Device-Id`; resposta em WAV (24 kHz por padrão) na mesma requisição, com `X-Tela` e `X-Dados`.

- ID: REQ-FUNC-015
- Title: Limite de perguntas por chave de API
- Statement: O backend shall limitar o número de perguntas aceitas por chave de API em uma janela de tempo, usando o Redis.
- Rationale: Proteger a cota gratuita do LLM e evitar uso abusivo.
- Acceptance Criteria: Excedido o limite, novas perguntas são recusadas até a janela liberar.
- Verification Method: Test
- More Information: 10 perguntas por janela de 60 s por chave de API (configurável); `/perguntar` e `/audio` compartilham o limite; excedido, a resposta é 429 com `Retry-After`; se o Redis cair, a pergunta passa (Arc42, 8.9).

- ID: REQ-FUNC-016
- Title: Display com alternância entre carinha e dados dos sensores
- Statement: O ESP32-S3 shall exibir, por padrão, uma carinha representando a personalidade da planta em seu display OLED, e trocar temporariamente para exibir os dados do sensor (pH, umidade do solo, temperatura e umidade do ar) quando o usuário fizer uma pergunta por voz, retornando à carinha ao final da resposta.
- Rationale: Reforçar a personalidade do assistente de voz e dar suporte visual à resposta falada, sem exigir que o usuário leia os dados só pelo app.
- Acceptance Criteria: Em repouso, o display mostra a carinha. Ao final de uma pergunta reconhecida, o display troca para os dados relevantes à pergunta (ou a leitura atual completa) e retorna à carinha após a resposta falada terminar (ou após um tempo configurável).
- Verification Method: Demonstration
- More Information: Quem decide o que exibir é o backend (módulo `ai/`), devolvido junto com o áudio da resposta no `POST /audio` (ver ADR-023 e Arc42, Seção 8.4). O firmware do S3 só executa a troca, sem decidir sozinho quando trocar. Formato definido: cabeçalho `X-Tela` (`rosto` ou `dados`) e cabeçalho `X-Dados` (JSON com `ph`, `solo`, `temp`, `ar` e `atuais`).

- ID: REQ-FUNC-017
- Title: Atualização de firmware pela rede (OTA) com rollback
- Statement: O sistema shall atualizar o firmware do ESP32-WROOM pela rede, a partir de um binário publicado no GitHub Releases, conferir o SHA-256, recusar a atualização com a bomba ligada e voltar sozinho à versão anterior se o firmware novo não se confirmar.
- Rationale: Evita regravar o vaso por cabo a cada correção e protege contra uma versão ruim.
- Acceptance Criteria: Uma versão nova registrada no backend é instalada pelo comando `atualizar`, e o vaso reinicia e publica a nova versão em `fw`. Um binário com hash errado é recusado. Um firmware que não se confirma em 5 minutos, ou que reinicia mais de 3 vezes sem se confirmar, volta à versão anterior. Uma versão ruim pode ser revertida por `/reverter`.
- Verification Method: Test
- More Information: Ver ADR-030 e Arc42, 8.11. Download só por HTTPS de `github.com`. A versão do registro precisa ser igual à `FW_VERSION` compilada.

- ID: REQ-FUNC-018
- Title: Palavra de ativação no ESP32-S3
- Statement: O ESP32-S3 shall detectar a palavra de ativação "Hi ESP" localmente, sem enviar áudio à nuvem antes dela, e só então capturar a pergunta e enviá-la ao backend.
- Rationale: Permitir falar com a planta sem botão e sem que o microfone envie áudio continuamente.
- Acceptance Criteria: Sem a palavra de ativação, nenhuma requisição é enviada a `/audio`. Com ela, a pergunta seguinte é capturada e a resposta é reproduzida.
- Verification Method: Demonstration
- More Information: Ver ADR-032 (ESP-SR, 8 MB de PSRAM do S3). É a última etapa do firmware do S3; o backend mantém `WAKE_WORD_ATIVA` desligado.

### 3.3 Quality of Service

#### 3.3.1 Performance

- A leitura dos sensores não deve bloquear a manutenção da conexão MQTT (uso de lógica não bloqueante em vez de `delay()` no firmware).
- O tempo entre a leitura de um sensor e sua exibição no app deve ser de até 10 s depois da publicação (o intervalo de leitura é de 30 s).
- O tempo entre o fim da pergunta falada e o início da resposta falada tem meta de até 10 s (medido em cerca de 9 s no backend; soma áudio, LLM e TTS).
- O sistema é de baixo volume de dados (um único vaso, poucas leituras por minuto) — não há requisito de throughput elevado.

#### 3.3.2 Security

- A conexão dos ESPs e do backend com o broker MQTT deve usar TLS (porta 8883), nunca a porta não criptografada; o firmware precisa do certificado da CA do broker. Na bancada, a validação do certificado do broker e do download do OTA está desativada (`TLS_INSEGURO`, `OTA_TLS_INSEGURO`) até a CA ser configurada.
- O endpoint de áudio deve exigir `X-API-Key`, com limite de perguntas por chave (REQ-FUNC-014 e REQ-FUNC-015).
- Credenciais do broker MQTT, chave de serviço do Firebase, chave da API do Gemini, `X-API-Key` e URL do Redis não devem ser expostas em repositório de código; ficam em `.env` local (fora do controle de versão) e em variáveis de ambiente no Render. Uma chave exposta deve ser revogada e substituída imediatamente.
- O Firestore opera em modo produção (acesso de clientes negado por padrão); as regras de acesso do app (leitura dos próprios vasos) ainda precisam ser publicadas antes da entrega final.
- Os dados de sensores são ambientais (uma planta), mas o áudio da pergunta é a voz do usuário e é enviado ao provedor de LLM. Recomenda-se que o backend não armazene o áudio, e o mute físico (REQ-FUNC-009) garante o controle do usuário sobre a captura. Requisitos de privacidade formal (ex.: LGPD) são de baixo risco, mas as boas práticas acima devem ser seguidas de qualquer forma.

#### 3.3.3 Reliability

- O sistema deve tolerar perda momentânea de conexão Wi-Fi, retomando a publicação MQTT automaticamente quando a conexão for restabelecida.
- Comandos de rega repetidos (QoS 1) não devem acionar a bomba duas vezes (ver REQ-FUNC-002).
- A bomba nunca deve ficar ligada além de um tempo máximo definido no firmware, independentemente de qualquer comando recebido (REQ-FUNC-002 e REQ-FUNC-011).
- Uma atualização de firmware ruim não deve deixar o vaso inutilizável: o rollback volta à versão anterior (REQ-FUNC-017).
- Os agendamentos de rega devem sobreviver a reinícios do backend (REQ-FUNC-012).
- Uma mensagem inválida não deve derrubar o assinante MQTT do backend (REQ-FUNC-004).
- O sensor de pH é reconhecido pelo grupo como o componente de maior risco de confiabilidade (sondas baratas podem ter calibração inconsistente) — recomenda-se teste isolado do componente antes da integração. O sensor de solo resistivo (YL-69) também se degrada com o tempo.

#### 3.3.4 Availability

- O backend no Render roda como serviço pago e sempre ativo, em instância única (duas instâncias gravariam cada leitura em dobro); o plano gratuito não serve porque "dorme" e o assinante MQTT deixaria de escutar (ADR-019).
- A irrigação automática por umidade não depende da nuvem: continua funcionando com backend, broker ou LLM fora do ar.
- Não há requisito de alta disponibilidade formal (SLA) — o projeto é acadêmico, não um serviço em produção contínua.

#### 3.3.5 Observability

- O backend deve registrar (log) as mensagens MQTT recebidas e as respectivas gravações no Firestore, incluindo mensagens descartadas por validação, para facilitar depuração durante o desenvolvimento.
- O backend deve registrar os pedidos de rega (validação, resultado e execução) e as perguntas recusadas por limite.
- O monitoramento usa os logs do Render e o gráfico de memória do serviço. O backend registra também o progresso do OTA.

### 3.4 Compliance

Não há requisitos regulatórios ou contratuais formais aplicáveis a este projeto acadêmico. Os únicos termos relevantes são os termos de uso dos serviços de terceiros usados (EMQX Cloud, Render, Firebase, Google Gemini, inclusive o TTS), que devem ser respeitados quanto a limites de uso.

### 3.5 Design and Implementation

#### 3.5.1 Installation

- Firmware: gravado nos dois ESPs (WROOM e S3) via PlatformIO, por USB na primeira gravação. Depois disso, o WROOM é atualizado pela rede (OTA, ADR-030) e a rede Wi-Fi é configurada por BLE (ADR-029), sem regravar o firmware.
- Backend: empacotado em imagem Docker (`Dockerfile`); implantado no Render (serviço web pago) a partir do repositório do grupo (deploy automático a partir da branch principal). Localmente, qualquer integrante sobe o backend com `docker compose up`, sem precisar configurar Python/dependências manualmente.
- Ambiente local (`docker-compose.yml`): serviço `backend` (com hot-reload, montando o código local e a chave de serviço do Firebase como volume somente leitura), serviço `mosquitto` (broker MQTT local, para desenvolver sem depender do EMQX Cloud) e serviço `redis` (Redis 7, usado no limite de perguntas). O endereço do broker é configurável por variável de ambiente, alternando entre local e EMQX Cloud.
- App: instalado nos aparelhos de teste via build de desenvolvimento Flutter; a distribuição final é um APK/build local para a demonstração, sem publicação em loja.

#### 3.5.2 Build and Delivery

- Controle de versão via Git/GitHub, em um único repositório (monorepo) com as pastas `firmware/`, `backend/`, `app/` e `docs/`.
- Backend: imagem Docker construída a partir do `Dockerfile` do repositório; deploy automático no Render a cada push na branch principal, usando essa mesma imagem.
- Variáveis sensíveis (credenciais do EMQX, chave de serviço do Firebase, chave do Gemini, `X-API-Key`, URL do Redis) mantidas em `.env` fora do controle de versão, injetadas como variáveis de ambiente tanto no `docker-compose` local quanto no Render.
- Firmware: a primeira gravação é manual. Cada versão do WROOM é publicada como *release* no GitHub (tag `firmware-wroom-vX.Y.Z`) e uma GitHub Action registra versão, URL e SHA-256 no backend (`PUT /firmware/{alvo}`); o vaso é atualizado pelo OTA.

#### 3.5.3 Distribution

Não aplicável em profundidade — o sistema roda em um único dispositivo físico (um vaso), um backend, e os clientes do app. Não há topologia distribuída ou replicação de dados além do que o Firebase já oferece nativamente.

#### 3.5.4 Maintainability

- Separação clara de responsabilidades entre firmware, backend e app, com o contrato MQTT/JSON (WROOM) e o contrato HTTP de áudio (S3) como interfaces estáveis entre hardware e backend.
- Código do backend organizado por módulo (cliente MQTT, validação, integração Firebase, IA, agendamentos e Redis).

#### 3.5.5 Reusability

O backend é desenhado para múltiplos dispositivos no futuro (estrutura `devices/{deviceId}` no Firestore), mesmo que a demonstração acadêmica use apenas um vaso.

#### 3.5.6 Portability

- Os firmwares são específicos do ESP32-WROOM e do ESP32-S3 (não portáveis a outras placas sem adaptação).
- O app em Flutter é multiplataforma (Android/iOS) por natureza da tecnologia escolhida.

#### 3.5.7 Cost

- Os serviços de nuvem devem permanecer em camada gratuita sempre que possível: EMQX Cloud (serverless), Firebase (free tier do Firestore), Google Gemini API (free tier — ver ADR-004) e Redis (Key Value do Render).
- A exceção prevista é o serviço web pago do Render (plano Starter, cerca de US$ 7 por mês em pesquisa de 21/09/2026; os preços mudam e devem ser conferidos antes de contratar), dividido entre os três integrantes — ver ADR-019.
- Custo de hardware é único (compra de componentes), não recorrente.

#### 3.5.8 Deadline

- V1 (vaso do WROOM: sensores, bomba por comando, sincronização de dados, app, configuração de Wi-Fi por BLE e OTA): demonstração em 23/11/2026.
- V2 (voz e display no ESP32-S3): em finalização; o backend de voz já está pronto.

#### 3.5.9 Proof of Concept

- O grupo validou, ou valida, isoladamente: (a) a sonda de pH, por ser o componente de maior risco; (b) a calibração do YL-69 e a leitura do DHT22; (c) o fluxo MQTT → broker → backend, com dados simulados; (d) a leitura/escrita no Firestore a partir do backend; (e) o tratamento do Last Will; (f) o Gemini com um áudio gravado no celular e leituras de sensor simuladas; (g) a porta 8883 na rede da faculdade; (h) a latência da voz.
- Validados no backend em novembro/2026, com dados simulados e o Gemini real: o assistente em texto e em áudio (WAV de pergunta e de resposta geradas), o limite de perguntas com Redis, o tratamento de dado velho e vaso offline e a criação de agendamento no Firestore. Pendentes: voz de celular com ruído, execução da rega no horário com o vaso real e o teste de ponta a ponta com o firmware.
- Validado no WROOM real em novembro/2026: DHT22 e YL-69 reais, relé e bomba, MQTT sobre TLS com o EMQX, Last Will, BLE (testado com nRF Connect) e OTA com SHA-256. O rollback automático ainda não foi exercitado.
- Já validados em ambiente local em 21/09/2026: (c) com o Mosquitto e um publicador de teste (validação de payload e descarte de mensagens inválidas) e (d) gravação da leitura atual e do histórico no Firestore.

#### 3.5.10 Change Management

Processo informal, adequado ao porte do grupo (3 pessoas): mudanças de contrato (tópicos MQTT, esquema JSON, estrutura do Firestore, API de áudio) devem ser comunicadas entre os responsáveis antes de implementadas, já que alteram a interface entre as três frentes de trabalho.

### 3.6 AI/ML

Esta seção se aplica ao assistente de voz (V2). Dado o porte acadêmico do projeto e o uso de uma API de LLM de terceiros hospedada (sem treinamento ou ajuste de modelo próprio), várias subseções do template completo não se aplicam e estão marcadas como tal, em vez de preenchidas artificialmente.

#### 3.6.1 Model Specification

- O modelo é a API do **Google Gemini**, escolhida por oferecer camada gratuita (critério: custo zero) com qualidade adequada em português — ver ADR-004. O Groq fica como plano B (ver ADR-018).
- Escopo do modelo: falar como a própria planta, em primeira pessoa, sobre o estado da planta a partir dos dados reais dos sensores (contexto injetado no prompt), pedir ações de rega por saída estruturada (ADR-025), e indicar o que o display deve mostrar — não é um chatbot de propósito geral.
- A entrada de áudio direta no Gemini (sem STT separado) foi validada em testes; o TTS também é do Gemini.
- Toda a integração fica atrás de duas funções (`responder` para texto e `responder_audio` para voz), para trocar de provedor sem afetar o resto do backend.
- Não há dataset de validação próprio nem versionamento de modelo pelo grupo — a qualidade é a fornecida pelo provedor escolhido.
- O módulo é construído em camadas: texto (`POST /perguntar`), depois áudio gravado no celular, depois o ESP32-S3 real (ver ADR-018).

#### 3.6.2 Data Management

- Os dados enviados ao modelo são a pergunta do usuário (áudio ou texto), as leituras dos sensores (pH, umidade, temperatura), o estado calculado da planta e um contexto curto da conversa, guardado no Redis com expiração.
- O áudio é a voz do usuário; recomenda-se que o backend não o armazene (ver Seção 3.3.2).
- Não há coleta, rotulagem ou treinamento de dataset próprio — não aplicável a este projeto.

#### 3.6.3 Guardrails

- O prompt enviado ao LLM deve restringir o escopo de resposta a perguntas sobre a planta/dados dos sensores, usando apenas os números recebidos; quando um dado faltar, o assistente deve dizer que não sabe, sem inventar valores.
- O LLM nunca aciona atuadores: ele apenas devolve um pedido estruturado (ADR-025), e o backend só aceita o pedido se a fala da pessoa contiver uma palavra de rega (silêncio ou ruído nunca viram rega) e valida atraso e duração máximos, intervalo mínimo entre regas e disponibilidade do dispositivo antes de agendar. A resposta falada reflete o resultado da validação, e o firmware ainda aplica seu próprio tempo máximo de bomba.
- O limite de perguntas por chave de API (REQ-FUNC-015) protege a cota do LLM.
- Não há mecanismo de moderação de conteúdo adicional além do que o provedor de LLM já oferece nativamente — considerado suficiente para o escopo do projeto.

#### 3.6.4 Ethics

Não aplicável em profundidade — o assistente é informativo sobre uma planta e não toma decisões consequentes sobre pessoas, portanto não há requisitos de equidade (fairness) ou explicabilidade formal além de o assistente citar os dados reais que embasam sua resposta. O risco relevante é físico (rega excessiva), tratado pelos limites de atuação da Seção 3.6.3.

#### 3.6.5 Human-in-the-Loop

As respostas são totalmente automatizadas, sem revisão humana antes de cada resposta, dado o baixo risco das informações sobre uma planta. Para ações físicas, a supervisão é feita por regras determinísticas (validação no backend e limite de tempo no firmware), e o usuário pode cancelar uma rega agendada por voz ou pelo app.

#### 3.6.6 Model Lifecycle and Operations

- Não há retreinamento ou versionamento de modelo pelo grupo — a troca de provedor de LLM (se necessária) é uma mudança na função `responder` e na configuração do backend, não uma operação de ciclo de vida de modelo.

## 4. Verification

| Requirement ID | Verification Method | Test/Artifact Link | Status | Evidence |
|----------------|---------------------|---------------------|--------|----------|
| REQ-FUNC-001 | Demonstration | Serial Monitor e dados no Firestore | Verificado no WROOM (DHT22 e YL-69 reais; pH simulado) | Leituras publicadas a cada 30 s e vistas no Firestore, novembro/2026 |
| REQ-FUNC-002 | Test | Comando `regar` publicado no EMQX | Verificado no WROOM (limite de 15 s e `id` repetido ignorado) | Bomba real acionada por comando, novembro/2026 |
| REQ-FUNC-003 | Test | Log do backend | Verificado com o WROOM real | Leituras do firmware recebidas pelo backend via EMQX, novembro/2026 |
| REQ-FUNC-004 | Test | `tests/` (validação e gravação) | Verificado | Testes automatizados; documentos no Firestore, novembro/2026 |
| REQ-FUNC-005 | Demonstration | App | Em andamento (dados em tempo real implementados) | Demonstração com o app |
| REQ-FUNC-006 | Demonstration | App | Em andamento (histórico em gráficos implementado) | Demonstração com o app |
| REQ-FUNC-007 | Test | `tests/test_frescor.py`, `tests/test_estado.py` | Em andamento (backend: status online/offline e frescor dos dados verificados; falta a indicação no app com o vaso real) | Testes automatizados; cenários reais (offline, dado velho, recuperação) com Mosquitto e Firestore, novembro/2026 |
| REQ-FUNC-008 | Demonstration | `tests/test_responder.py`, `tests/test_prompt.py`, `tests/test_contexto.py`, `tests/manual_gemini.py`, `tests/manual_audio.py` | Em andamento (assistente em texto e em áudio funcionando no backend com o Gemini real; falta o S3 e o teste com voz de celular e ruído) | Respostas reais do Gemini e WAVs de resposta gerados nos testes manuais; contexto verificado por testes automatizados e contra um Redis real (5 trocas guardadas, 3 lembradas, prazo de 300 s), novembro/2026 |
| REQ-FUNC-009 | Inspection | Montagem do S3 | Em andamento (hardware do S3 em teste) | |
| REQ-FUNC-011 | Test | `tests/test_regras.py`, `tests/test_servico.py`, `tests/test_agendador.py`, `tests/test_mqtt_comando.py`, `tests/manual_rega.py` | Em andamento (validação, agendamento e publicação do comando verificados por testes automatizados; falta rodar `manual_rega.py` com o Gemini real e executar com o vaso físico) | Testes automatizados; documento de agendamento criado no Firestore real, novembro/2026 |
| REQ-FUNC-012 | Test | `tests/test_agendador.py`, `tests/test_servico.py` | Em andamento (persistência, reivindicação antes de publicar, recarga e expiração no reinício verificadas por testes automatizados; falta confirmar a execução no horário com o Firestore real) | Testes automatizados (inclui reinício sem rega duplicada); documento `pendente` no Firestore real, novembro/2026 |
| REQ-FUNC-013 | Demonstration | nRF Connect e app | Verificado no WROOM com o nRF Connect; app em teste em aparelho Android | Serviço `GreenSync_BLE`, escrita `ssid,senha` e notificações, novembro/2026 |
| REQ-FUNC-014 | Test | `tests/test_rota_audio.py`, `tests/test_audio.py`, `tests/test_voz.py` | Em andamento (endpoint verificado com chave, validação de áudio e voz; falta o cliente no S3) | Chamadas reais ao `POST /audio`: 401 sem chave, 422 com áudio inválido, 200 com WAV de resposta em cerca de 9 s, novembro/2026 |
| REQ-FUNC-015 | Test | `tests/test_limite.py`, `tests/test_rota_perguntar.py`, `tests/test_rota_audio.py` | Verificado no backend | Execução real com Redis: 200, 200, 200, 429, 429 (limite reduzido para o teste); testes automatizados, novembro/2026 |
| REQ-FUNC-016 | Demonstration | `tests/test_tela.py`, `tests/test_rota_audio.py` | Em andamento (backend decide e devolve `X-Tela` e `X-Dados`; falta o display do S3) | Testes automatizados, novembro/2026 |
| REQ-FUNC-017 | Test | `tests/` (rotas e registro de firmware), GitHub Action | Verificado no WROOM, exceto o rollback automático | Atualização com SHA-256 concluída no vaso real, novembro/2026 |
| REQ-FUNC-018 | Demonstration | — | Não iniciado (última etapa do S3) | |

Suíte automatizada do backend: 973 testes (pytest), todos passando em novembro/2026. Para rodar: `docker compose run --rm --no-deps backend python -m pytest tests/ -v`. Os scripts `tests/manual_gemini.py`, `tests/manual_audio.py` e `tests/manual_rega.py` gastam cota do Gemini e por isso não rodam no pytest.

Plano de testes completo (níveis, critérios de aprovação e suspensão, ambiente, responsabilidades): ver o Plano de Testes (IEEE 829).

## 5. Appendixes

- Lista de Componentes de Hardware — GreenSync (documento Word separado, com tabela completa de componentes por grupo e fase V1/V2).
- ADR — Decisões — GreenSync (registro das decisões arquiteturais tomadas, ver arquivo próprio).
- Arc42 — SDD — GreenSync (documento de arquitetura de software, ver arquivo próprio).
- Plano de Testes — GreenSync (formato IEEE 829, ver arquivo próprio).