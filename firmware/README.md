# GreenSync — Firmware

Código dos microcontroladores do vaso. O projeto usa **dois ESP32** que pertencem ao mesmo vaso lógico (`deviceId`):

| Placa | Função | Comunicação | Estado |
|---|---|---|---|
| **ESP32-WROOM** | Sensores, bomba, configuração de Wi-Fi e atualização de firmware | MQTT (EMQX Cloud, TLS) e BLE | Versão 2.1.0 funcionando em bancada |
| **Seeed XIAO ESP32-S3** | Voz (microfone, alto-falante) e display | HTTP com o backend | Em desenvolvimento (testes de hardware por módulo) |

Este README cobre principalmente o **ESP32-WROOM** (`firmware_wroom/`) e traz, no fim, o plano do S3.

## Estrutura

```
firmware/
├── README.md
└── firmware_wroom/
    ├── platformio.ini
    ├── include/
    │   ├── config.h.example   ← modelo (vai para o Git)
    │   ├── config.h           ← valores reais (NÃO vai para o Git)
    │   ├── pinos.h            ← pinagem
    │   ├── ota.h
    │   └── ble.h
    └── src/
        ├── main.cpp           ← Wi-Fi, MQTT, sensores, bomba
        ├── ota.cpp            ← atualização de firmware e rollback
        └── ble.cpp            ← configuração de Wi-Fi por Bluetooth
```

## O que o firmware do WROOM faz

- Conecta ao Wi-Fi e ao broker **EMQX Cloud** (porta 8883, TLS).
- Lê os sensores a cada `INTERVALO_MS` (padrão 30 s) e publica a leitura em `greensync/{deviceId}/sensores`.
- Publica `online` (com a versão do firmware, `fw`) ao conectar, com *retain*, e registra o **Last Will** `offline`, para o app saber quando o vaso cai.
- Não publica a leitura se o DHT22 falhar.
- Assina `greensync/{deviceId}/comandos` e executa:
  - **`regar`**: liga a bomba pelo tempo pedido, limitado a `BOMBA_MAX_S` (15 s), e ignora um `id` repetido (o QoS 1 pode entregar a mesma mensagem duas vezes). O firmware não decide regar sozinho: a rega vem sempre de um comando validado pelo backend.
  - **`atualizar`** e **`reverter`**: atualização de firmware (veja abaixo).
- Configura o Wi-Fi por **Bluetooth (BLE)**, sem regravar o firmware.

### Sensores

| Item | Situação |
|---|---|
| Temperatura e umidade do ar (DHT22) | Real |
| Umidade do solo (YL-69) | Real, média de 16 leituras, convertida em % entre `SOLO_SECO` e `SOLO_MOLHADO` |
| pH | Simulado entre 6,0 e 7,0 (ADR-024); o pino 34 fica reservado para a sonda |
| Bomba | Real, acionada por módulo relé de 2 canais (ativo em nível baixo) |

A calibração atual do YL-69 usa ar seco e água (`SOLO_SECO 3300`, `SOLO_MOLHADO 1400`). Para uso na planta, recalibre com o próprio solo (seco e encharcado).

## Pinagem (ESP32-WROOM DevKit)

| Função | GPIO | Observação |
|---|---|---|
| Relé da bomba (IN2) | 23 | Ativo em nível baixo |
| DHT22 (dado) | 27 | |
| Umidade do solo (YL-69, saída analógica) | 33 | ADC1 |
| pH (saída analógica) | 34 | Reservado (ADC1) |
| UART com o S3 (TX / RX) | 17 / 16 | Reservado |
| LED da placa | 2 | |

Os sensores analógicos ficam no **ADC1**, porque o ADC2 não funciona com o Wi-Fi ligado.

### Ligação da bomba

- Módulo relé: VCC em 5 V, GND comum, IN2 no GPIO23.
- Bomba: 5 V da fonte externa → COM do relé 2; NO → fio + da bomba; fio − da bomba → GND da fonte.
- Diodo 1N4007 em paralelo com a bomba, com a faixa no lado +.
- Todos os GND ficam juntos (ESP, módulos e fonte da bomba). Nunca ligue o 5 V da fonte da bomba em pinos do ESP.

## Como configurar e gravar

### 1. Criar o `config.h`

