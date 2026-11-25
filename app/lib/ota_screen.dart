import 'package:cloud_firestore/cloud_firestore.dart';
import 'package:flutter/material.dart';

import 'mensagens.dart';
import 'ota_logica.dart';
import 'util_firestore.dart';

/// Tela "Firmware do vaso": SÓ INFORMATIVA. Mostra a versão instalada de cada placa e o estado da
/// atualização, em tempo real (devices/{id}: fw, fw_s3 e ota). Não tem nenhum botão de ação:
/// o backend atualiza os vasos sozinho quando sai uma versão nova.
class OtaScreen extends StatelessWidget {
  final String deviceId;

  const OtaScreen({super.key, required this.deviceId});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Firmware: $deviceId', style: const TextStyle(color: Colors.white)),
        backgroundColor: Colors.green[700],
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: StreamBuilder<DocumentSnapshot<Map<String, dynamic>>>(
        stream: FirebaseFirestore.instance.collection('devices').doc(deviceId).snapshots(),
        builder: (context, snapshot) {
          if (snapshot.hasError) {
            return const Center(child: Text('Não consegui ler os dados do vaso.'));
          }
          if (!snapshot.hasData) return const Center(child: CircularProgressIndicator());

          final dados = snapshot.data!.data() ?? <String, dynamic>{};
          final ota = otaDoDispositivo(dados);
          return ListView(
            padding: const EdgeInsets.all(16.0),
            children: [
              _PlacaFirmware(
                titulo: 'Sensores/bomba (WROOM)',
                alvo: 'wroom',
                instalada: dados['fw'] is String ? dados['fw'] as String : null,
                ota: ota,
              ),
              const SizedBox(height: 12),
              _PlacaFirmware(
                titulo: 'Voz/tela (S3)',
                alvo: 's3',
                instalada: dados['fw_s3'] is String ? dados['fw_s3'] as String : null,
                ota: ota,
              ),
              const Padding(
                padding: EdgeInsets.only(top: 16),
                child: Text(
                  'As atualizações são feitas automaticamente quando sai uma versão nova.',
                  style: TextStyle(fontSize: 12, color: Colors.grey, fontStyle: FontStyle.italic),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

/// O mapa `ota` do documento do vaso (ou null).
Map<String, dynamic>? otaDoDispositivo(Map<String, dynamic> dados) {
  final bruta = dados['ota'];
  return bruta is Map ? Map<String, dynamic>.from(bruta) : null;
}

/// Frase do estado do OTA para este alvo (vazia se a atualização é de outra placa ou não há o que dizer).
String textoOtaDoAlvo(Map<String, dynamic>? ota, String alvo, String? instalada, DateTime agora) {
  if (ota == null || ota['alvo'] != alvo) return '';
  final estado = ota['estado'] is String ? ota['estado'] as String : null;
  final andando = otaEmAndamento(estado: estado, atualizadoEm: paraData(ota['atualizado_em']), agora: agora);
  final versao = instalada ?? (ota['versao'] is String ? ota['versao'] as String : null);
  return textoEstadoOta(estado, emAndamento: andando, versao: versao);
}

class _PlacaFirmware extends StatelessWidget {
  final String titulo;
  final String alvo;
  final String? instalada;
  final Map<String, dynamic>? ota;

  const _PlacaFirmware({
    required this.titulo,
    required this.alvo,
    required this.instalada,
    required this.ota,
  });

  @override
  Widget build(BuildContext context) {
    final agora = DateTime.now();
    final texto = textoOtaDoAlvo(ota, alvo, instalada, agora);
    final doAlvo = ota != null && ota!['alvo'] == alvo;
    final estado = doAlvo && ota!['estado'] is String ? ota!['estado'] as String : null;
    final andando = doAlvo &&
        otaEmAndamento(estado: estado, atualizadoEm: paraData(ota!['atualizado_em']), agora: agora);
    final versao = (instalada == null || instalada!.isEmpty) ? 'desconhecida' : instalada!;
    return Card(
      elevation: 3,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulo, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            Text('Versão instalada: $versao'),
            if (texto.isNotEmpty) ...[
              const SizedBox(height: 12),
              Text(texto, style: const TextStyle(fontStyle: FontStyle.italic)),
              if (andando)
                const Padding(padding: EdgeInsets.only(top: 6), child: LinearProgressIndicator()),
            ],
          ],
        ),
      ),
    );
  }
}
