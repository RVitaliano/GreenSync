# GreenSync Mobile App

Aplicativo móvel desenvolvido em Flutter para o ecossistema GreenSync. Permite o monitoramento em tempo real dos dados do vaso, o pedido de rega e a configuração da rede Wi-Fi do ESP32 via Bluetooth Low Energy (BLE).

## 🛠️ Tecnologias Utilizadas
- **Framework:** Flutter / Dart
- **Banco de Dados:** Firebase Firestore (leitura atual e histórico, em tempo real)
- **Comunicação de Hardware:** FlutterBluePlus (BLE)
- **Gráficos:** fl_chart

## ✨ Funcionalidades
- **Dashboard em tempo real:** temperatura do ar, umidade do ar, umidade do solo, pH e estado da bomba, atualizados por listeners do Firestore, sem recarregar a tela.
- **Status do vaso:** indica online ou offline, para o usuário não confundir um dado antigo com um dado atual.
- **Seleção dinâmica:** suporte a múltiplos vasos.
- **Histórico em gráficos:** evolução das leituras dos sensores ao longo do tempo.
- **Provisionamento BLE:** envio das credenciais Wi-Fi para o ESP32 e acompanhamento do resultado da conexão.

## 📶 Configuração de Wi-Fi por BLE

O vaso aparece como **`GreenSync_BLE`** quando não tem rede salva ou depois de falhas seguidas de conexão.

| Item | Valor |
|---|---|
| Serviço | `4fafc201-1fb5-459e-8fcc-c5c9c331914b` |
| Característica | `beb5483e-36e1-4688-b7f5-ea07361b26a8` (escrita e notificação) |
| Escrita | `ssid,senha` |
| Notificações | `conectando`, `ok` ou `erro:senha`, `erro:rede`, `erro:timeout` |

Passo a passo no app:
1. Ligue o Bluetooth e conceda as permissões de Bluetooth (e de localização, em versões antigas do Android).
2. Procure o dispositivo `GreenSync_BLE` e conecte.
3. Informe a rede (2,4 GHz) e a senha. O vaso só salva a rede depois de conectar com sucesso; com a senha errada, ele avisa `erro:senha` e mantém a rede anterior.

> **Segurança:** a senha trafega sem criptografia pelo BLE, e a conexão é curta e feita ao lado do vaso. O pareamento com PIN fica como melhoria futura.

## 🚀 Como Executar o Projeto Localmente
1. Tenha o Flutter SDK instalado (compatível com Android SDK 37+).
2. Na pasta do app, instale as dependências: `flutter pub get`
3. Configure o Firebase localmente: `dart pub global run flutterfire_cli:flutterfire configure`
4. Execute o projeto: `flutter run`

O BLE só funciona em aparelho físico (o emulador não tem Bluetooth).