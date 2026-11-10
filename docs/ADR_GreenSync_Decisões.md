# ADR — Registro de Decisões Arquiteturais — GreenSync

Cada decisão segue o template de Michael Nygard (Title / Status / Context / Decision / Consequences).

> **Atualizado em 03/11/2026** com as ADR-024 a ADR-026 (backend implementado). Atualizações anteriores: 01/10/2026 (ADR-023) e 21/09/2026 (ADR-014 a ADR-022). Decisões antigas que foram revisadas ou substituídas continuam registradas, com o status indicando qual ADR as revisou. Itens marcados **[A DEFINIR]** dependem de confirmação do grupo, do professor ou de teste prático.

---

# ADR-001 — Uso do ESP32-S3 como microcontrolador principal

## Status
Aceita — revisada pela ADR-016 (o ESP32-S3 passa a cuidar da voz; os sensores ficam no ESP32-WROOM)

## Context
O projeto precisa de um microcontrolador capaz de ler múltiplos sensores, acionar atuadores, exibir informações em um display, e — na V2 — processar áudio para o assistente de voz (captura de microfone e reprodução de áudio via I2S).

## Decision
Usar o ESP32-S3 em vez de variantes anteriores como o ESP32 WROOM-32.

## Consequences
Fica mais fácil integrar microfone/alto-falante via I2S e contar com mais memória disponível para as bibliotecas de rede (Wi-Fi, MQTT) e áudio simultaneamente. Fica mais difícil aproveitar diretamente exemplos de código voltados ao WROOM-32 clássico (como os que a equipe já encontrou prontos), exigindo pequenas adaptações de pinagem e bibliotecas.

---

# ADR-002 — Protocolo de comunicação: MQTT via HiveMQ Cloud

## Status
Substituída pela ADR-014 (broker EMQX Cloud)

## Context
A comunicação entre o dispositivo e a nuvem precisava ser definida. O professor orientador exigiu o uso de MQTT como parte do conteúdo avaliado na disciplina.

## Decision
Usar MQTT como protocolo de publicação dos dados dos sensores, com o HiveMQ Cloud (camada gratuita) como broker.

## Consequences
Fica mais fácil atender ao requisito da disciplina e lidar com conexões intermitentes (importante para a V2, com GPRS). Fica mais difícil manter uma arquitetura "sem servidor": passa a ser necessário um backend sempre ativo, assinando o broker — introduzindo um componente de infraestrutura adicional (ver ADR-003) que não existiria em uma integração direta ESP32 → Firebase.

---

# ADR-003 — Introdução de um backend (Python + FastAPI) entre o MQTT e o Firebase

## Status
Aceita — hospedagem revisada pela ADR-019 (serviço pago e sempre ativo)

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
Substituída pela ADR-020 (DHT22 e YL-69)

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
Aceita — revisada pela ADR-018 (o assistente de voz sobe para a V1; a V2 fica com o GPRS)

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

### Atualização (21/09/2026)
O `docker-compose.yml` local passa a incluir o Redis (ADR-015) e a montar a chave de serviço do Firebase (`serviceAccountKey.json`) como volume somente leitura, **fora da imagem**. Não há `supervisord`: o container roda um único processo (uvicorn). Em produção, a mesma imagem roda no Render (ADR-019).

---

# ADR-013 — Concorrência via `async`/`await` em vez de Celery + Redis

## Status
Aceita — parcialmente revisada pela ADR-015 (o Celery continua fora; o Redis entra)

## Context
Ao pesquisar como estruturar o backend, o grupo teve contato com o material do professor orientador, cujo projeto pessoal usa uma stack mais robusta (Django + DRF + Postgres + Redis + Celery + EMQX) para lidar com tarefas em segundo plano e concorrência. Era preciso decidir se o GreenSync deveria seguir uma stack semelhante ou uma abordagem mais simples.

## Decision
Usar apenas os recursos assíncronos nativos do Python (`async`/`await`, FastAPI, `aiomqtt`) para lidar com a concorrência necessária — ouvir o broker MQTT continuamente sem bloquear o restante do backend — em vez de introduzir Celery (execução de tarefas em processos/workers separados) e Redis (fila de mensagens entre esses processos).

