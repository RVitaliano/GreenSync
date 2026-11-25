import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/ota_logica.dart';

void main() {
  final agora = DateTime.utc(2026, 11, 16, 12, 0, 0);
  DateTime ha(Duration d) => agora.subtract(d);

  group('otaEmAndamento', () {
    test('estados em andamento e recentes contam como andando', () {
      for (final e in ['solicitada', 'baixando', 'aplicando']) {
        expect(otaEmAndamento(estado: e, atualizadoEm: ha(const Duration(minutes: 1)), agora: agora), isTrue);
      }
    });

    test('mais antiga que 10 minutos é considerada travada: o app deixa de mostrar "Atualizando"', () {
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: ha(const Duration(minutes: 9)), agora: agora), isTrue);
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: ha(const Duration(minutes: 10)), agora: agora), isFalse);
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: ha(const Duration(hours: 2)), agora: agora), isFalse);
    });

    test('estados finais, nulos e sem data não contam', () {
      for (final e in ['ok', 'falhou', 'revertido', null, 'marciano']) {
        expect(otaEmAndamento(estado: e, atualizadoEm: ha(const Duration(seconds: 5)), agora: agora), isFalse);
      }
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: null, agora: agora), isFalse);
    });
  });
}
