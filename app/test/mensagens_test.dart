import 'package:flutter_test/flutter_test.dart';
import 'package:greensync_app/mensagens.dart';

void main() {
  group('mensagemRecusaRega', () {
    const esperado = {
      'sem_dados': 'Não consegui confirmar o estado do vaso agora',
      'offline': 'O vaso está offline',
      'solo_encharcado': 'O solo já está úmido',
      'bomba_ligada': 'A bomba já está ligada',
      'intervalo': 'Aguarde alguns minutos para regar de novo',
      'duracao_grande': 'Duração inválida',
      'duracao_invalida': 'Duração inválida',
    };
    esperado.forEach((codigo, frase) {
      test(codigo, () => expect(mensagemRecusaRega(codigo), frase));
    });

    test('código desconhecido, nulo ou vazio', () {
      expect(mensagemRecusaRega('algo_novo'), 'Não foi possível regar agora');
      expect(mensagemRecusaRega(null), 'Não foi possível regar agora');
      expect(mensagemRecusaRega(''), 'Não foi possível regar agora');
    });
  });

  group('mensagemFalhaRega', () {
    test('"não tenho certeza" avisa que a rega pode ter acontecido', () {
      const motivo = 'não tenho certeza se o comando chegou ao vaso';
      expect(mensagemFalhaRega(motivo),
          'A rega pode ter acontecido: aguarde alguns minutos antes de tentar de novo');
      expect(mensagemFalhaRega('Não Tenho Certeza se chegou'),
          'A rega pode ter acontecido: aguarde alguns minutos antes de tentar de novo');
    });

    test('outros motivos', () {
      expect(mensagemFalhaRega('não consegui falar com o broker'), 'Não foi possível regar agora');
      expect(mensagemFalhaRega(null), 'Não foi possível regar agora');
      expect(mensagemFalhaRega(''), 'Não foi possível regar agora');
    });
  });

  test('mensagemRegaAgendada', () {
    expect(mensagemRegaAgendada(5), 'Regando por 5 segundos…');
    expect(mensagemRegaAgendada(1), 'Regando por 1 segundo…');
  });

  group('mensagemErroHttp', () {
    test('códigos conhecidos', () {
      expect(mensagemErroHttp(401), 'Chave de acesso inválida');
      expect(mensagemErroHttp(422), 'Pedido inválido');
      expect(mensagemErroHttp(429), 'Muitas tentativas');
      expect(mensagemErroHttp(502), 'Não consegui falar com o servidor, tente de novo');
      expect(mensagemErroHttp(503), 'Não consegui falar com o servidor, tente de novo');
    });

    test('qualquer outro erro cai na mensagem do servidor', () {
      expect(mensagemErroHttp(500), msgSemServidor);
      expect(mensagemErroHttp(404), msgSemServidor);
    });
  });

  group('textoEstadoOta (só informativo)', () {
    test('baixando e aplicando', () {
      expect(textoEstadoOta('baixando'), 'Atualizando o vaso...');
      expect(textoEstadoOta('aplicando'), 'Atualizando o vaso...');
    });

    test('solicitada (o backend já decidiu atualizar) também mostra "Atualizando"', () {
      expect(textoEstadoOta('solicitada'), 'Atualizando o vaso...');
    });

    test('em andamento mas parada além do prazo não mostra nada', () {
      for (final e in ['solicitada', 'baixando', 'aplicando']) {
        expect(textoEstadoOta(e, emAndamento: false), '');
      }
    });

    test('ok mostra a versão', () {
      expect(textoEstadoOta('ok', versao: '1.2.0'), 'Vaso atualizado (versão 1.2.0)');
      expect(textoEstadoOta('ok'), 'Vaso atualizado');
      expect(textoEstadoOta('ok', versao: ''), 'Vaso atualizado');
    });

    test('falhou e revertido', () {
      expect(textoEstadoOta('falhou'), 'A atualização falhou, o vaso continua na versão anterior');
      expect(textoEstadoOta('falhou', versao: '1.2.0'),
          'A atualização falhou, o vaso continua na versão anterior');
      expect(textoEstadoOta('revertido'), 'Vaso voltou para a versão anterior');
    });

    test('estado desconhecido ou nulo não mostra nada', () {
      expect(textoEstadoOta('marciano'), '');
      expect(textoEstadoOta(null), '');
    });
  });

  group('interpretarNotificacaoWifi', () {
    test('conectando não é final', () {
      final n = interpretarNotificacaoWifi('conectando')!;
      expect(n.status, 'Vaso conectando ao Wi-Fi…');
      expect(n.terminal, isFalse);
      expect(n.sucesso, isFalse);
    });

    test('ok é sucesso final', () {
      final n = interpretarNotificacaoWifi('ok')!;
      expect(n.status, 'Conectado ao Wi-Fi!');
      expect(n.terminal, isTrue);
      expect(n.sucesso, isTrue);
    });

    test('erros conhecidos', () {
      expect(interpretarNotificacaoWifi('erro:senha')!.status, 'Senha incorreta');
      expect(interpretarNotificacaoWifi('erro:rede')!.status, 'Rede não encontrada');
      expect(interpretarNotificacaoWifi('erro:timeout')!.status, 'Não consegui conectar a tempo');
      for (final e in ['erro:senha', 'erro:rede', 'erro:timeout']) {
        final n = interpretarNotificacaoWifi(e)!;
        expect(n.terminal, isTrue);
        expect(n.sucesso, isFalse);
      }
    });

    test('qualquer outro erro:*', () {
      expect(interpretarNotificacaoWifi('erro:dhcp')!.status, 'Não foi possível conectar');
      expect(interpretarNotificacaoWifi('erro:')!.status, 'Não foi possível conectar');
    });

    test('ignora espaços, quebra de linha e maiúsculas', () {
      expect(interpretarNotificacaoWifi(' OK\n')!.sucesso, isTrue);
      expect(interpretarNotificacaoWifi('Erro:Senha')!.status, 'Senha incorreta');
    });

    test('texto desconhecido é ignorado', () {
      expect(interpretarNotificacaoWifi('oi'), isNull);
      expect(interpretarNotificacaoWifi(''), isNull);
    });
  });
}
