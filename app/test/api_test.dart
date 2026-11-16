import 'dart:async';
import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/api.dart';
import 'package:greensync_app/mensagens.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

ApiGreenSync api(MockClient client, {String url = 'http://backend:8000', Duration? timeout}) =>
    ApiGreenSync(
      client: client,
      baseUrl: url,
      chave: 'chave-teste',
      timeout: timeout ?? const Duration(seconds: 15),
    );

http.Response json(int status, Object corpo) => http.Response.bytes(
      utf8.encode(jsonEncode(corpo)),
      status,
      headers: {'content-type': 'application/json; charset=utf-8'},
    );

void main() {
  group('o que é enviado', () {
    test('regar: URL, cabeçalhos e corpo', () async {
      late http.Request visto;
      final c = MockClient((req) async {
        visto = req;
        return json(200, {'resultado': 'agendada', 'id': 'ag1', 'motivo': null});
      });
      await api(c).regar('vaso-01', duracaoS: 5);
      expect(visto.method, 'POST');
      expect(visto.url.toString(), 'http://backend:8000/dispositivos/vaso-01/regar');
      expect(visto.headers['X-API-Key'], 'chave-teste');
      expect(visto.headers['Content-Type'], startsWith('application/json'));
      expect(jsonDecode(visto.body), {'duracao_s': 5});
      expect((jsonDecode(visto.body) as Map)['duracao_s'], isA<int>());
    });

    test('atualizar: URL, cabeçalhos e corpo', () async {
      late http.Request visto;
      final c = MockClient((req) async {
        visto = req;
        return json(200, {'resultado': 'solicitada', 'id': 'x', 'motivo': null, 'versao': '2.0.0'});
      });
      await api(c).atualizar('vaso-01', 's3');
      expect(visto.url.toString(), 'http://backend:8000/dispositivos/vaso-01/atualizar');
      expect(visto.headers['X-API-Key'], 'chave-teste');
      expect(visto.headers['Content-Type'], startsWith('application/json'));
      expect(jsonDecode(visto.body), {'alvo': 's3'});
    });

    test('barra no fim da URL não duplica e o id é escapado', () async {
      late http.Request visto;
      final c = MockClient((req) async {
        visto = req;
        return json(200, {'resultado': 'agendada'});
      });
      await api(c, url: 'http://backend:8000/').regar('a b/c');
      expect(visto.url.toString(), 'http://backend:8000/dispositivos/a%20b%2Fc/regar');
    });
  });

  group('regar: respostas 200', () {
    test('agendada', () async {
      final c = MockClient((_) async => json(200, {'resultado': 'agendada', 'id': 'ag1', 'motivo': null}));
      final r = await api(c).regar('vaso-01');
      expect(r.resultado, 'agendada');
      expect(r.sucesso, isTrue);
      expect(r.id, 'ag1');
      expect(r.mensagem, 'Regando por 5 segundos…');
    });

    test('recusada traduz o motivo', () async {
      final c = MockClient((_) async => json(200, {'resultado': 'recusada', 'id': null, 'motivo': 'intervalo'}));
      final r = await api(c).regar('vaso-01');
      expect(r.resultado, 'recusada');
      expect(r.sucesso, isFalse);
      expect(r.motivo, 'intervalo');
      expect(r.mensagem, 'Aguarde alguns minutos para regar de novo');
    });

    test('falhou comum', () async {
      final c = MockClient((_) async =>
          json(200, {'resultado': 'falhou', 'id': 'ag1', 'motivo': 'não consegui falar com o broker'}));
      final r = await api(c).regar('vaso-01');
      expect(r.sucesso, isFalse);
      expect(r.mensagem, 'Não foi possível regar agora');
    });

    test('falhou incerto', () async {
      final c = MockClient((_) async => json(
          200, {'resultado': 'falhou', 'id': 'ag1', 'motivo': 'não tenho certeza se o comando chegou ao vaso'}));
      final r = await api(c).regar('vaso-01');
      expect(r.mensagem, 'A rega pode ter acontecido: aguarde alguns minutos antes de tentar de novo');
    });
  });

  group('atualizar: respostas 200', () {
    test('solicitada', () async {
      final c = MockClient((_) async =>
          json(200, {'resultado': 'solicitada', 'id': 'abc', 'motivo': null, 'versao': '2.0.0'}));
      final r = await api(c).atualizar('vaso-01', 'wroom');
      expect(r.sucesso, isTrue);
      expect(r.versao, '2.0.0');
      expect(r.id, 'abc');
      expect(r.mensagem, msgAtualizacaoSolicitada);
    });

    test('recusada traduz o motivo', () async {
      final c = MockClient((_) async =>
          json(200, {'resultado': 'recusada', 'id': null, 'motivo': 'versao_igual', 'versao': null}));
      final r = await api(c).atualizar('vaso-01', 'wroom');
      expect(r.sucesso, isFalse);
      expect(r.mensagem, 'O vaso já está na versão mais recente');
    });

    test('falhou', () async {
      final c = MockClient((_) async =>
          json(200, {'resultado': 'falhou', 'id': 'abc', 'motivo': 'não consegui falar com o broker', 'versao': '2.0.0'}));
      final r = await api(c).atualizar('vaso-01', 'wroom');
      expect(r.resultado, 'falhou');
      expect(r.mensagem, 'Não foi possível pedir a atualização agora');
    });
  });

  group('erros', () {
    final casos = {
      401: 'Chave de acesso inválida',
      422: 'Pedido inválido',
      429: 'Muitas tentativas',
      502: 'Não consegui falar com o servidor, tente de novo',
      503: 'Não consegui falar com o servidor, tente de novo',
      500: 'Não consegui falar com o servidor, tente de novo',
    };
    casos.forEach((status, frase) {
      test('HTTP $status', () async {
        final c = MockClient((_) async => json(status, {'detail': 'x'}));
        for (final r in [await api(c).regar('vaso-01'), await api(c).atualizar('vaso-01', 'wroom')]) {
          expect(r.resultado, 'erro');
          expect(r.sucesso, isFalse);
          expect(r.mensagem, frase);
        }
      });
    });

    test('timeout', () async {
      final c = MockClient((_) async {
        await Future<void>.delayed(const Duration(milliseconds: 300));
        return json(200, {'resultado': 'agendada'});
      });
      final r = await api(c, timeout: const Duration(milliseconds: 20)).regar('vaso-01');
      expect(r.resultado, 'erro');
      expect(r.mensagem, msgSemServidor);
    });

    test('exceção de rede', () async {
      final c = MockClient((_) async => throw http.ClientException('sem rede'));
      final r = await api(c).atualizar('vaso-01', 's3');
      expect(r.resultado, 'erro');
      expect(r.mensagem, msgSemServidor);
    });

    test('corpo 200 que não é JSON do backend', () async {
      final c = MockClient((_) async => http.Response('<html>oi</html>', 200));
      expect((await api(c).regar('vaso-01')).mensagem, msgSemServidor);
      final c2 = MockClient((_) async => json(200, ['lista']));
      expect((await api(c2).regar('vaso-01')).mensagem, msgSemServidor);
      final c3 = MockClient((_) async => json(200, {'sem': 'resultado'}));
      expect((await api(c3).regar('vaso-01')).mensagem, msgSemServidor);
    });

    test('resultado desconhecido não vira sucesso', () async {
      final c = MockClient((_) async => json(200, {'resultado': 'talvez'}));
      final r = await api(c).regar('vaso-01');
      expect(r.sucesso, isFalse);
      expect(r.mensagem, msgSemServidor);
    });
  });

  group('backend não configurado', () {
    test('sem API_URL não chama nada', () async {
      var chamadas = 0;
      final c = MockClient((_) async {
        chamadas++;
        return json(200, {'resultado': 'agendada'});
      });
      final a = api(c, url: '');
      expect(a.configurado, isFalse);
      final r1 = await a.regar('vaso-01');
      final r2 = await a.atualizar('vaso-01', 'wroom');
      expect(chamadas, 0);
      for (final r in [r1, r2]) {
        expect(r.resultado, 'erro');
        expect(r.mensagem, 'Backend não configurado');
      }
    });
  });
}
