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

  group('mensagemRecusaAtualizar', () {
    const esperado = {
      'sem_firmware': 'Nenhuma versão disponível',
      'sem_dados': 'Não consegui confirmar o estado do vaso agora',
      'offline': 'O vaso está offline',
      'bomba_ligada': 'Aguarde a bomba desligar',
      'versao_igual': 'O vaso já está na versão mais recente',
      'ota_em_curso': 'Já existe uma atualização em andamento',
      'firmware_invalido': 'Versão indisponível no momento',
    };
    esperado.forEach((codigo, frase) {
      test(codigo, () => expect(mensagemRecusaAtualizar(codigo), frase));
    });

    test('código desconhecido ou nulo', () {
      expect(mensagemRecusaAtualizar('outro'), 'Não foi possível pedir a atualização agora');
      expect(mensagemRecusaAtualizar(null), 'Não foi possível pedir a atualização agora');
    });
  });

  group('mensagemFalhaAtualizar', () {
    test('incerto e comum', () {
      expect(mensagemFalhaAtualizar('não tenho certeza se o comando chegou ao vaso'),
          'O pedido pode ter chegado ao vaso: aguarde alguns minutos antes de tentar de novo');
      expect(mensagemFalhaAtualizar('não consegui falar com o broker'),
          'Não foi possível pedir a atualização agora');
      expect(mensagemFalhaAtualizar(null), 'Não foi possível pedir a atualização agora');
    });
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

  group('progresso do OTA', () {
    test('estados', () {
      expect(textoProgressoOta('solicitada', null), 'Pedido enviado');
      expect(textoProgressoOta('baixando', null), 'Baixando…');
      expect(textoProgressoOta('aplicando', null), 'Instalando…');
      expect(textoProgressoOta('ok', null), 'Atualizado com sucesso');
      expect(textoProgressoOta('revertido', null), 'Voltou à versão anterior');
      expect(textoProgressoOta('falhou', 'hash'), 'Falhou: arquivo corrompido');
    });

    test('estado desconhecido ou nulo não mostra nada', () {
      expect(textoProgressoOta('marciano', null), '');
      expect(textoProgressoOta(null, null), '');
    });

    test('tradução dos motivos', () {
      const esperado = {
        'hash': 'arquivo corrompido',
        'download': 'não consegui baixar',
        'bomba_ligada': 'bomba em uso',
        'versao_igual': 'já estava nessa versão',
        'espaco': 'sem espaço no vaso',
        'host': 'origem não permitida',
        'desconhecido': 'erro desconhecido',
      };
      esperado.forEach((codigo, frase) => expect(traduzirMotivoOta(codigo), frase));
      expect(traduzirMotivoOta('qualquer_outro'), 'erro desconhecido');
      expect(traduzirMotivoOta(null), 'erro desconhecido');
      expect(textoProgressoOta('falhou', null), 'Falhou: erro desconhecido');
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
