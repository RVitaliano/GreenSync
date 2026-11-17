import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/ota_screen.dart';

void main() {
  final agora = DateTime.utc(2026, 11, 16, 12, 0, 0);
  Map<String, dynamic> ota(String estado, {String alvo = 'wroom', Duration idade = const Duration(minutes: 1)}) =>
      {'alvo': alvo, 'id': 'x', 'versao': '2.0.0', 'estado': estado, 'atualizado_em': agora.subtract(idade)};

  group('textoOtaDoAlvo', () {
    test('baixando e aplicando', () {
      expect(textoOtaDoAlvo(ota('baixando'), 'wroom', '1.0.0', agora), 'Atualizando o vaso...');
      expect(textoOtaDoAlvo(ota('aplicando'), 'wroom', '1.0.0', agora), 'Atualizando o vaso...');
    });

    test('ok usa a versão instalada; sem ela, a do pedido', () {
      expect(textoOtaDoAlvo(ota('ok'), 'wroom', '2.0.0', agora), 'Vaso atualizado (versão 2.0.0)');
      expect(textoOtaDoAlvo(ota('ok'), 'wroom', null, agora), 'Vaso atualizado (versão 2.0.0)');
    });

    test('falhou e revertido', () {
      expect(textoOtaDoAlvo(ota('falhou'), 'wroom', '1.0.0', agora),
          'A atualização falhou, o vaso continua na versão anterior');
      expect(textoOtaDoAlvo(ota('revertido'), 'wroom', '1.0.0', agora), 'Vaso voltou para a versão anterior');
    });

    test('andamento parado há mais de 10 minutos não mostra "Atualizando"', () {
      expect(textoOtaDoAlvo(ota('baixando', idade: const Duration(minutes: 30)), 'wroom', '1.0.0', agora), '');
    });

    test('atualização de outra placa não aparece nesta', () {
      expect(textoOtaDoAlvo(ota('baixando', alvo: 's3'), 'wroom', '1.0.0', agora), '');
    });

    test('sem ota ou com estado estranho não mostra nada', () {
      expect(textoOtaDoAlvo(null, 'wroom', '1.0.0', agora), '');
      expect(textoOtaDoAlvo({'alvo': 'wroom', 'estado': 7}, 'wroom', '1.0.0', agora), '');
    });
  });

  test('otaDoDispositivo', () {
    expect(otaDoDispositivo({'fw': '1.0.0'}), isNull);
    expect(otaDoDispositivo({'ota': 'lixo'}), isNull);
    expect(otaDoDispositivo({'ota': {'estado': 'ok'}}), {'estado': 'ok'});
  });
}
