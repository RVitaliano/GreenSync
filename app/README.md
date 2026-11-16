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

## 🔌 Backend (rega e atualização de firmware)

Os botões **Regar agora** e **Atualizar** falam com o backend do GreenSync. O endereço e a chave **não ficam no código**: são passados na hora de rodar.

```bash
flutter run --dart-define=API_URL=http://IP_DO_BACKEND:8000 --dart-define=API_KEY=sua_chave
```

- `API_URL`: endereço do backend (ex.: `http://192.168.0.10:8000` na rede local). Se estiver vazia, os botões mostram "Backend não configurado" e não chamam nada.
- `API_KEY`: a mesma `API_KEY` do `.env` do backend (cabeçalho `X-API-Key`). O app **nunca** usa a chave de administrador.
- HTTP sem TLS só funciona em **debug** (`android/app/src/debug/AndroidManifest.xml`). Para release, use um backend com HTTPS.
- Funções do app: **Regar agora** (5 s), selo Online/Offline com a hora da última leitura, tela **Atualização do Firmware** (instalada x disponível por placa, com progresso) e o envio de Wi-Fi por BLE, que agora mostra o resultado quando o firmware do vaso responde.
- Retirar/reverter firmware e cadastrar versões são feitos só pelo administrador, direto no backend.

### Testes

```bash
flutter test
```

`test/mensagens_test.dart`, `test/api_test.dart`, `test/status_vaso_test.dart` e `test/ota_logica_test.dart` são testes unitários puros (sem Firebase nem rede). O `test/widget_test.dart` original é o exemplo do contador do Flutter e não corresponde a este app.
