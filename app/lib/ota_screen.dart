import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:flutter/material.dart';

import 'api.dart';
import 'mensagens.dart';
import 'ota_logica.dart';
import 'snack.dart';
import 'util_firestore.dart';

/// Tela "Atualização do firmware": versão instalada x disponível de cada placa e o botão Atualizar.
/// Tudo em tempo real pelo Firestore (devices/{id} e firmware/{alvo}); só o pedido passa pelo backend.
class OtaScreen extends StatefulWidget {
  final String deviceId;

  /// Só para testes; sem ele usa o backend configurado por --dart-define.
  final ApiGreenSync? api;

  const OtaScreen({super.key, required this.deviceId, this.api});

  @override
  State<OtaScreen> createState() => _OtaScreenState();
}

class _OtaScreenState extends State<OtaScreen> {
  late final ApiGreenSync _api = widget.api ?? ApiGreenSync();
  bool _ocupado = false;

  Future<void> _atualizar(String alvo) async {
    if (_ocupado) return;
    setState(() => _ocupado = true);
    final r = await _api.atualizar(widget.deviceId, alvo);
    if (!mounted) return;
    setState(() => _ocupado = false);
    mostrarSnack(context, r.mensagem, sucesso: r.sucesso);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Firmware: ${widget.deviceId}', style: const TextStyle(color: Colors.white)),
        backgroundColor: Colors.green[700],
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
        stream: FirebaseFirestore.instance.collection('devices').doc(widget.deviceId).snapshots(),
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return const Center(child: Text('Não consegui ler os dados do vaso.'));
          }
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());

          final dados = snapshot.data!.data() ?? <String, dynamic>{};
          final bruta = dados['ota'];
          final ota = bruta is Map ? Map<String, dynamic>.from(bruta) : null;
          final agora = DateTime.now();
          final offline = dados['status'] == 'offline';
          final emAndamento = otaEmAndamento(
            estado: ota?['estado'] as String?,
            atualizadoEm: paraData(ota?['atualizado_em']),
            agora: agora,
          );

          return ListView(
            padding: const EdgeInsets.all(16.0),
            children: [
              if (offline)
                const Padding(
                  padding: EdgeInsets.only(bottom: 12),
                  child: Text('Vaso offline: não é possível atualizar agora.',
                      style: TextStyle(color: Colors.grey, fontStyle: FontStyle.italic)),
                ),
              _PlacaOta(
                titulo: 'Sensores/bomba (WROOM)',
                alvo: 'wroom',
                instalada: dados['fw'] as String?,
                ota: ota,
                bloqueado: offline || emAndamento || _ocupado,
                onAtualizar: () => _atualizar('wroom'),
              ),
              const SizedBox(height: 12),
              _PlacaOta(
                titulo: 'Voz/tela (S3)',
                alvo: 's3',
                instalada: dados['fw_s3'] as String?,
                ota: ota,
                bloqueado: offline || emAndamento || _ocupado,
                onAtualizar: () => _atualizar('s3'),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _PlacaOta extends StatelessWidget {
  final String titulo;
  final String alvo;
  final String? instalada;
  final Map<String, dynamic>? ota;
  final bool bloqueado;
  final VoidCallback onAtualizar;

  const _PlacaOta({
    required this.titulo,
    required this.alvo,
    required this.instalada,
    required this.ota,
    required this.bloqueado,
    required this.onAtualizar,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 3,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
          stream: FirebaseFirestore.instance.collection('firmware').doc(alvo).snapshots(),
          builder: (context, snapshot) {
            final filhos = <Widget>[
              Text(titulo, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Text('Instalada: ${instalada == null || instalada!.isEmpty ? 'desconhecida' : instalada}'),
            ];

            if (snapshot.hasError) {
              final negada = snapshot.error is FirebaseException &&
                  (snapshot.error as FirebaseException).code == 'permission-denied';
              filhos.add(Text(negada ? 'Sem permissão para ler as versões' : 'Não consegui ler as versões',
                  style: const TextStyle(color: Colors.grey)));
            } else if (!snapshot.hasData) {
              filhos.add(const Padding(padding: EdgeInsets.only(top: 8), child: LinearProgressIndicator()));
            } else {
              final reg = snapshot.data!.data();
              final disponivel = reg?['versao'] is String ? reg!['versao'] as String : null;
              final notas = reg?['notas'] is String ? (reg!['notas'] as String).trim() : '';
              if (disponivel == null || disponivel.isEmpty) {
                filhos.add(const Text('Nenhuma versão publicada', style: TextStyle(color: Colors.grey)));
              } else {
                filhos.add(Text('Disponível: $disponivel'));
                if (notas.isNotEmpty) {
                  filhos.add(Padding(
                    padding: const EdgeInsets.only(top: 4),
                    child: Text(notas, style: const TextStyle(fontSize: 12, color: Colors.grey)),
                  ));
                }
              }
              if (mostrarBotaoAtualizar(instalada: instalada, disponivel: disponivel)) {
                filhos.add(const SizedBox(height: 12));
                filhos.add(ElevatedButton.icon(
                  onPressed: bloqueado ? null : onAtualizar,
                  icon: const Icon(Icons.system_update),
                  label: const Text('Atualizar'),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green[600],
                    foregroundColor: Colors.white,
                    minimumSize: const Size(double.infinity, 40),
                  ),
                ));
              }
            }

            filhos.addAll(_progresso());
            return Column(crossAxisAlignment: CrossAxisAlignment.start, children: filhos);
          },
        ),
      ),
    );
  }

  /// Progresso da atualização DESTA placa (texto e, se estiver andando, barra indeterminada).
  List<Widget> _progresso() {
    final o = ota;
    if (o == null || o['alvo'] != alvo) return const [];
    final estado = o['estado'] as String?;
    final motivo = o['motivo'] as String?;
    final agora = DateTime.now();
    final atualizadoEm = paraData(o['atualizado_em']);

    final travada = otaTravada(estado: estado, atualizadoEm: atualizadoEm, agora: agora);
    final andando = otaEmAndamento(estado: estado, atualizadoEm: atualizadoEm, agora: agora);
    final texto = travada ? msgSemRespostaDoVaso : textoProgressoOta(estado, motivo);
    if (texto.isEmpty) return const [];

    return [
      const SizedBox(height: 12),
      Text(texto, style: const TextStyle(fontStyle: FontStyle.italic)),
      if (andando) const Padding(padding: EdgeInsets.only(top: 6), child: LinearProgressIndicator()),
    ];
  }
}