## Consequences
Fica mais fácil manter o backend como um único processo, sem infraestrutura adicional para configurar, monitorar e manter (não é preciso subir workers separados nem um serviço de fila). Isso é suficiente porque o volume de dados do projeto é baixo (um único dispositivo, poucas leituras por minuto — ver SRS, seção 3.3.1) e as tarefas envolvidas (assinar MQTT, validar payload, gravar no Firestore) são rápidas o bastante para caber dentro de funções `async` no mesmo processo do FastAPI. Fica mais difícil escalar esse desenho caso o projeto cresça no futuro para múltiplos dispositivos de alto volume ou tarefas pesadas (ex.: processamento de vídeo, treinamento de modelo) — nesse cenário, uma arquitetura com Celery/Redis (ou equivalente) voltaria a fazer sentido, mas está fora do escopo acadêmico atual.

---

# ADR-014 — Broker EMQX Cloud no lugar do HiveMQ Cloud

## Status
Aceita — substitui a ADR-002

## Context
A ADR-002 escolheu o HiveMQ Cloud como broker MQTT. O grupo já usa o EMQX no laboratório da disciplina (repositório separado) e o projeto de referência do professor orientador também usa EMQX. Como o protocolo é o mesmo, a troca de broker não exige mudar a arquitetura.

## Decision
Usar o **EMQX Cloud** (gerenciado) como broker do GreenSync, mantendo tudo o que a ADR-002 definia sobre o protocolo: MQTT sobre TLS (porta 8883), tópicos `greensync/{deviceId}/...`, QoS 1 e Last Will. O desenvolvimento local continua usando o Mosquitto do `docker-compose` (ADR-012).

## Consequences
Fica mais fácil alinhar o projeto ao conteúdo da disciplina e reaproveitar o que o grupo já aprendeu no laboratório; no backend, a troca se resume às variáveis `MQTT_HOST`, `MQTT_USERNAME` e `MQTT_PASSWORD`. Fica mais difícil porque o plano gratuito ou serverless do EMQX Cloud e seus limites ainda não foram conferidos **[A DEFINIR]**, o firmware precisa do certificado da CA para validar o TLS, e é preciso criar usuários e permissões no painel. Não se recomenda hospedar um EMQX próprio no Render: consome muita memória e não há confirmação de que o Render aceite conexões MQTT públicas (TCP puro).

---

# ADR-015 — Redis sem Celery

## Status
Aceita — revisa parcialmente a ADR-013

## Context
A ADR-013 rejeitou Celery e Redis, mantendo o backend em um único processo assíncrono. Depois, o professor pediu a presença do Redis. Uma proposta externa de arquitetura sugeria Celery + Redis + `supervisord` em um único container no Render, mas ela tem problemas: o Redis dentro do container do worker não seria alcançável pelo serviço web (que roda em outro container), o `supervisord` e os múltiplos processos pressionam os 512 MB do plano Starter, e uma fila assíncrona obrigaria o S3 a consultar a resposta depois, em vez de recebê-la na mesma requisição.

## Decision
**O Redis entra; o Celery continua fora.** O backend segue como processo único (uvicorn) com `async`/`await`. Usos do Redis: contexto curto da conversa por dispositivo (com expiração), limite de perguntas por chave de API e, opcionalmente, cache da última leitura. A chamada ao Gemini roda dentro da requisição; as regas agendadas são tarefas `asyncio` persistidas no Firestore (ADR-021); a detecção de "vaso offline" usa o Last Will do MQTT. A URL do Redis vem da variável de ambiente `REDIS_URL`.

## Consequences
Fica mais fácil manter um único processo, gastar pouca memória, atender à exigência do professor e migrar depois para serviços separados, já que a URL do Redis é configurável. Fica mais difícil porque não há fila durável: uma tarefa em andamento se perde num reinício (aceitável, pois o usuário repete a pergunta, e as regas agendadas ficam no Firestore). Se o professor exigir uma fila de verdade, existem alternativas mais leves que o Celery (ex.: `arq` ou `RQ`). A expectativa exata do professor sobre o Redis (fila, cache ou ambos) ainda deve ser confirmada **[A DEFINIR]**.

