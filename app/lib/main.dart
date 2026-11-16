import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:fl_chart/fl_chart.dart';
import 'firebase_options.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp(
    options: DefaultFirebaseOptions.currentPlatform,
  );
  runApp(const GreenSyncApp());
}

class GreenSyncApp extends StatelessWidget {
  const GreenSyncApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'GreenSync',
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.green),
        useMaterial3: true,
      ),
      home: const DashboardScreen(),
    );
  }
}

class DashboardScreen extends StatefulWidget {
  const DashboardScreen({super.key});

  @override
  State<DashboardScreen> createState() => _DashboardScreenState();
}

class _DashboardScreenState extends State<DashboardScreen> {
  String statusBluetooth = "Desconectado";
  final TextEditingController ssidController = TextEditingController();
  final TextEditingController passwordController = TextEditingController();

  String? dispositivoSelecionado; 

  final String serviceUuid = "4fafc201-1fb5-459e-8fcc-c5c9c331914b";
  final String charUuid = "beb5483e-36e1-4688-b7f5-ea07361b26a8";

  Future<void> pedirPermissoes() async {
    await [
      Permission.bluetoothScan,
      Permission.bluetoothConnect,
      Permission.location,
    ].request();
  }

  void enviarWiFiViaBLE() async {
    if (ssidController.text.isEmpty || passwordController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Preencha o SSID e a Senha!')),
      );
      return;
    }

    await pedirPermissoes();
    setState(() { statusBluetooth = "Procurando ESP32..."; });
    await FlutterBluePlus.startScan(timeout: const Duration(seconds: 5));

