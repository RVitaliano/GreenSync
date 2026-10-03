# GreenSync — Firmware

Código dos microcontroladores do vaso. O projeto usa **dois ESP32** que pertencem ao mesmo vaso lógico (`deviceId`):

| Placa | Função | Comunicação | Estado |
|---|---|---|---|
| **ESP32-WROOM** | Sensores, bomba e publicação dos dados | MQTT (EMQX Cloud, TLS) | Versão de teste pronta |
| **ESP32-S3** | Voz (microfone, alto-falante) e display | HTTP com o backend | Não iniciado |

Este README cobre o **ESP32-WROOM** (`firmware_wroom/`).

## Estrutura

```
firmware/
├── README.md
└── firmware_wroom/
    ├── platformio.ini
    ├── include/
    │   ├── config.example.h   ← modelo (vai para o Git)
    │   └── config.h           ← valores reais (NÃO vai para o Git)
    └── src/
        └── main.cpp
```

## O que o firmware faz hoje

- Conecta ao Wi-Fi e ao broker **EMQX Cloud** (porta 8883, TLS).
- Publica uma leitura a cada `INTERVALO_PUBLICACAO_MS` (padrão 30 s).
- Publica `online` ao conectar (com *retain*) e registra o **Last Will** `offline`, para o app saber quando o vaso cai.
- Assina o tópico de comandos e liga o LED da placa (GPIO 2) no lugar da bomba ao receber um pedido de rega.
- Não publica a leitura se o DHT22 falhar.
- Limita a bomba a 10 s por rega e exige 30 s entre regas, qualquer que seja o comando.

### O que ainda é simulado

| Item | Situação |
|---|---|
| Temperatura e umidade do ar (DHT22) | **Real** |
| pH | **Simulado** (`PH_SIMULADO`), sensor ainda não comprado |
| Umidade do solo (YL-69) | **Simulada** (`SOLO_SIMULADO`), sensor ainda não conectado |
| Bomba | **Simulada** pelo LED da placa (GPIO 2), relé e bomba ainda não conectados |
| Irrigação automática por umidade | **Não implementada** (depende do sensor de solo) |

As linhas simuladas estão marcadas com `// SIMULADO` no `main.cpp`.

## Pinagem (ESP32-WROOM DevKit, 30 pinos)

| Função | GPIO | Observação |
|---|---|---|
| DHT22 (dado) | 4 | Em uso |
| Umidade do solo (YL-69, saída analógica) | 34 | Reservado (ADC1) |
| pH (saída analógica) | 35 | Reservado (ADC1) |
| Relé da bomba (IN) | 26 | Reservado |
| LED da placa (simula a bomba) | 2 | Em uso |
| LEDs de status (futuro) | 27 e 14 | Reservados, não usar |

Os sensores analógicos ficam no **ADC1**, porque o ADC2 não funciona com o Wi-Fi ligado.

## Como configurar e gravar

### 1. Criar o projeto no PlatformIO

- Board: **Espressif ESP32 Dev Module** (`esp32dev`)
- Framework: **Arduino**
- Pasta: `firmware/firmware_wroom/`

A primeira compilação baixa o toolchain do ESP32 (mais de 1 GB) e pode demorar bastante.

### 2. Criar o `config.h`

Copie `include/config.example.h` para `include/config.h` (mesma pasta) e preencha:

| Campo | O que colocar |
|---|---|
| `WIFI_SSID` / `WIFI_PASSWORD` | Wi-Fi de **2,4 GHz** |
| `MQTT_SERVER` | Endereço do cluster (painel do EMQX, *Deployment Overview*), sem `mqtts://` e sem porta |
| `MQTT_PORT` | `8883` |
| `MQTT_USER` / `MQTT_PASS` | Usuário `esp_vaso` e a senha dele |
| `DEVICE_ID` | `"vaso-teste"` durante os testes |
| `MQTT_TLS_INSEGURO` | `1` no primeiro teste (veja a seção de TLS) |

> **Nunca** commite o `config.h`. Ele deve estar no `.gitignore`. Se uma senha for parar no repositório, troque-a imediatamente.

### 3. Compilar e gravar

1. **Build** (`Ctrl+Alt+B`) para conferir se compila.
2. **Upload** (`Ctrl+Alt+U`) com o ESP32 conectado por USB.
3. **Serial Monitor** (`Ctrl+Alt+S`), 115200 baud.

Saída esperada:

```
Conectando ao Wi-Fi....
Wi-Fi conectado!
Conectando ao broker MQTT... conectado!
Publicado em greensync/vaso-teste/sensores: {"ph":7.0,"umidade_solo":50,...}
```