Copie `include/config.h.example` para `include/config.h` e preencha:

| Campo | O que colocar |
|---|---|
| `MQTT_SERVER` / `MQTT_PORT` | Endereço do cluster (painel do EMQX), sem `mqtts://`, e porta `8883` |
| `MQTT_USER` / `MQTT_PASS` | Usuário `esp_vaso` e a senha dele |
| `DEVICE_ID` | Por exemplo, `"vaso-01"` |
| `WIFI_SSID_TESTE` / `WIFI_SENHA_TESTE` | Opcional, só para bancada; vazios, a rede vem pelo BLE |
| `INTERVALO_MS` | Intervalo entre leituras (`30000UL`) |
| `BOMBA_REAL` | `1` com relé e bomba ligados; `0` para só acender o LED |
| `TLS_INSEGURO` | `1` não valida o certificado do broker (veja a seção de TLS) |

> **Nunca** commite o `config.h`. Ele deve estar no `.gitignore`. Se uma senha for parar no repositório, troque-a imediatamente.

### 2. Compilar e gravar (PlatformIO)

```bash
cd firmware/firmware_wroom
pio run -t upload          # grava
pio device monitor         # monitor serial (115200)
```

- Placa: `esp32dev`, framework Arduino, partições `min_spiffs.csv` (dois slots de OTA).
- Feche o monitor antes de gravar, senão o upload acusa "port busy".
- Se o upload parar em `Connecting...`, segure o botão **BOOT** até aparecer a porcentagem.
- A versão do firmware vem de `-DFW_VERSION=\"X.Y.Z\"` no `platformio.ini`.

## Configuração de Wi-Fi por BLE

Quando não há rede salva, ou depois de 4 falhas seguidas de conexão, o vaso abre o BLE sob o nome **GreenSync_BLE**. O app envia `ssid,senha` e acompanha o resultado por notificações.

| Item | Valor |
|---|---|
| Serviço | `4fafc201-1fb5-459e-8fcc-c5c9c331914b` |
| Característica | `beb5483e-36e1-4688-b7f5-ea07361b26a8` (escrita e notificação) |
| Escrita | `ssid,senha` |
| Notificações | `conectando`, `ok` ou `erro:senha`, `erro:rede`, `erro:timeout` |

- As credenciais só são gravadas na memória (NVS) **depois** de uma conexão bem-sucedida; uma senha errada não apaga a rede que já funcionava.
- Não há botão físico para apagar a rede: o BLE reabre sozinho quando a rede falha.
- A senha trafega **sem criptografia** pelo BLE (o pareamento com PIN fica como melhoria futura).

## Atualização de firmware (OTA)

O backend manda o comando `atualizar` e o vaso baixa e aplica o `.bin`, com proteção contra atualização ruim:

1. O vaso só baixa por **HTTPS** de `github.com`, calcula o **SHA-256** enquanto grava e só aceita se o hash bater com o do comando.
2. Recusa a atualização com a bomba ligada.
3. Grava na partição inativa e reinicia nela. Se o firmware novo não se **confirmar** (conectar ao MQTT) em 5 minutos, ou reiniciar mais de 3 vezes sem confirmar, volta sozinho para a versão anterior (*rollback*).
4. Publica o progresso em `greensync/{deviceId}/ota` (`baixando`, `aplicando`, `ok`, `falhou`, `revertido`).

### Publicar uma versão

1. Ajuste `FW_VERSION` no `platformio.ini` e compile (`pio run`).
2. Copie `.pio/build/wroom/firmware.bin` para `greensync-wroom-X.Y.Z.bin`. Use **o mesmo binário** que foi compilado com aquela versão: a versão do registro precisa ser igual à `FW_VERSION` embutida no `.bin`, senão o vaso não se confirma depois de atualizar e volta à versão anterior.
3. Crie um *release* no GitHub com a tag `firmware-wroom-vX.Y.Z` e anexe o `.bin`.
4. A GitHub Action registra a versão no backend (`PUT /firmware/wroom`). Depois, `POST /dispositivos/{id}/atualizar` (ou o OTA automático, se ligado) manda o vaso atualizar.
5. Para voltar, `POST /dispositivos/{id}/reverter` (com a versão anterior no registro) ou `POST /firmware/wroom/retirar`.

## TLS

