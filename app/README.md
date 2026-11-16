# GreenSync Mobile App

Aplicativo móvel desenvolvido em Flutter para o ecossistema GreenSync. Permite o monitoramento em tempo real de sensores de estufas/vasos e a configuração de rede de microcontroladores ESP32 via Bluetooth Low Energy (BLE).

## 🛠️ Tecnologias Utilizadas
- **Framework:** Flutter / Dart
- **Banco de Dados:** Firebase Firestore (Realtime e Histórico)
- **Comunicação de Hardware:** FlutterBluePlus (BLE)
- **Gráficos:** fl_chart

## ✨ Funcionalidades
- **Dashboard em Tempo Real:** Leitura síncrona de temperatura do ar, umidade do ar, umidade do solo e pH.
- **Seleção Dinâmica:** Suporte a múltiplos vasos e estufas.
- **Histórico em Gráficos:** Visualização do histórico de leitura dos sensores.
- **Provisionamento BLE:** Envio seguro de credenciais Wi-Fi para o ESP32.

## 🚀 Como Executar o Projeto Localmente
1. Tenha o Flutter SDK instalado (compatível com Android SDK 37+).
2. Na pasta do app, instale as dependências: `flutter pub get`
3. Configure o Firebase localmente: `dart pub global run flutterfire_cli:flutterfire configure`
4. Execute o projeto: `flutter run`