### Atualização (03/11/2026) — contexto da conversa implementado
O contexto curto passou a existir: lista `ctx:{deviceId}` no Redis com as últimas **3 trocas**, cada pergunta e resposta cortada em **300 caracteres**, expirando em **5 minutos** sem conversa (`CONTEXTO_TURNOS`, `CONTEXTO_MAX_CHARS`, `CONTEXTO_TTL_S`; `CONTEXTO_TURNOS=0` desliga). Guarda só texto, nunca áudio, e o conteúdo não vai para o log. Se o Redis faltar ou cair, o assistente segue sem contexto (mesma política do limite de perguntas). No prompt, o bloco vem depois dos dados reais e manda usar sempre os dados atuais e ignorar instruções que apareçam na conversa. Guarda-se a frase realmente falada, inclusive a confirmação ou recusa da rega escrita pelo backend (ADR-025). Consequência aceita: um pedido de rega que dependa só do contexto ("e daqui a 1 hora?") não é executado, porque a trava da rega exige a palavra de rega na frase atual.

---

# ADR-016 — Dois microcontroladores: ESP32-WROOM (sensores) e ESP32-S3 (voz)

## Status
Aceita — revisa a ADR-001

## Context
A ADR-001 escolheu o ESP32-S3 como único microcontrolador, pensando no áudio da V2. Concentrar sensores, bomba, display, MQTT e áudio em uma só placa aumenta o risco do firmware, e a equipe já tem exemplos prontos de leitura de sensores para o WROOM.

## Decision
Dividir as funções em dois dispositivos do mesmo vaso lógico (`deviceId`, ex.: `vaso-01`):
- **ESP32-WROOM:** sensores (DHT22, YL-69, pH), bomba, publicação MQTT, Last Will e assinatura de comandos de rega.
- **ESP32-S3:** voz — microfone (INMP441), alto-falante, display OLED (rosto/dados, ver ADR-023), mute físico e comunicação HTTP com o backend (ADR-017).

No Firestore, continua havendo um único documento por vaso.

## Consequences
Fica mais fácil separar os riscos — a irrigação não depende do áudio — e aproveitar os exemplos de código do WROOM. Fica mais difícil manter dois firmwares, dois provisionamentos de Wi-Fi (ADR-022) e uma fonte de 5V que aguente os dois ESPs mais a bomba. Na V2, o GPRS deve ficar só no WROOM, porque o áudio do S3 é pesado para dados móveis. A dúvida sobre em qual dos dois ESPs ficaria o display foi resolvida pela ADR-023: fica no S3, junto com a voz.

---

# ADR-017 — Áudio do S3 enviado por HTTP, com chave de API

## Status
Aceita

## Context
Uma pergunta falada de 5 segundos, em 16 kHz e 16 bits, ocupa cerca de 160 KB, enquanto uma leitura de sensor ocupa cerca de 100 bytes. O MQTT é pensado para mensagens pequenas; enviar áudio por ele exigiria cortá-lo em pedaços, numerá-los e remontá-los no backend.

## Decision
O S3 envia o áudio por **HTTP (POST) direto ao backend**, com o cabeçalho `X-API-Key` e a identificação do dispositivo. O MQTT fica exclusivo do WROOM (leituras, status e comandos). A resposta em áudio volta ao S3 na mesma requisição (**proposta**, a confirmar); essa mesma resposta também carrega o estado da tela (rosto ou dados), ver ADR-023.

## Consequences
Fica mais fácil implementar (casa com o FastAPI) e o S3 não precisa conhecer o broker. Fica mais difícil porque o endpoint fica exposto na internet e exige a chave e o limite de perguntas no Redis, o backend precisa estar sempre acordado quando alguém fala (ADR-019), e o formato do áudio (PCM ou WAV, taxa de amostragem), a duração máxima e o formato do campo de estado da tela ainda estão em aberto **[A DEFINIR]**.

---

# ADR-018 — Assistente de voz entregue na V1; Gemini com Groq de reserva

## Status
Aceita — revisa a ADR-011

## Context
A ADR-011 previa a integração da IA ao hardware de voz na V2, com o módulo de IA desenvolvido em paralelo na V1. O grupo decidiu que o assistente de voz deve ser entregue já na V1.

## Decision
O assistente de voz faz parte da **V1**; a V2 fica com a conectividade GPRS. O LLM é o **Google Gemini** (ADR-004). A entrada de áudio direta no Gemini (sem STT separado) é uma **proposta** a validar na documentação atual e em testes; o TTS ainda precisa ser definido **[A DEFINIR]**. O **Groq** fica como plano B (o que exigiria um STT separado). Toda a integração fica atrás de uma função única, `responder(audio, leitura)`, para trocar de provedor mexendo só no interior dela.

