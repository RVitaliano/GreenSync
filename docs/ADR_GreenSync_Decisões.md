# ADR — Registro de Decisões Arquiteturais — GreenSync

Cada decisão segue o template de Michael Nygard (Title / Status / Context / Decision / Consequences).

---

# ADR-001 — Uso do ESP32-S3 como microcontrolador principal

## Status
Aceita

## Context
O projeto precisa de um microcontrolador capaz de ler múltiplos sensores, acionar atuadores, exibir informações em um display, e — na V2 — processar áudio para o assistente de voz (captura de microfone e reprodução de áudio via I2S).

## Decision
Usar o ESP32-S3 em vez de variantes anteriores como o ESP32 WROOM-32.

## Consequences
Fica mais fácil integrar microfone/alto-falante via I2S e contar com mais memória disponível para as bibliotecas de rede (Wi-Fi, MQTT) e áudio simultaneamente. Fica mais difícil aproveitar diretamente exemplos de código voltados ao WROOM-32 clássico (como os que a equipe já encontrou prontos), exigindo pequenas adaptações de pinagem e bibliotecas.

---

# ADR-002 — Protocolo de comunicação: MQTT via HiveMQ Cloud

## Status
Aceita

## Context
A comunicação entre o dispositivo e a nuvem precisava ser definida. O professor orientador exigiu o uso de MQTT como parte do conteúdo avaliado na disciplina.

## Decision
Usar MQTT como protocolo de publicação dos dados dos sensores, com o HiveMQ Cloud (camada gratuita) como broker.

## Consequences
Fica mais fácil atender ao requisito da disciplina e lidar com conexões intermitentes (importante para a V2, com GPRS). Fica mais difícil manter uma arquitetura "sem servidor": passa a ser necessário um backend sempre ativo, assinando o broker — introduzindo um componente de infraestrutura adicional (ver ADR-003) que não existiria em uma integração direta ESP32 → Firebase.

---

# ADR-003 — Introdução de um backend (Python + FastAPI) entre o MQTT e o Firebase

## Status
Aceita

## Context
Com a adoção do MQTT (ADR-002), os dados publicados pelo ESP32-S3 precisam ser recebidos por um assinante e gravados no Firebase — o ESP32 não escreve diretamente no Firestore.

## Decision
Implementar um backend em Python com FastAPI, responsável por assinar os tópicos MQTT no HiveMQ e gravar os dados recebidos no Firestore. Hospedar esse backend no Render (camada gratuita) durante o desenvolvimento.

## Consequences
Fica mais fácil centralizar validação e lógica de negócio (ex.: preparar o contexto para o LLM na V2) em um único lugar controlado pelo grupo. Fica mais difícil manter esse serviço sempre ativo gratuitamente — a camada gratuita do Render "dorme" após inatividade, introduzindo latência na primeira resposta após um período ocioso.

---

# ADR-004 — LLM em nuvem (Google Gemini API) em vez de processamento local (NPU dedicado)

## Status
Aceita

## Context
O grupo avaliou usar um módulo de IA local dedicado (inspirado no projeto pessoal do professor orientador, que usa um NPU específico e um modelo pequeno rodando localmente) para o assistente de voz da V2. Optou-se por uma API de LLM em nuvem em vez de processamento local, restando definir qual provedor usar — o critério adotado foi custo zero (camada gratuita) com qualidade adequada em português.

## Decision
Usar a API do **Google Gemini** como LLM do assistente de voz, por oferecer camada gratuita suficiente para o volume de uso do projeto e boa qualidade de resposta em português, eliminando a necessidade de processamento local dedicado.

## Consequences
Fica mais fácil implementar com qualidade de resposta melhor e sem depender de hardware adicional específico e de configuração especializada, além de não haver custo operacional para essa parte do projeto (camada gratuita do Gemini). Fica mais difícil manter a filosofia de privacidade/processamento local que orienta o projeto pessoal do professor — decisão consciente do grupo, validada com ele, de que essa não era uma exigência para o projeto da disciplina. Fica também mais difícil trocar de provedor no futuro caso os limites da camada gratuita do Gemini se tornem insuficientes, exigindo adaptar o módulo de orquestração de IA para outra API.

---

# ADR-005 — Firestore em vez de Realtime Database

## Status
Aceita

## Context
O Firebase oferece dois produtos de banco de dados: Firestore (documentos/coleções) e Realtime Database (árvore JSON única). Era preciso escolher um para armazenar os dados dos sensores.

## Decision
Usar o Firestore, com uma coleção `devices`, documentos por dispositivo, e subcoleção `historico` para os dados ao longo do tempo.

## Consequences
Fica mais fácil escalar para múltiplos dispositivos e tipos de consulta no futuro (filtros, ordenação), e separar "leitura atual" de "histórico" sem penalizar performance. Fica mais difícil para iniciantes em comparação ao modelo mais simples do Realtime Database — mitigado pelo bom suporte do FlutterFire a ambos.

---

# ADR-006 — Flutter para o aplicativo mobile

## Status
Aceita

## Context
O aplicativo precisava ser definido em uma linguagem/framework. Opções consideradas: React Native e Flutter.

## Decision
Usar Flutter, integrado ao Firebase via FlutterFire.

## Consequences
Fica mais fácil aproveitar a integração oficial entre Flutter e Firebase (FlutterFire é mantido pela própria equipe do Firebase/Google), com listeners em tempo real prontos para uso. Fica mais difícil para integrantes do grupo sem experiência prévia em Dart, exigindo curva de aprendizado adicional.

---

# ADR-007 — Remoção da iluminação artificial (LED) do escopo

## Status
Aceita

