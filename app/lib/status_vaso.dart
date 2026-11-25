// Estado do vaso (online/offline/dados velhos) a partir do Firestore. Funções puras.

/// Depois disso sem leitura nova, o vaso "online" mostra "Dados de há X min" (fácil de ajustar).
const Duration limiteDadosAntigos = Duration(seconds: 120);

enum EstadoVaso { online, offline, desatualizado, semDados }

class StatusVaso {
  final EstadoVaso estado;
  final String rotulo;

  const StatusVaso(this.estado, this.rotulo);

  /// Só "Online" significa que os números são de agora.
  bool get atual => estado == EstadoVaso.online;
  bool get offline => estado == EstadoVaso.offline;
}

/// [status] = devices/{id}.status; [atualizadoEm] = leitura_atual.updated_at.
StatusVaso calcularStatusVaso({
  required String? status,
  required DateTime? atualizadoEm,
  required DateTime agora,
  Duration limite = limiteDadosAntigos,
}) {
  if (status == 'offline') return const StatusVaso(EstadoVaso.offline, 'Offline');
  if (atualizadoEm == null) return const StatusVaso(EstadoVaso.semDados, 'Sem dados');

  var idade = agora.difference(atualizadoEm);
  if (idade.isNegative) idade = Duration.zero; // relógio do celular um pouco atrás do servidor
  if (idade > limite) {
    return StatusVaso(EstadoVaso.desatualizado, 'Dados de há ${descreverIdade(idade)}');
  }
  return const StatusVaso(EstadoVaso.online, 'Online');
}

/// "5 min", "2 h", "3 dias" (arredonda para baixo, nunca exagera).
String descreverIdade(Duration d) {
  if (d.inMinutes < 1) return 'alguns segundos';
  if (d.inMinutes < 60) return '${d.inMinutes} min';
  if (d.inHours < 24) return '${d.inHours} h';
  return '${d.inDays} ${d.inDays == 1 ? 'dia' : 'dias'}';
}

String _dois(int n) => n.toString().padLeft(2, '0');

/// "14:05:09" se for de hoje; senão "08/11 14:05:09". Usa o horário local do celular.
String formatarUltimaLeitura(DateTime quando, DateTime agora) {
  final q = quando.toLocal();
  final a = agora.toLocal();
  final hora = '${_dois(q.hour)}:${_dois(q.minute)}:${_dois(q.second)}';
  final hoje = q.year == a.year && q.month == a.month && q.day == a.day;
  return hoje ? hora : '${_dois(q.day)}/${_dois(q.month)} $hora';
}