A construção segue em camadas: primeiro texto (`POST /perguntar`, testável sem hardware), depois um áudio WAV gravado no celular, e por último o S3 real.

## Consequences
Fica mais fácil demonstrar o produto completo na V1 e reduzir o risco validando a IA em texto antes do hardware. Fica mais difícil porque a V1 fica bem maior (dois firmwares, áudio e IA), o prazo precisa ser reconfirmado com o professor **[A DEFINIR]**, a latência da voz precisa ser medida cedo, e as cotas do plano gratuito do Gemini (inclusive para áudio e voz) ainda não foram conferidas.

### Atualização (03/11/2026)
A entrada de áudio direta no Gemini (sem STT separado) foi validada em testes reais com gravações de teste, e o **TTS também é do Gemini** (Interactions API, modelo principal `gemini-3.8-flash-tts` e reserva `gemini-3.8-flash-lite-tts`), então o Groq e um STT separado não foram necessários. A integração ficou atrás de duas funções, `responder` (texto) e `responder_audio` (voz); a voz fica em `ai/voz.py`. A resiliência (modelo reserva, retry, prazos) está na ADR-026. Pendente: testar com voz de celular e ruído de fundo, e medir a latência com o S3 real. Caso típico medido no backend: cerca de 9 s (3 s para entender e responder, 5 a 6 s para a voz).

---

# ADR-019 — Hospedagem paga no Render, instância única

## Status
Aceita — revisa a ADR-003

## Context
A ADR-003 hospedou o backend no plano gratuito do Render, que "dorme" após inatividade. O assinante MQTT é uma conexão de saída para o broker e não conta como tráfego de entrada, então o serviço dormiria e as leituras se perderiam. Além disso, o assistente de voz precisa de resposta rápida.

## Decision
Usar um **serviço web pago e sempre ativo** no Render (plano Starter, cerca de US$ 7 por mês segundo pesquisa de 21/09/2026, com 512 MB de RAM e 0,5 CPU), **instância única** e sem autoscaling, rodando API, assinante MQTT e chamadas de IA em um só processo. O Redis usa o Key Value do Render (plano gratuito ou pago, a conferir **[A DEFINIR]**). O custo é dividido pela equipe. Se a memória apertar (uso próximo de 512 MB, reinícios por falta de memória) ou a voz ficar lenta por disputa de CPU, migra-se para serviços separados, reaproveitando a mesma imagem Docker.

## Consequences
Fica mais fácil manter o assinante sempre ativo, com custo baixo dividido entre três pessoas, e migrar depois sem reescrever código. Fica mais difícil porque o projeto deixa de ser "só camada gratuita" (ver SRS, Seção 3.5.7), os preços do Render mudam e devem ser conferidos antes de contratar, e uma instância única significa nenhuma redundância — mas duas instâncias gravariam cada leitura em dobro.

---

# ADR-020 — Sensores DHT22 e YL-69

## Status
Aceita — substitui a ADR-008

## Context
A ADR-008 trocou o DHT22 pelo DS18B20 porque a umidade do ar não era necessária. O grupo voltou atrás e definiu o DHT22 para temperatura e umidade do ar, e o YL-69 para a umidade do solo.

## Decision
Usar o **DHT22** (temperatura e umidade do ar) e o **YL-69** (sensor resistivo de umidade do solo). O contrato MQTT ganha o campo opcional `umidade_ar`. O firmware **não publica** uma leitura em que o DHT22 falhe (`NaN`). O YL-69 é calibrado no firmware (leitura seca e molhada; a leitura bruta é invertida) e enviado já em porcentagem, ligado a um pino do ADC1 do WROOM (o ADC2 não funciona junto com o Wi-Fi).

## Consequences
Fica mais fácil ter a umidade do ar como dado extra e usar um sensor digital simples. Fica mais difícil porque o YL-69 corrói com o tempo e exige calibração (alimentá-lo só durante a leitura prolonga a vida; um sensor capacitivo é a alternativa), o DHT22 é lento (cerca de 2 s entre leituras), e o campo novo precisa constar no contrato e no esquema do Firestore.

---

# ADR-021 — Assistente com personalidade e rega por voz, com agenda no Firestore

## Status
Aceita — o item 2 foi ajustado pela ADR-025 (saída estruturada no lugar de function calling); os valores de limite foram definidos na ADR-025 e ainda precisam ser calibrados com testes reais

