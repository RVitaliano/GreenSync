import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter_blue_plus/flutter_blue_plus.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:fl_chart/fl_chart.dart';
import 'firebase_options.dart';
import 'api.dart';
import 'mensagens.dart';
import 'ota_screen.dart';
import 'snack.dart';
import 'status_vaso.dart';
import 'util_firestore.dart';

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

  // ------------------------------------------------------------ Wi-Fi (BLE) ----

  bool _bleOcupado = false; // impede duas conexões ao mesmo tempo

  void _statusBle(String texto) {
    if (mounted) setState(() { statusBluetooth = texto; });
  }

  /// Procura "GreenSync_BLE" por até 5 s. A escuta é cancelada ao achar o vaso ou ao fim do tempo.
  Future<BluetoothDevice?> _procurarVaso() async {
    final achou = Completer<BluetoothDevice?>();
    final escuta = FlutterBluePlus.onScanResults.listen((resultados) {
      for (final r in resultados) {
        if (r.device.platformName == "GreenSync_BLE" || r.advertisementData.advName == "GreenSync_BLE") {
          if (!achou.isCompleted) achou.complete(r.device);
          break;
        }
      }
    });
    try {
      unawaited(FlutterBluePlus.startScan(timeout: const Duration(seconds: 5)).catchError((Object e) {
        if (!achou.isCompleted) achou.completeError(e);
      }));
      return await achou.future.timeout(const Duration(milliseconds: 5500), onTimeout: () => null);
    } finally {
      await escuta.cancel();
      try { await FlutterBluePlus.stopScan(); } catch (_) {}
    }
  }

  Future<void> enviarWiFiViaBLE() async {
    if (_bleOcupado) return;
    if (ssidController.text.isEmpty || passwordController.text.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Preencha o SSID e a Senha!')),
      );
      return;
    }

    _bleOcupado = true;
    BluetoothDevice? vaso;
    StreamSubscription<List<int>>? notificacoes;
    try {
      await pedirPermissoes();
      _statusBle("Procurando ESP32...");
      vaso = await _procurarVaso();
      if (vaso == null) {
        _statusBle(msgVasoNaoEncontrado);
        return;
      }

      _statusBle("Conectando ao ESP32...");
      await vaso.connect(license: License.nonprofit);
      List<BluetoothService> services = await vaso.discoverServices();

      BluetoothCharacteristic? caracteristica;
      for (BluetoothService service in services) {
        if (service.uuid.toString() == serviceUuid) {
          for (BluetoothCharacteristic c in service.characteristics) {
            if (c.uuid.toString() == charUuid) caracteristica = c;
          }
        }
      }
      if (caracteristica == null) {
        _statusBle(msgErroNaConexao);
        return;
      }

      final dados = utf8.encode("${ssidController.text},${passwordController.text}");

      if (!caracteristica.properties.notify) {
        // Firmware antigo: não responde. Só dá para dizer que foi enviado.
        _statusBle("Enviando credenciais...");
        await caracteristica.write(dados);
        _statusBle(msgEnviadoSemConfirmacao);
        await Future.delayed(const Duration(seconds: 2));
        return;
      }

      // Firmware novo: ativa as notificações ANTES de escrever e espera o resultado final.
      final resultado = Completer<NotificacaoWifi>();
      notificacoes = caracteristica.onValueReceived.listen((valor) {
        final n = interpretarNotificacaoWifi(utf8.decode(valor, allowMalformed: true));
        if (n == null) return;
        _statusBle(n.status);
        if (n.terminal && !resultado.isCompleted) resultado.complete(n);
      });
      await caracteristica.setNotifyValue(true);
      _statusBle("Enviando credenciais...");
      await caracteristica.write(dados);
      // Sem trocar o status aqui: "conectando" pode ter chegado antes de o write retornar.
      try {
        await resultado.future.timeout(const Duration(seconds: 45));
      } on TimeoutException {
        _statusBle(msgSemRespostaDoVaso);
      }
    } catch (_) {
      _statusBle(msgErroNaConexao);
    } finally {
      await notificacoes?.cancel();
      if (vaso != null) {
        try { await vaso.disconnect(); } catch (_) {}
      }
      _bleOcupado = false;
    }
  }

  // ------------------------------------------------------------------ rega ----

  final ApiGreenSync _api = ApiGreenSync();
  bool _regando = false; // chamada em andamento, e mais 5 s depois (evita toque duplo)

  Future<void> _regarAgora() async {
    final id = dispositivoSelecionado;
    if (id == null || _regando) return;
    setState(() => _regando = true);
    final r = await _api.regar(id, duracaoS: 5);
    if (!mounted) return;
    mostrarSnack(context, r.mensagem, sucesso: r.sucesso);
    await Future.delayed(const Duration(seconds: 5));
    if (mounted) setState(() => _regando = false);
  }

  Widget _buildBotaoRegar(StatusVaso status) {
    final botao = ElevatedButton.icon(
      onPressed: (_regando || status.offline) ? null : _regarAgora,
      icon: _regando
          ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
          : const Icon(Icons.water_drop),
      label: const Text("Regar agora"),
      style: ElevatedButton.styleFrom(
        backgroundColor: Colors.blue,
        foregroundColor: Colors.white,
        minimumSize: const Size(double.infinity, 40),
      ),
    );
    // Dica "Vaso offline" quando o botão está desabilitado por isso.
    return status.offline ? Tooltip(message: "Vaso offline", child: botao) : botao;
  }

  /// Linha informativa do OTA (o backend atualiza sozinho; aqui só se mostra o estado):
  /// "Atualizando o vaso...", "Vaso atualizado (versão X)", etc. Some se não houver o que dizer.
  Widget _buildEstadoOta(Map<String, dynamic> dados) {
    final ota = otaDoDispositivo(dados);
    if (ota == null) return const SizedBox.shrink();
    final alvo = ota['alvo'] is String ? ota['alvo'] as String : '';
    final instalada = alvo == 's3' ? dados['fw_s3'] : dados['fw'];
    final texto = textoOtaDoAlvo(ota, alvo, instalada is String ? instalada : null, DateTime.now());
    if (texto.isEmpty) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.only(top: 8),
      child: Text(texto,
          textAlign: TextAlign.center,
          style: const TextStyle(fontSize: 12, fontStyle: FontStyle.italic, color: Colors.black54)),
    );
  }

  Widget _buildStatusVaso(StatusVaso status, DateTime? atualizadoEm) {
    final cor = status.atual
        ? Colors.green
        : (status.estado == EstadoVaso.desatualizado ? Colors.orange : Colors.grey);
    return Row(
      children: [
        Icon(Icons.circle, size: 12, color: cor),
        const SizedBox(width: 6),
        Text(status.rotulo, style: TextStyle(fontWeight: FontWeight.bold, color: cor)),
        const Spacer(),
        if (atualizadoEm != null)
          Text(
            "Última leitura: ${formatarUltimaLeitura(atualizadoEm, DateTime.now())}",
            style: const TextStyle(fontSize: 12, color: Colors.grey),
          ),
      ],
    );
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
                  final atualizadoEm = paraData(leituraAtual['updated_at']);
                  final statusVaso = calcularStatusVaso(
                    status: dados['status'] as String?,
                    atualizadoEm: atualizadoEm,
                    agora: DateTime.now(),
                  );
                  final bombaLigada = leituraAtual['bomba_ligada'] == true;

                  return Card(
                    elevation: 3,
                    child: Padding(
                      padding: const EdgeInsets.all(16.0),
                      child: Column(
                        children: [
                          _buildStatusVaso(statusVaso, atualizadoEm),
                          if (!statusVaso.atual)
                            const Padding(
                              padding: EdgeInsets.only(top: 6),
                              child: Text(
                                "Valores da última leitura recebida (podem estar desatualizados)",
                                style: TextStyle(fontSize: 12, color: Colors.grey, fontStyle: FontStyle.italic),
                              ),
                            ),
                          const SizedBox(height: 12),
                          // Valores que não são de agora ficam esmaecidos, para não parecerem atuais.
                          Opacity(
                            opacity: statusVaso.atual ? 1.0 : 0.45,
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
                              ],
                            ),
                          ),
                          const Divider(height: 20),

                          // REGAR AGORA (5 s). O backend valida; aqui só pedimos e mostramos o resultado.
                          _buildBotaoRegar(statusVaso),
                          if (statusVaso.offline)
                            const Padding(
                              padding: EdgeInsets.only(top: 4),
                              child: Text("Vaso offline", style: TextStyle(fontSize: 12, color: Colors.grey)),
                            ),
                          if (bombaLigada)
                            const Padding(
                              padding: EdgeInsets.only(top: 6),
                              child: Row(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2)),
                                  SizedBox(width: 8),
                                  Text("Regando…", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.blue)),
                                ],
                              ),
                            ),
                          _buildEstadoOta(dados),
                          const SizedBox(height: 8),

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
                          const SizedBox(height: 8),
                          ElevatedButton.icon(
                            onPressed: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (context) => OtaScreen(deviceId: dispositivoSelecionado!)),
                              );
                            },
                            icon: const Icon(Icons.memory),
                            label: const Text("Versão do Firmware"),
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