- `TLS_INSEGURO 1` **não valida o certificado do broker**. Use só em bancada.
- Para validar de verdade: baixe o certificado da CA no painel do EMQX, cole em `EMQX_CA_CERT` no `config.h` e use `TLS_INSEGURO 0` (e `OTA_TLS_INSEGURO 0` para o download do OTA).

## Como testar

1. **Conexão:** no painel do EMQX, em *Monitor → Clients*, deve aparecer `greensync-vaso-01`.
2. **Mensagens:** em *Diagnostics → Online Test*, assine `greensync/#`; as leituras chegam a cada 30 s.
3. **Last Will:** desligue o ESP. O status passa para `offline` em alguns segundos.
4. **Rega:** publique em `greensync/vaso-01/comandos`:
   ```json
   {"acao": "regar", "duracao_s": 3, "id": "t1"}
   ```
   A bomba liga por 3 s. Repetir o mesmo `id` não liga de novo.
5. **Ponta a ponta:** com o backend rodando, a leitura aparece em `devices/vaso-01` no Firestore, e o app mostra os dados.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| Upload: `port busy` | Monitor serial aberto | Fechar o monitor (Ctrl+C) e gravar de novo |
| Upload para em `Connecting...` | Placa fora do modo de gravação | Segurar **BOOT** até aparecer a porcentagem |
| `falhou, rc=-2` | Não alcançou o broker | Conferir `MQTT_SERVER` e `MQTT_PORT`, testar outra rede (porta 8883 bloqueada?) |
| `falhou, rc=4` ou `rc=5` | Usuário ou senha do MQTT incorretos | Conferir `MQTT_USER` e `MQTT_PASS` |
| `DHT22 falhou: leitura NAO publicada` | Fio solto no GPIO27 | Conferir a ligação |
| `umidade_solo` sempre em 0 ou 100 | YL-69 mal ligado ou fora da calibração | Conferir o GPIO33 e os valores de `SOLO_SECO` e `SOLO_MOLHADO` |
| O vaso não aparece no BLE | Já conectado a uma rede, BLE fechado | O BLE só abre sem rede salva ou após 4 falhas de conexão |
| `versao_igual` ao reverter | A versão do registro é a que já está instalada | Registrar a versão anterior antes de reverter |

## ESP32-S3 (voz)

Em desenvolvimento. O S3 captura a pergunta falada, envia ao backend (`POST /audio`) e toca a resposta. Pinos do módulo de teste (Seeed XIAO ESP32-S3):

| Módulo | Sinal | Pino |
|---|---|---|
| Microfone INMP441 | SCK / WS / SD | D2 / D3 / D0 |
| Amplificador MAX98357 | BCLK / LRC / DIN | D4 / D5 / D8 |
| Display OLED (I2C) | SDA / SCL | D6 / D7 |

- O microfone trabalha em 3,3 V (o L/R vai no GND, canal esquerdo); o amplificador aceita 3,3 V a 5 V.
- A ativação por voz será feita no próprio S3 com a palavra "Hi ESP" (ESP-SR), o que exige PSRAM (a placa tem 8 MB) e uma partição de modelo. O backend também aceita uma palavra de ativação opcional (`WAKE_WORD_ATIVA`).
- O WROOM e o S3 conversam por UART (GPIO17/16 do WROOM) para o S3 aproveitar a conexão do vaso.
- Cuidado com o volume nos testes: o alto-falante de 1 W não suporta tom contínuo em volume alto.

## Cuidados

- **Não ligue o USB e a fonte de 5 V ao mesmo tempo** no pino VIN do ESP.
- Não commitar a linha `upload_port` do `platformio.ini`, pois a porta varia de computador para computador.
- A biblioteca `PubSubClient` publica apenas em QoS 0; se for preciso QoS 1 na publicação, migrar para `espMqttClient`.
- Bibliotecas: `PubSubClient`, `ArduinoJson` 7, `NimBLE-Arduino` 2 (exige `-std=gnu++17`), `DHT sensor library` e `Adafruit Unified Sensor`.

## Próximos passos

- [ ] Calibrar o YL-69 no solo real e substituir o pH simulado pela sonda
- [ ] Concluir o firmware do S3 (áudio, display, "Hi ESP") e a ponte UART com o WROOM