## Context
O SRS previa um assistente apenas consultivo e excluía o controle de atuadores por voz. O grupo quer que o assistente simule a planta (fala em primeira pessoa, informa os dados dos sensores e diz quando precisa de água) e que seja possível pedir "regar daqui 1 minuto" por voz.

## Decision
1. **Personalidade:** a planta fala em primeira pessoa, curta e usando apenas os números recebidos; se faltar dado, diz que não sabe. O estado da planta (ex.: com sede) é calculado pelo backend a partir de limiares configuráveis, e o Gemini apenas dá a voz. O tom é configurável. Essa mesma personalidade também aparece visualmente na carinha do display do S3 (ADR-023).
2. **Comandos:** a rega é pedida por *function calling*; o Gemini apenas devolve o pedido, e o **backend valida** antes de agir (atraso e duração máximos, intervalo mínimo entre regas, dispositivo online). O Gemini nunca aciona a bomba.
3. **Agenda no Firestore:** cada rega vira um documento em `devices/{deviceId}/agendamentos`, com status (`pendente`, `executando`, `concluida`, `cancelada`, `expirada`, `falhou`); o backend mantém uma tarefa `asyncio` por agendamento e, ao reiniciar, recarrega os `pendente`. Agendamentos vencidos além de uma tolerância (sugestão: 5 minutos) viram `expirada`. O backend marca `executando` **antes** de publicar o comando, para nunca duplicar a rega.
4. **Comando ao dispositivo:** publicação em `greensync/{deviceId}/comandos` (MQTT, QoS 1) **(proposta)**; o firmware aplica um tempo máximo de bomba ligada, independente do que receber.
5. **Irrigação por umidade:** continua no firmware, com histerese, como regra base; voz e agenda são camadas por cima.

## Consequences
Fica mais fácil fazer uma demonstração marcante, e o app pode listar e cancelar regas lendo o Firestore em tempo real. A segurança fica em camadas (backend e firmware). Fica mais difícil porque há um novo canal MQTT (trabalho de firmware), o SRS muda (REQ-FUNC-008 deixa de ser só consultivo e surgem REQ-FUNC-011 e REQ-FUNC-012), é preciso definir a regra de conflito entre irrigação automática e agenda, os limites precisam de calibração real, e agendas longas dependem do backend estar no ar. Perder uma rega num travamento é aceitável; duplicá-la não é.

---

# ADR-022 — Provisionamento de Wi-Fi por portal de configuração

## Status
Aceita

## Context
O grupo alterna entre redes (casa e faculdade, ambas WPA2 comum), e o SRS presumia um Wi-Fi já conhecido pelo firmware. Regravar o ESP a cada troca de rede é inviável.

## Decision
Cada ESP abre, quando não consegue conectar, uma rede própria (ex.: `GreenSync-Setup`) com uma página de configuração (por exemplo, com a biblioteca WiFiManager). As credenciais ficam na memória flash, com suporte a mais de uma rede, e um botão físico mantido pressionado apaga a rede salva. Vale para os **dois** ESPs. O hotspot do celular é o plano B. Configurar a rede pelo aplicativo, via Bluetooth (BLE), fica como melhoria futura.

## Consequences
Fica mais fácil trocar de rede sem regravar o firmware e sem trabalho no app. Fica mais difícil porque são dois firmwares com o mesmo comportamento, as credenciais ficam gravadas na flash (não usar a senha da rede pessoal em repositório público), e redes de faculdade podem bloquear a porta 8883 do MQTT, o que deve ser testado na rede real **[A DEFINIR]**.

---

# ADR-023 — Display no ESP32-S3, alternando entre rosto e dados dos sensores

## Status
Aceita

## Context
A ADR-016 dividiu sensores (WROOM) e voz (S3) em dois microcontroladores, mas deixou em aberto em qual dos dois ficaria o display OLED com o "rosto" da planta. O grupo já havia definido, desde antes da divisão em dois ESPs, que o display mostraria uma carinha simulando a personalidade da planta (ADR-021), e decidiu agora que essa carinha também deve dar lugar aos dados dos sensores quando o usuário pergunta algo por voz.

## Decision
O display OLED fica no **ESP32-S3**, junto com o microfone e o alto-falante — a troca de tela acontece no mesmo momento em que o assistente fala, então faz mais sentido estar no mesmo dispositivo que já processa a voz, em vez de depender de uma segunda via de comunicação (MQTT, que é do WROOM) só para sincronizar a expressão com a resposta falada.

