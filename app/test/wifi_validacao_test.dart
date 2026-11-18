import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/mensagens.dart';

void main() {
  group('validarCredenciaisWifi', () {
    test('ok', () {
      expect(validarCredenciaisWifi('MinhaRede', 'senha123'), isNull);
    });

    test('ssid vazio', () {
      expect(validarCredenciaisWifi('', 'senha123'), 'Preencha o SSID e a Senha!');
    });

    test('senha vazia', () {
      expect(validarCredenciaisWifi('MinhaRede', ''), 'Preencha o SSID e a Senha!');
    });

    test('ssid e senha vazios', () {
      expect(validarCredenciaisWifi('', ''), 'Preencha o SSID e a Senha!');
    });

    test('ssid com vírgula', () {
      expect(validarCredenciaisWifi('Minha,Rede', 'senha123'), 'O nome da rede não pode ter vírgula');
      expect(validarCredenciaisWifi(',', 'senha123'), 'O nome da rede não pode ter vírgula');
    });

    test('senha com vírgula passa', () {
      expect(validarCredenciaisWifi('MinhaRede', 'abc,def,123'), isNull);
    });

    test('campos vazios têm prioridade sobre a vírgula no ssid', () {
      expect(validarCredenciaisWifi('a,b', ''), 'Preencha o SSID e a Senha!');
    });
  });

  test('msgPermissaoBluetooth', () {
    expect(msgPermissaoBluetooth, 'Permita o Bluetooth para configurar o vaso');
  });
}