    FlutterBluePlus.scanResults.listen((resultados) async {
      for (ScanResult r in resultados) {
        if (r.device.platformName == "GreenSync_BLE") {
          FlutterBluePlus.stopScan();
          setState(() { statusBluetooth = "Conectando ao ESP32..."; });

          try {
            await r.device.connect(license: License.nonprofit);
            setState(() { statusBluetooth = "Enviando credenciais..."; });

            List<BluetoothService> services = await r.device.discoverServices();
            for (BluetoothService service in services) {
              if (service.uuid.toString() == serviceUuid) {
                for (BluetoothCharacteristic characteristic in service.characteristics) {
                  if (characteristic.uuid.toString() == charUuid) {
                    String wifiData = "${ssidController.text},${passwordController.text}";
                    await characteristic.write(utf8.encode(wifiData));
                    
                    setState(() { statusBluetooth = "Credenciais enviadas!"; });
                    await Future.delayed(const Duration(seconds: 2));
                    await r.device.disconnect();
                    return;
                  }
                }
              }
            }
          } catch (e) {
            setState(() { statusBluetooth = "Erro na conexão."; });
          }
        }
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('GreenSync Dashboard', style: TextStyle(color: Colors.white)),
        backgroundColor: Colors.green[700],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            const Text("Selecione o Vaso/Estufa", style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Card(
              elevation: 2,
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 4.0),
                child: StreamBuilder<QuerySnapshot>(
                  stream: FirebaseFirestore.instance.collection('devices').snapshots(),
                  builder: (context, snapshot) {
                    if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());
                    var documentos = snapshot.data!.docs;
                    if (documentos.isEmpty) return const Padding(padding: EdgeInsets.all(12.0), child: Text("Nenhum dispositivo encontrado."));

                    bool idExiste = documentos.any((doc) => doc.id == dispositivoSelecionado);
                    if (!idExiste) dispositivoSelecionado = documentos.first.id;

                    return DropdownButtonHideUnderline(
                      child: DropdownButton<String>(
                        isExpanded: true,
                        value: dispositivoSelecionado,
                        icon: const Icon(Icons.arrow_drop_down, color: Colors.green),
                        items: documentos.map((doc) {
                          return DropdownMenuItem<String>(
                            value: doc.id,
                            child: Text(doc.id.toUpperCase(), style: const TextStyle(fontWeight: FontWeight.bold)),
                          );
                        }).toList(),
                        onChanged: (novoValor) => setState(() => dispositivoSelecionado = novoValor),
                      ),
                    );
                  },
                ),
              ),
            ),
            const SizedBox(height: 20),

            if (dispositivoSelecionado != null) ...[
              const Text("Leitura Atual", style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              StreamBuilder<DocumentSnapshot>(
                stream: FirebaseFirestore.instance.collection('devices').doc(dispositivoSelecionado).snapshots(),
                builder: (context, snapshot) {
                  if (snapshot.connectionState == ConnectionState.waiting) return const Center(child: CircularProgressIndicator());
                  if (snapshot.hasError || !snapshot.hasData || !snapshot.data!.exists) return const Card(child: Padding(padding: EdgeInsets.all(16.0), child: Text("Aguardando dados...")));

                  var dados = snapshot.data!.data() as Map<String, dynamic>;
                  var leituraAtual = dados['leitura_atual'] as Map<String, dynamic>? ?? {};

                  return Card(
                    elevation: 3,
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                            children: [
                              _buildInfoSensor(Icons.thermostat, "Temp. Ar", "${leituraAtual['temperatura_ar'] ?? '--'}°C", Colors.orange),
                              _buildInfoSensor(Icons.water_drop, "Umid. Ar", "${leituraAtual['umidade_ar'] ?? '--'}%", Colors.blue),
                            ],
                          ),
                          const SizedBox(height: 16),
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
                            children: [
                              _buildInfoSensor(Icons.grass, "Umid. Solo", "${leituraAtual['umidade_solo'] ?? '--'}%", Colors.brown),
                              _buildInfoSensor(Icons.science, "pH", "${leituraAtual['ph'] ?? '--'}", Colors.purple),
                            ],
                          ),
                          const Divider(height: 20),
                          
                          // NOVO BOTÃO PARA VER O HISTÓRICO
                          ElevatedButton.icon(
                            onPressed: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (context) => HistoricoScreen(deviceId: dispositivoSelecionado!)),
                              );
                            },
                            icon: const Icon(Icons.show_chart),
                            label: const Text("Ver Gráficos do Histórico"),
                            style: ElevatedButton.styleFrom(
                              backgroundColor: Colors.green[600],
                              foregroundColor: Colors.white,
                              minimumSize: const Size(double.infinity, 40),
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ],

            const SizedBox(height: 30),
            const Text("Configurar Wi-Fi (BLE)", style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Card(
              elevation: 3,
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Column(
                  children: [
                    TextField(controller: ssidController, decoration: const InputDecoration(labelText: "Nome da Rede (SSID)", prefixIcon: Icon(Icons.wifi))),
                    const SizedBox(height: 10),
                    TextField(controller: passwordController, obscureText: true, decoration: const InputDecoration(labelText: "Senha do Wi-Fi", prefixIcon: Icon(Icons.lock))),
                    const SizedBox(height: 20),
                    ElevatedButton.icon(
                      onPressed: enviarWiFiViaBLE,
                      icon: const Icon(Icons.bluetooth_connected),
                      label: const Text("Enviar para o ESP32"),
                      style: ElevatedButton.styleFrom(backgroundColor: Colors.blue, foregroundColor: Colors.white, minimumSize: const Size(double.infinity, 45)),
                    ),
                    const SizedBox(height: 10),
                    Text("Status: $statusBluetooth", style: const TextStyle(fontStyle: FontStyle.italic)),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoSensor(IconData icon, String label, String value, Color color) {
    return Column(
      children: [
        Icon(icon, color: color, size: 30),
        const SizedBox(height: 4),
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
        Text(value, style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
      ],
    );
  }
}

// --- NOVA TELA DE HISTÓRICO (ATUALIZADA COM OS 4 GRÁFICOS) ---
class HistoricoScreen extends StatelessWidget {
  final String deviceId;
  const HistoricoScreen({super.key, required this.deviceId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Histórico: $deviceId', style: const TextStyle(color: Colors.white)),
        backgroundColor: Colors.green[700],
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: StreamBuilder<QuerySnapshot>(
        // Lê os últimos 20 registos da subcoleção "historico"
        stream: FirebaseFirestore.instance
            .collection('devices')
            .doc(deviceId)
            .collection('historico')
            .limit(20) 
            .snapshots(),
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return const Center(child: CircularProgressIndicator());
          }
          if (!snapshot.hasData || snapshot.data!.docs.isEmpty) {
            return const Center(child: Text("Nenhum dado histórico encontrado."));
          }

          List<FlSpot> pontosTemperatura = [];
          List<FlSpot> pontosUmidadeAr = [];
          List<FlSpot> pontosUmidadeSolo = [];
          List<FlSpot> pontosPh = [];
          
          var docs = snapshot.data!.docs;
          
          // Extrai os 4 parâmetros de cada documento
          for (int i = 0; i < docs.length; i++) {
            var dados = docs[i].data() as Map<String, dynamic>;
            
            double temp = (dados['temperatura_ar'] ?? 0).toDouble();
            double umidAr = (dados['umidade_ar'] ?? 0).toDouble();
            double umidSolo = (dados['umidade_solo'] ?? 0).toDouble();
            double ph = (dados['ph'] ?? 0).toDouble();
            
            pontosTemperatura.add(FlSpot(i.toDouble(), temp));
            pontosUmidadeAr.add(FlSpot(i.toDouble(), umidAr));
            pontosUmidadeSolo.add(FlSpot(i.toDouble(), umidSolo));
            pontosPh.add(FlSpot(i.toDouble(), ph));
          }

          return SingleChildScrollView( // Permite rolar a tela para ver todos os gráficos
            padding: const EdgeInsets.all(16.0),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _buildGrafico("Temperatura do Ar (°C)", pontosTemperatura, Colors.orange),
                const SizedBox(height: 30),
                _buildGrafico("Umidade do Ar (%)", pontosUmidadeAr, Colors.blue),
                const SizedBox(height: 30),
                _buildGrafico("Umidade do Solo (%)", pontosUmidadeSolo, Colors.brown),
                const SizedBox(height: 30),
                _buildGrafico("Nível de pH", pontosPh, Colors.purple),
                const SizedBox(height: 20),
              ],
            ),
          );
        },
      ),
    );
  }

  // Função auxiliar para desenhar qualquer gráfico sem repetir código
  Widget _buildGrafico(String titulo, List<FlSpot> pontos, Color cor) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text(titulo, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        const SizedBox(height: 10),
        SizedBox(
          height: 200, // Altura fixa para cada gráfico não ficar espremido
          child: LineChart(
            LineChartData(
              gridData: FlGridData(show: true),
              titlesData: FlTitlesData(
                rightTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
                topTitles: AxisTitles(sideTitles: SideTitles(showTitles: false)),
              ),
              borderData: FlBorderData(show: true, border: Border.all(color: Colors.grey.shade300)),
              lineBarsData: [
                LineChartBarData(
                  spots: pontos,
                  isCurved: true,
                  color: cor,
                  barWidth: 3,
                  dotData: FlDotData(show: true), // Mostra a bolinha do ponto exato
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}