Comportamento: por padrão, o display mostra a carinha (personalidade da planta, ADR-021). Quando o usuário faz uma pergunta por voz, o display troca temporariamente para mostrar os dados do sensor relevantes à pergunta (ex.: temperatura, umidade, pH) e volta à carinha ao final da resposta. Quem decide o que mostrar é o **backend** (módulo `ai/`): a resposta do endpoint de áudio (`POST /audio`, ADR-017) passa a carregar, além do áudio, um campo de estado da tela (ex.: `"tela": "dados"` ou `"tela": "rosto"`). O firmware do S3 só executa a troca — não decide sozinho quando trocar.

## Consequences
Fica mais fácil manter a expressão da planta sincronizada com a resposta falada, já que os dois saem do mesmo dispositivo e da mesma requisição HTTP, sem depender de uma segunda mensagem para coordenar os dois ESPs. Fica mais difícil porque o contrato HTTP de áudio (Seção 8.4 do Arc42) precisa ganhar esse campo extra, e o ESP32-WROOM deixa de ter qualquer indicação visual local — se o WROOM ficar offline mas o S3 continuar ligado, o usuário não percebe isso olhando para o vaso (mitigado pelo app já indicar o status offline, REQ-FUNC-007). O formato exato desse campo deve ser definido junto com o restante do contrato de áudio, ainda em aberto na ADR-017 — **[A DEFINIR]**.

---

# ADR-024 — pH simulado na demonstração

## Status
Aceita — combinada com o professor orientador

## Context
A sonda de pH é o componente de maior risco do projeto: sondas baratas têm calibração inconsistente e se degradam (SRS, Seção 3.3.3; Arc42, Seção 11). O pH alimenta o estado da planta e as respostas do assistente, e o prazo não permite esperar uma sonda confiável para integrar o restante do sistema.

## Decision
Na demonstração, o firmware publica um valor de pH **simulado**, entre 6,0 e 7,0, dentro da faixa que o backend considera adequada (5,5 a 7,5). O contrato continua o mesmo (campo `ph` obrigatório, de 0 a 14) e o backend e o assistente tratam o valor como uma leitura normal. A apresentação deve dizer claramente que o pH é simulado.

## Consequences
Fica mais fácil integrar e demonstrar o sistema completo (app, histórico e assistente falando do pH) sem depender da sonda, e trocar o valor simulado pela sonda real mexe só no firmware, sem mudar contrato, backend nem app. Fica mais difícil porque o alerta `ph_fora_da_faixa` não dispara na demonstração (a menos que o firmware simule um valor fora da faixa de propósito), o assistente fala do pH como se tivesse sido medido, e existe o risco de ele ser apresentado como real. Marcar o dado como simulado no próprio payload (por exemplo, com um campo extra) é uma melhoria possível **[A DEFINIR]**.

---

# ADR-025 — Pedido de rega como saída estruturada, validado e confirmado pelo backend

## Status
Aceita — ajusta o item 2 da ADR-021 (que previa function calling) e define os limites iniciais da rega; os valores ainda precisam de calibração real

## Context
A ADR-021 decidiu que o Gemini apenas devolve o pedido de rega e o backend valida antes de agir. Ao implementar, a entrada em áudio já usava saída JSON com schema (`pergunta_ouvida` e `resposta`). Combinar function calling com saída estruturada na mesma chamada não pôde ser confirmado nos modelos usados, e uma segunda chamada ao modelo só para falar o resultado dobraria a latência e deixaria o LLM livre para prometer algo que o backend recusou.

