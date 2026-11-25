import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/status_vaso.dart';

void main() {
  final agora = DateTime.utc(2026, 11, 16, 12, 0, 0);

  StatusVaso calc(String? status, Duration? idade) => calcularStatusVaso(
        status: status,
        atualizadoEm: idade == null ? null : agora.subtract(idade),
        agora: agora,
      );

  test('online com leitura recente', () {
    final s = calc('online', const Duration(seconds: 30));
    expect(s.rotulo, 'Online');
    expect(s.atual, isTrue);
  });

  test('no limite exato ainda é online; acima vira "Dados de há X min"', () {
    expect(calc('online', limiteDadosAntigos).rotulo, 'Online');
    final s = calc('online', const Duration(minutes: 5));
    expect(s.rotulo, 'Dados de há 5 min');
    expect(s.estado, EstadoVaso.desatualizado);
    expect(s.atual, isFalse);
  });

  test('offline vence tudo', () {
    final s = calc('offline', const Duration(seconds: 5));
    expect(s.rotulo, 'Offline');
    expect(s.offline, isTrue);
    expect(s.atual, isFalse);
    expect(calc('offline', null).rotulo, 'Offline');
  });

  test('sem updated_at: "Sem dados"', () {
    expect(calc('online', null).rotulo, 'Sem dados');
    expect(calc(null, null).estado, EstadoVaso.semDados);
  });

  test('relógio do celular atrás do servidor não dá idade negativa', () {
    final s = calcularStatusVaso(
        status: 'online', atualizadoEm: agora.add(const Duration(seconds: 10)), agora: agora);
    expect(s.rotulo, 'Online');
  });

  test('limite configurável', () {
    final s = calcularStatusVaso(
      status: 'online',
      atualizadoEm: agora.subtract(const Duration(seconds: 40)),
      agora: agora,
      limite: const Duration(seconds: 30),
    );
    expect(s.estado, EstadoVaso.desatualizado);
  });

  test('descreverIdade', () {
    expect(descreverIdade(const Duration(seconds: 10)), 'alguns segundos');
    expect(descreverIdade(const Duration(minutes: 3, seconds: 59)), '3 min');
    expect(descreverIdade(const Duration(hours: 2, minutes: 59)), '2 h');
    expect(descreverIdade(const Duration(days: 1, hours: 5)), '1 dia');
    expect(descreverIdade(const Duration(days: 3)), '3 dias');
  });

  test('formatarUltimaLeitura: hoje só a hora, outro dia com a data', () {
    final hoje = DateTime(2026, 11, 16, 14, 5, 9);
    final agoraLocal = DateTime(2026, 11, 16, 20, 0, 0);
    expect(formatarUltimaLeitura(hoje, agoraLocal), '14:05:09');
    expect(formatarUltimaLeitura(DateTime(2026, 11, 8, 9, 3, 1), agoraLocal), '08/11 09:03:01');
  });
}
