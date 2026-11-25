// Configuração do backend, passada na hora de rodar (nada fica no código):
//   flutter run --dart-define=API_URL=http://IP:8000 --dart-define=API_KEY=...
const String apiUrl = String.fromEnvironment('API_URL');
const String apiKey = String.fromEnvironment('API_KEY');