## Contrato MQTT (resumo)

Detalhes completos em `docs/Arc42_GreenSync_SDD.md`, Seção 8.1. Qualquer mudança deve ser combinada com o backend antes.

| Tópico | Direção | Payload |
|---|---|---|
| `greensync/{deviceId}/sensores` | ESP → backend | Leitura (abaixo) |
| `greensync/{deviceId}/status` | ESP → backend (retain) | `{"status": "online"}` ou `{"status": "offline"}` (Last Will) |
| `greensync/{deviceId}/comandos` | backend → ESP | `{"acao": "regar", "duracao_s": 5, "id": "abc"}` |

Leitura:

```json
{
  "ph": 7.0,
  "umidade_solo": 50,
  "temperatura_ar": 24.1,
  "umidade_ar": 58,
  "bomba_ligada": false
}
```

- Obrigatórios: `ph` (0 a 14), `umidade_solo` (0 a 100, em %), `temperatura_ar` (-40 a 80), `bomba_ligada`.
- Opcionais: `umidade_ar` (0 a 100) e `timestamp` (Unix, em segundos). Sem relógio sincronizado, o firmware omite o `timestamp` e o backend usa a hora do servidor.

## TLS

- `MQTT_TLS_INSEGURO 1` **não valida o certificado do broker**. Use só nos primeiros testes.
- Para validar de verdade: baixe o certificado da CA no painel do EMQX, cole em `EMQX_CA_CERT` no `config.h` e mude para `MQTT_TLS_INSEGURO 0`.

## Como testar

1. **Conexão:** no painel do EMQX, em *Monitor → Clients*, deve aparecer `greensync-vaso-teste`.
2. **Mensagens:** em *Diagnostics → Online Test*, assine `greensync/#`. As leituras chegam a cada 30 s.
3. **Last Will:** desligue o ESP da energia. O status deve passar para `offline` depois que o broker perceber a queda (pode levar alguns segundos).
4. **Comando de rega:** publique em `greensync/vaso-teste/comandos`:
   ```json
   {"acao": "regar", "duracao_s": 3, "id": "t1"}
   ```
   O LED da placa acende por 3 s.
5. **Ponta a ponta:** com o backend rodando, a leitura deve aparecer em `devices/vaso-teste` no Firestore.

## Problemas comuns

| Sintoma | Causa provável | O que fazer |
|---|---|---|
| `Please specify upload_port` | ESP não detectado na USB | Trocar o cabo (precisa ser de dados), instalar o driver **CP210x** (Windows), conferir a porta COM |
| Upload para em `Connecting...` | Placa não entrou em modo de gravação | Segurar o botão **BOOT** até aparecer a porcentagem |
| Fica em `Conectando ao Wi-Fi....` | Rede errada, senha errada ou rede de 5 GHz | Usar Wi-Fi de 2,4 GHz e conferir SSID e senha |
| `falhou, rc=-2` | Não alcançou o broker | Conferir `MQTT_SERVER` e `MQTT_PORT`, testar outra rede |
| `falhou, rc=4` ou `rc=5` | Usuário ou senha do MQTT incorretos | Conferir `MQTT_USER` e `MQTT_PASS` |
| `DHT22 falhou: leitura NAO publicada` | Fio solto ou sensor mal ligado | Conferir a ligação no GPIO 4 |
| `PermissionError` no `packages.lock` (Windows) | Processo do PlatformIO pendurado ou antivírus | Reiniciar, apagar o `packages.lock`, excluir `.platformio` do antivírus |
| `config.h: No such file or directory` | Arquivo ausente ou com nome errado | Criar `include/config.h` (cuidado com `config.h.txt`) |

## Cuidados

- **Não ligue o USB e a fonte de 5 V ao mesmo tempo** na bancada, até conferir se a placa tem diodo de proteção.
- Não commitar a linha `upload_port = COM3` do `platformio.ini`, pois a porta varia de computador para computador.
- Biblioteca de MQTT: o `PubSubClient` publica apenas em QoS 0. Se for preciso QoS 1 na publicação, migrar para `espMqttClient`.

## Próximos passos

- [ ] Validar o TLS com o certificado da CA (`MQTT_TLS_INSEGURO 0`)
- [ ] Ligar o YL-69 e implementar a calibração (leitura seca e molhada, convertida para %)
- [ ] Escolher e comprar o sensor de pH, e implementar a conversão
- [ ] Ligar o relé e a bomba, e implementar a irrigação automática com histerese
- [ ] Provisionamento de Wi-Fi por portal (ADR-022), para trocar de rede sem regravar
- [ ] Firmware do ESP32-S3 (voz e display)