## Context
O projeto originalmente incluía uma fita de LED grow com controle manual por interruptor físico, para suplementar a luz da planta.

## Decision
Remover o LED e o interruptor físico do escopo do projeto.

## Consequences
Fica mais fácil simplificar a lista de componentes, a montagem física e a fonte de alimentação (não é mais preciso dimensionar corrente para o LED). Fica mais difícil oferecer suplementação de luz à planta nesta fase — mitigado por não ser um requisito central do projeto atual.

---

# ADR-008 — Sensor de temperatura DS18B20 em vez de DHT22

## Status
Aceita

## Context
O sensor DHT22 mede temperatura e umidade do ar. O grupo decidiu que a umidade do ar não é necessária para o escopo atual, apenas a temperatura.

## Decision
Substituir o DHT22 pelo DS18B20 (sensor digital de temperatura, sem leitura de umidade do ar).

## Consequences
Fica mais fácil simplificar o conjunto de dados monitorados e reduzir uma variável desnecessária no app e no backend. Fica mais difícil obter dados de umidade do ar caso uma fase futura do projeto venha a precisar dessa informação — nesse caso, o componente precisaria ser adicionado novamente.

---

# ADR-009 — Fonte de alimentação única em 5V

## Status
Aceita

## Context
A arquitetura de energia originalmente previa uma fonte de 12V (para acomodar o LED grow, então já removido pela ADR-007) com um conversor step-down para 5V.

## Decision
Usar uma única fonte externa de 5V, alimentando diretamente o ESP32-S3 (via regulador para 3,3V), a bomba d'água e demais periféricos, eliminando o conversor step-down.

## Consequences
Fica mais fácil montar o circuito de energia, com menos componentes e menos pontos de falha. Fica mais difícil usar, no futuro, atuadores que exijam 12V (ex.: uma bomba mais potente) sem reintroduzir um conversor de tensão.

---

# ADR-010 — Ausência de armazenamento local (remoção do módulo microSD)

## Status
Aceita

## Context
O projeto originalmente incluía um módulo leitor de cartão microSD para guardar logs localmente como buffer offline, caso a conexão com a nuvem caísse.

## Decision
Remover o módulo microSD e o cartão da lista de componentes — o sistema não terá nenhuma forma de armazenamento ou funcionamento offline.

## Consequences
Fica mais fácil simplificar o hardware, o firmware e reduzir custo. Fica mais difícil (impossível, na prática) recuperar dados de períodos em que o dispositivo estiver sem conexão com a internet — aceito pelo grupo como trade-off razoável para o escopo acadêmico do projeto.

---

# ADR-011 — Entrega faseada em V1 e V2, com o módulo de IA desenvolvido em paralelo

## Status
Aceita

## Context
O escopo completo do projeto (hardware, irrigação automática, sincronização de dados, assistente de voz integrado, conectividade celular) é amplo para ser entregue de uma vez, e o professor orientador sugeriu uma divisão em etapas. Ao mesmo tempo, o módulo de orquestração de IA (chamadas ao Gemini, montagem de prompt com dados do Firestore) não depende do hardware de voz (microfone, alto-falante, GPRS) para começar a ser construído e testado — só depende do backend e de dados simulados/reais já sincronizados no Firestore.

## Decision
Dividir a entrega em duas fases: **V1** (hardware, sensores, irrigação automática, sincronização de dados via Wi-Fi/MQTT/Firebase, app básico) e **V2** (integração completa do assistente de voz ao hardware — captura de áudio, reprodução de resposta — e substituição do Wi-Fi por conectividade GPRS). O **módulo de orquestração de IA (LLM via Google Gemini) é desenvolvido em paralelo, já durante a V1**, testado com os dados reais que já estarão sendo gravados no Firestore — mas sem estar conectado ao hardware de voz ainda. A integração desse módulo ao firmware (áudio de entrada/saída) só ocorre na V2.

## Consequences
Fica mais fácil priorizar o núcleo funcional do projeto (dados e irrigação) antes de arriscar a complexidade adicional da integração com hardware de voz e da conectividade celular, e ao mesmo tempo adiantar a parte de IA sem depender do cronograma do hardware — reduzindo o risco de a V2 ficar sobrecarregada no fim do projeto. Fica mais difícil demonstrar a experiência completa do produto (assistente de voz falando de verdade) caso a V2 não seja concluída a tempo — risco aceito e mitigado pela priorização da V1 como entrega mínima viável, com a vantagem de que o módulo de IA já estará pronto e testado (via texto/API) quando a V2 começar.

---

# ADR-012 — Empacotamento do backend com Docker (deploy + ambiente local)

## Status
Aceita

## Context
O backend (Python + FastAPI) precisa ser implantado no Render e também ser fácil de rodar localmente pelos integrantes do grupo durante o desenvolvimento, sem que cada um precise configurar manualmente o ambiente Python e as dependências.

## Decision
Empacotar o backend em uma imagem Docker (Dockerfile), usada tanto para o deploy no Render quanto para o desenvolvimento local via `docker-compose`. O `docker-compose.yml` local inclui também um broker MQTT (Eclipse Mosquitto) opcional, para testes sem depender do cluster do HiveMQ Cloud durante o desenvolvimento.

## Consequences
Fica mais fácil garantir que o ambiente de desenvolvimento é idêntico ao de produção, e que qualquer integrante do grupo sobe o backend localmente com um único comando (`docker compose up`). Fica mais difícil (exige atenção extra) manter o `Dockerfile` e o `docker-compose.yml` sincronizados conforme dependências forem adicionadas, e é preciso tomar cuidado para não vazar credenciais do `.env` no controle de versão.
