# Plano de Testes — GreenSync (formato IEEE 829)

> Plano mestre enxuto. Não repete o SRS: aponta para ele. Itens marcados **[A DEFINIR]** dependem de confirmação do grupo.

## 1. Identificador do Plano

| Campo | Valor |
|---|---|
| Identificador | PT-GREENSYNC-001 (plano mestre) |
| Versão | 0.2 — 23/11/2026 |
| Autor | Grupo GreenSync (frente de backend) |
| Software relacionado | SRS v0.8, Arc42 v0.8, ADR-001 a ADR-033 |

Histórico: 0.1 (09/11/2026) — primeira versão, com o backend já testado e o firmware, o app e a integração ainda por testar. 0.2 (23/11/2026) — firmware do WROOM testado em bancada (sensores reais, bomba, BLE, OTA); rega somente por comando; novos requisitos REQ-FUNC-017 e REQ-FUNC-018; suíte com 973 testes.

## 2. Referências

- SRS — Requisitos — GreenSync (v0.8): requisitos REQ-FUNC-001 a REQ-FUNC-018 (o REQ-FUNC-010 foi retirado) e a tabela de verificação (Seção 4).
- Arc42 — SDD — GreenSync (v0.8): contratos MQTT (8.1), Firestore (8.2), HTTP de áudio (8.4), limites da rega (8.5), estratégia de testes (8.10), OTA (8.11) e BLE (8.12).
- ADR — Decisões — GreenSync: em especial ADR-024 (pH simulado), ADR-025 (rega), ADR-026 (falhas), ADR-027 (pH exato) e ADR-028 (estratégia de testes).
- `backend/README.md`: como rodar a suíte automatizada.

## 3. Introdução

Este plano define como o GreenSync é testado até a demonstração: o backend (já testado), o vaso do WROOM (V1, testado em bancada), a voz e o display do S3 (V2, em testes de hardware), o aplicativo e a integração de ponta a ponta. O grupo tem três pessoas e uma só frente (backend) com código testável sem hardware, então o plano separa o que se prova com testes automatizados do que só se prova em teste conjunto com o vaso real. 

## 4. Itens de Teste

| Item | Versão / forma | Nível |
|---|---|---|
| Backend (FastAPI, MQTT, Firestore, Redis, IA, agendador) | Branch `main` do repositório, imagem Docker | Unidade, integração e sistema |
| Firmware ESP32-WROOM (sensores, bomba, MQTT, BLE, OTA) | Versão 2.1.0 (tag `firmware-wroom-vX.Y.Z`) | Unidade (bancada) e integração |
| Firmware ESP32-S3 (voz, display, HTTP) | Em desenvolvimento, testado por módulo (display, microfone, alto-falante) | Unidade (bancada) e integração |
| Aplicativo Flutter | Branch `main` do repositório, em aparelho Android | Sistema e aceitação |
| Serviços externos (EMQX Cloud, Firebase, Gemini, Render) | Contas e planos do grupo | Integração |

## 5. Riscos de Software

| Risco | Por quê | Efeito |
|---|---|---|
| Rega indevida ou em excesso | Atuação física: bomba ligada sem pedido, em dobro ou por tempo demais | Alto (segurança do vaso) |
| Sonda de pH pouco confiável | Maior risco técnico do projeto; o pH da demonstração é simulado (ADR-024) | Alto |
| Modelo de linguagem imprevisível | O Gemini pode arredondar o pH, errar horários ou estourar o prazo (503) | Médio |
| Contrato de áudio não validado com o S3 | O contrato MQTT está validado com o WROOM; o cliente HTTP de áudio do S3 ainda não | Alto |
| Atualização de firmware ruim | Um OTA com binário defeituoso pode deixar o vaso fora do ar | Alto |
| Hardware do S3 instável | Montagem em protoboard, com maus contatos | Médio |
| Rede da faculdade bloquear a porta 8883 | MQTT/TLS pode não conectar | Alto |
| Testes com fakes não provam o mundo real | A suíte automatizada não usa Gemini, Firestore, Redis nem broker reais | Médio |
| Credenciais vazarem | `.env` e chave do Firebase | Alto |
| Segurança ainda parcial | TLS sem validação de certificado na bancada, senha do Wi-Fi sem criptografia no BLE, regras do Firestore pendentes | Médio |

## 6. Funcionalidades a Testar (visão do usuário)

Risco: A = alto, M = médio, B = baixo. Detalhes e critérios de cada requisito estão no SRS.

