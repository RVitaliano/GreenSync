// Regra do estado do OTA mostrado no app (sem Flutter nem Firestore, para testar).
// O app só exibe: quem atualiza os vasos é o backend.

/// Atualização "em andamento" parada há mais que isso é considerada travada (igual ao backend):
/// o app deixa de mostrar "Atualizando o vaso..." em vez de mostrar para sempre.
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