## Decision
1. **Saída estruturada.** O Gemini devolve, junto da resposta, um campo `acao` com `tipo` (`nenhuma`, `regar` ou `cancelar`), `daqui_a_s` ou `as_hora` ("HH:MM") e `duracao_s` opcional. Texto e áudio usam o mesmo formato, em uma única chamada. O princípio da ADR-021 não muda: o LLM só propõe e nunca aciona a bomba.
2. **O backend decide e fala.** A confirmação ou recusa é uma frase escrita pelo backend, com o horário e a duração realmente agendados, que substitui a frase do modelo. Numa rega "de agora", o backend espera o resultado e, se falhar, a planta diz que não conseguiu.
3. **Travas independentes do LLM.** O pedido só é aceito se a fala da pessoa contiver uma palavra de rega (regar, molhar, irrigar) e, no áudio, se houver transcrição: silêncio ou ruído nunca viram rega. Se a saída do modelo vier torta, nenhuma ação é tomada.
4. **Limites iniciais:** atraso máximo de 24 h; duração máxima de 10 s (padrão 5 s); intervalo mínimo de 10 min entre regas; recusa se o vaso estiver offline ou sem leitura; recusa a rega de agora se o solo estiver acima de 80% ou a bomba já estiver ligada. A reconferência de vaso online e solo encharcado é refeita na hora de regar. Tolerância de 5 min no reinício. Todos configuráveis por variável de ambiente.
5. **Execução sem duplicar.** O backend reivindica o agendamento (`pendente` para `executando`, em transação do Firestore) antes de publicar. No reinício, `pendente` dentro da tolerância executa uma vez, fora dela vira `expirada`, e `executando` vira `falhou` (nunca repete).
6. **Comando ao vaso:** `greensync/{deviceId}/comandos`, QoS 1, **sem retain**, payload `{"acao":"regar","duracao_s":5,"id":"<idAgendamento>"}`. O firmware deve ignorar `id` repetido (o QoS 1 pode entregar duas vezes) e manter o próprio tempo máximo de bomba ligada.

## Consequences
Fica mais fácil garantir a segurança (várias camadas independentes do modelo, uma única chamada ao LLM, frases sempre verdadeiras) e testar tudo com dados simulados. Fica mais difícil porque o prompt carrega regras de extração de horário que precisam ser validadas com o Gemini real (`tests/manual_rega.py`), a confirmação perde um pouco da personalidade da planta por ser uma frase fixa, o firmware precisa assinar o tópico de comandos e tratar `id` repetido, e a precedência entre a irrigação automática por umidade e a rega agendada continua em aberto **[A DEFINIR]**. "Concluída" no backend quer dizer "comando publicado": só o firmware sabe se a bomba girou.

---

# ADR-026 — Dados desatualizados e tolerância a falhas do assistente

## Status
Aceita

## Context
Se o vaso para de enviar leituras ou cai da rede, o último valor gravado no Firestore continua lá, e o assistente poderia falar dele como se fosse o de agora (REQ-FUNC-007). Além disso, o Gemini mostrou-se instável nos testes (timeouts e erros 503 no modelo principal), e o Redis, que guarda o limite de perguntas, pode ficar fora do ar.

## Decision
1. **Frescor no backend.** Cada leitura gravada leva `updated_at` com a hora do servidor e marca o vaso como `online`; o Last Will marca `offline`. O backend classifica os dados como atuais, desatualizados (mais de 120 s sem leitura, ou vaso offline) ou sem dados, e o prompt manda a planta avisar que são os últimos dados e há quanto tempo, sem inventar a causa. Sem `updated_at`, a idade é desconhecida e o dado não é marcado como velho (a menos que esteja offline). O display recebe `atuais` em `X-Dados`.
2. **Modelo reserva.** Há um modelo principal e um reserva, para texto e para voz. Erro 5xx: uma nova tentativa no mesmo modelo; timeout, erro 4xx ou resposta vazia: vai ao reserva; se todos falham, a rota responde 502. Prazos: 8 s (texto), 12 s (entender o áudio), 15 s (voz).
3. **Limite de perguntas "fail-open".** O limite usa janela fixa no Redis (10 por 60 s por chave). Se o Redis não estiver configurado ou cair, a pergunta passa e o erro é logado.
4. **Ordem das checagens e privacidade.** Chave, `device_id` e validação do áudio vêm antes do limite, para requisições inválidas não gastarem o limite nem o Gemini. O que a pessoa falou ou escreveu não vai para o log.

## Consequences
Fica mais fácil manter o assistente honesto e no ar mesmo com o vaso offline, o Gemini lento ou o Redis fora; o app e o display podem avisar que o dado é velho. Fica mais difícil porque o limite de 120 s precisa combinar com o intervalo de publicação do firmware (10 a 30 s), o modelo reserva pode ter qualidade ou latência diferentes, sem Redis o limite deixa de proteger a cota do Gemini (aceito, e há aviso no log de inicialização), e o pior caso de latência soma tentativas (o cliente do S3 deve usar timeout de pelo menos 30 s).