| Funcionalidade | Requisito | Risco |
|---|---|---|
| Execução segura da rega no firmware (tempo máximo, `id` repetido ignorado, sem rega sem comando) | REQ-FUNC-002 | A |
| Atualização OTA com SHA-256 e rollback | REQ-FUNC-017 | A |
| Rega por voz ou texto, com limites | REQ-FUNC-011 | A |
| Agendamento persistente, sem duplicar | REQ-FUNC-012 | A |
| Endpoint de áudio autenticado | REQ-FUNC-014 | A |
| Leitura de sensores e publicação MQTT | REQ-FUNC-001, 003 | M |
| Validação e gravação dos dados no Firestore | REQ-FUNC-004 | M |
| Indicação de vaso offline e dado velho | REQ-FUNC-007 | M |
| Assistente com personalidade, dados reais e pH exato | REQ-FUNC-008 | M |
| Limite de perguntas por chave | REQ-FUNC-015 | M |
| Configuração de Wi-Fi por BLE, sem regravar | REQ-FUNC-013 | M |
| Dados e histórico no app | REQ-FUNC-005, 006 | B |
| Mute do microfone | REQ-FUNC-009 | B |
| Display (carinha e dados) | REQ-FUNC-016 | B |
| Palavra de ativação "Hi ESP" | REQ-FUNC-018 | B |

## 7. Funcionalidades que Não Serão Testadas

| Item | Motivo |
|---|---|
| Carga e desempenho com muitos vasos | Fora do escopo: um vaso, poucas leituras por minuto |
| Acessibilidade e padrão visual do app | Sem requisito formal; segue o Material Design |
| Privacidade formal (LGPD) | Baixo risco; seguem-se só as boas práticas do SRS 3.3.2 |
| Pareamento do BLE com PIN | Melhoria futura; hoje a senha trafega sem criptografia em curta distância |
| Qualidade da voz sintetizada do Gemini | Depende do provedor; avaliada só por escuta nos testes manuais |

## 8. Abordagem

**Níveis**
1. **Unidade e integração do backend (automatizado):** pytest dentro do Docker, com fakes de Gemini, Firestore, Redis e MQTT. Cobre estado e frescor dos dados, prompt, resiliência, áudio e voz, as duas rotas, limite de perguntas, regras da rega, agendador (inclusive reinício sem duplicar), publicação do comando e entrada MQTT.
2. **Sistema do backend (manual):** testes manuais em grupo (subir o ambiente, dados do vaso, perguntas, rega, cancelamento, recusas, reinício, áudio, limite, dado velho e Redis fora), com Mosquitto, Redis, Firestore e Gemini reais.
3. **Bancada do firmware:** cada ESP isolado, com contratos simulados pelo backend (e o backend simulado por `mosquitto_pub` e `curl`).
4. **Integração com o vaso:** testes manuais com o firmware, com o vaso real, o broker de nuvem e o backend.
5. **Ponta a ponta e aceitação:** vaso, broker, backend, Firestore e app juntos, com falhas provocadas (Wi-Fi cai, backend reinicia, Gemini lento), e ensaio da demonstração.

**Ferramentas:** pytest e anyio, Docker Compose, `mosquitto_pub` e `mosquitto_sub`, `curl`, `redis-cli`, console do Firebase, `tests/manual_*.py` (gastam cota do Gemini e ficam fora do pytest).

**Regras do processo**
- A suíte completa roda antes de cada Pull Request; o PR só entra na `main` com a suíte verde.
- Toda trava de segurança corrigida passa pela **prova por reversão**: desfaz-se a correção, confirma-se que um teste falha e restaura-se.
- Os testes não alteram os existentes só para passar.
- Métricas coletadas: testes executados e aprovados (hoje 973 e 973), defeitos achados por nível e itens do roteiro manual aprovados.
- Configurações testadas: local (Docker: backend, Mosquitto, Redis) e nuvem (EMQX Cloud e Render). Hardware: um vaso, dois ESPs.
- Mudança de contrato (tópico, JSON, Firestore, HTTP) é avisada às três frentes e repete os testes dos dois lados.

## 9. Critérios de Aprovação e Reprovação

- **Automatizado:** 100% da suíte passando; nenhum teste ignorado ou enfraquecido para passar.
- **Manual do backend:** todos os itens do roteiro marcados, ou defeitos registrados com decisão do grupo.
- **Integração com o vaso:** o vaso publica no formato combinado e aparece no Firestore; a bomba só liga com comando válido, uma vez por `id`, e desliga pelo timer do firmware; o Last Will marca `offline`.
- **Demonstração:** o checklist "pronto para demonstração" do Guia do Projeto passa de ponta a ponta pelo menos uma vez com os três presentes.
- **Defeitos:** nenhum defeito crítico aberto (rega fora das regras, credencial exposta, backend caindo com entrada inválida). Defeitos menores (texto da fala, ajuste de calibração) podem seguir abertos com registro.

## 10. Critérios de Suspensão e Retomada

| Suspender quando | Retomar quando |
|---|---|
| A suíte automatizada fica vermelha | A causa é corrigida e a suíte volta a passar |
| A bomba liga sem comando, ou fica ligada além do tempo máximo | A bomba é desligada da energia, a causa é achada no firmware ou no backend e o teste de bancada passa sem água |
| Firestore, EMQX ou Gemini fora do ar (ou cota estourada) | O serviço volta, ou o teste é refeito com o Mosquitto local e os fakes |
| Credencial exposta no repositório | A chave é revogada e trocada, e o `git status` e o `.gitignore` são conferidos |
| A rede bloqueia a porta 8883 | Outra rede é usada (hotspot do celular) ou se adota MQTT sobre WebSocket seguro na 443 (decisão do grupo) |

