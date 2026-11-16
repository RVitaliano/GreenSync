import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/ota_logica.dart';

void main() {
  final agora = DateTime.utc(2026, 11, 16, 12, 0, 0);
  DateTime ha(Duration d) => agora.subtract(d);

  group('otaEmAndamento', () {
    test('estados em andamento e recentes bloqueiam', () {
      for (final e in ['solicitada', 'baixando', 'aplicando']) {
        expect(otaEmAndamento(estado: e, atualizadoEm: ha(const Duration(minutes: 1)), agora: agora), isTrue);
      }
    });

    test('mais antiga que 10 minutos é considerada travada e libera', () {
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: ha(const Duration(minutes: 9)), agora: agora), isTrue);
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: ha(const Duration(minutes: 10)), agora: agora), isFalse);
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: ha(const Duration(hours: 2)), agora: agora), isFalse);
    });

    test('estados finais, nulos e sem data não bloqueiam', () {
      for (final e in ['ok', 'falhou', 'revertido', null, 'marciano']) {
        expect(otaEmAndamento(estado: e, atualizadoEm: ha(const Duration(seconds: 5)), agora: agora), isFalse);
      }
      expect(otaEmAndamento(estado: 'baixando', atualizadoEm: null, agora: agora), isFalse);
    });
  });

  group('otaTravada', () {
    test('só quando o estado era de andamento e passou do prazo (ou sem data)', () {
      expect(otaTravada(estado: 'aplicando', atualizadoEm: ha(const Duration(minutes: 30)), agora: agora), isTrue);
      expect(otaTravada(estado: 'aplicando', atualizadoEm: null, agora: agora), isTrue);
      expect(otaTravada(estado: 'aplicando', atualizadoEm: ha(const Duration(minutes: 1)), agora: agora), isFalse);
      expect(otaTravada(estado: 'ok', atualizadoEm: ha(const Duration(days: 1)), agora: agora), isFalse);
    });
  });

  group('mostrarBotaoAtualizar', () {
    test('só com versão disponível diferente da instalada', () {
      expect(mostrarBotaoAtualizar(instalada: '1.0.0', disponivel: '1.1.0'), isTrue);
      expect(mostrarBotaoAtualizar(instalada: null, disponivel: '1.1.0'), isTrue);
      expect(mostrarBotaoAtualizar(instalada: '1.1.0', disponivel: '1.1.0'), isFalse);
      expect(mostrarBotaoAtualizar(instalada: '1.0.0', disponivel: null), isFalse);
      expect(mostrarBotaoAtualizar(instalada: '1.0.0', disponivel: ''), isFalse);
    });
  });
}
