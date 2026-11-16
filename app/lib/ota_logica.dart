// Regras da tela de atualização (sem Flutter nem Firestore, para testar).

/// Atualização "em andamento" parada há mais que isso é considerada travada (igual ao backend).
const Duration prazoOtaTravada = Duration(minutes: 10);

const Set<String> estadosOtaEmAndamento = {'solicitada', 'baixando', 'aplicando'};

/// Há uma atualização andando de verdade? Sem `atualizadoEm` não dá para saber: conta como travada.
bool otaEmAndamento({
  required String? estado,
  required DateTime? atualizadoEm,
  required DateTime agora,
  Duration prazo = prazoOtaTravada,
}) {
  if (estado == null || !estadosOtaEmAndamento.contains(estado)) return false;
  if (atualizadoEm == null) return false;
  return agora.difference(atualizadoEm) < prazo;
}

/// Estado de andamento, mas parado além do prazo (o botão é liberado).
bool otaTravada({
  required String? estado,
  required DateTime? atualizadoEm,
  required DateTime agora,
  Duration prazo = prazoOtaTravada,
}) {
  if (estado == null || !estadosOtaEmAndamento.contains(estado)) return false;
  return !otaEmAndamento(estado: estado, atualizadoEm: atualizadoEm, agora: agora, prazo: prazo);
}

/// O botão "Atualizar" só aparece se existe versão disponível diferente da instalada.
bool mostrarBotaoAtualizar({required String? instalada, required String? disponivel}) {
  if (disponivel == null || disponivel.isEmpty) return false;
  return disponivel != instalada;
}