## 11. Entregáveis de Teste

- Este plano e o roteiro interno de testes manuais do grupo.
- A suíte automatizada (`backend/tests/`) e os scripts manuais (`tests/manual_*.py`).
- Simuladores: fakes dos testes, `mosquitto_pub` como "vaso" de mentira, WAVs de teste.
- Relatórios de execução (saída do pytest e do roteiro manual) e logs do backend (`docker compose logs backend`).
- Registro de defeitos: GitHub Issues do repositório.

## 12. Tarefas de Teste Restantes

- Executar o roteiro manual do backend em grupo e registrar os resultados.
- Concluir o teste do firmware do WROOM: o rollback automático do OTA, a validação do certificado TLS e a calibração do YL-69 com solo real (já testados: `comandos`, `id` repetido ignorado, timer da bomba, Last Will, TLS na 8883, BLE e OTA com SHA-256).
- Testar o display, o microfone, o alto-falante e o cliente HTTP de áudio do S3 (timeout de pelo menos 30 s, memória para o WAV de resposta), e por último a palavra de ativação.
- Testar o app: dados em tempo real, histórico, vaso offline e agendamentos.
- Testar voz de celular e ruído de fundo com o Gemini real.
- Conferir as variáveis do Render na demonstração (`REGA_INTERVALO_MIN_S=30`).
- Teste de ponta a ponta e ensaio da demonstração.

## 13. Necessidades de Ambiente

- Computador com Docker (o único meio de rodar o backend e os testes) e o repositório clonado.
- Contas ativas: Firebase, Google AI (Gemini), EMQX Cloud e Render; chave de serviço do Firebase fora do repositório.
- Hardware: um vaso com os dois ESPs, sensores, bomba e fonte de 5V; no primeiro teste da bomba, usar um copo d'água e nunca a planta.
- Dados de teste: leituras simuladas por `mosquitto_pub` (faixas do contrato, valores fora da faixa e valores de pH como 6,5 e 6,7) e WAVs de pergunta.
- Rede: Wi-Fi com internet; testar também a da faculdade (porta 8883).
- Restrição: os scripts `manual_*.py` consomem cota do Gemini; usar com moderação.

## 14. Pessoal e Treinamento

Todos precisam saber subir o ambiente com Docker, usar `mosquitto_pub`/`mosquitto_sub` e ler os logs do backend. A frente de backend orienta as outras duas nesses comandos, com o roteiro interno de testes manuais como guia.

## 15. Responsabilidades

| Atividade | Responsável |
|---|---|
| Suíte automatizada, roteiro manual e este plano | Backend |
| Testes de bancada e de integração do firmware (WROOM e S3) | Hardware/firmware |
| Testes do app | App/design |
| Integração e ensaio da demonstração | Os três, juntos |
| Decisão de seguir (go/no-go) para a demonstração | Os três |
| Aprovação de mudança de contrato | Os três |

## 16. Cronograma

Datas relativas aos marcos de desenvolvimento, para o teste não ser culpado por atraso:

| Marco | Teste que começa |
|---|---|
| Backend na `main` (feito) | Roteiro manual do backend (assim que o grupo se reunir) |
| Firmware publicando no formato combinado | Integração do vaso |
| Deploy do backend no Render (feito) | Teste do backend em nuvem e do cliente do S3 |
| Release do firmware do WROOM publicada | Teste do OTA no vaso real |
| App lendo o Firestore | Ponta a ponta |
| Demonstração (23/11/2026) | Ensaio da demonstração, antes da data |

Se um marco atrasar, o teste que depende dele começa no dia seguinte à entrega, e não em data fixa.

## 17. Riscos do Planejamento e Contingências

| Risco | O que fazer |
|---|---|
| Firmware ou app atrasam | Continuar com dados simulados (`mosquitto_pub`, Firestore manual); a demonstração prioriza a V1 (o vaso do WROOM) |
| Falta de tempo para o teste de ponta a ponta | Cortar itens de risco baixo (display, mute) e manter os de risco alto (bomba, rega, offline) |
| Cota do Gemini acaba | Usar o modelo reserva, reduzir os scripts manuais e testar o resto com fakes |
| Hardware quebra (bomba, sonda) | Ter peça reserva; o pH já é simulado (ADR-024) |
| Mudança de requisito perto da entrega | Atualizar o SRS e os contratos antes e repetir os testes dos dois lados |

## 18. Glossário

| Termo | Definição |
|---|---|
| Fake | Objeto de teste que imita um serviço externo (Gemini, Firestore, Redis, MQTT) |
| Prova por reversão | Desfazer temporariamente uma correção para confirmar que algum teste falha |
| Regressão | Rodar os testes de novo depois de uma mudança, para ver se algo antigo quebrou |
| Go/no-go | Decisão de seguir ou não para a próxima etapa |
| Last Will | Mensagem MQTT que o broker publica quando o vaso cai |
| Histerese | Margem que evita ligar e desligar a bomba repetidamente |