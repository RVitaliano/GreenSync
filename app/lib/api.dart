// Cliente do backend do GreenSync (só a rega manual). Usa apenas a X-API-Key; o app não tem
// chave de administrador e não pede atualização de firmware (o backend atualiza sozinho).
import 'dart:async';
import 'dart:convert';

import 'package:http/http.dart' as http;

import 'config.dart' as config;
import 'mensagens.dart';

/// Resultado de uma chamada ao backend, já com a mensagem pronta para o usuário.
class RespostaApi {
  /// "agendada", "recusada", "falhou" ou "erro" (falha de rede/HTTP).
  final String resultado;
  final String? motivo;
  final String? id;
  final String? versao;
  final String mensagem;

  const RespostaApi({
    required this.resultado,
    required this.mensagem,
    this.motivo,
    this.id,
    this.versao,
  });

  /// A rega foi aceita pelo backend.
  bool get sucesso => resultado == 'agendada';

  factory RespostaApi.erro(String mensagem) => RespostaApi(resultado: 'erro', mensagem: mensagem);
}

class ApiGreenSync {
  final http.Client _client;
  final String baseUrl;
  final String chave;
  final Duration timeout;

  /// Sem argumentos usa `API_URL` e `API_KEY` do --dart-define. Nos testes, passe um
  /// `http.Client` falso (MockClient).
  ApiGreenSync({
    http.Client? client,
    String? baseUrl,
    String? chave,
    this.timeout = const Duration(seconds: 15),
  })  : _client = client ?? http.Client(),
        baseUrl = _semBarraFinal(baseUrl ?? config.apiUrl),
        chave = chave ?? config.apiKey;

  static String _semBarraFinal(String url) =>
      url.endsWith('/') ? url.substring(0, url.length - 1) : url;

  bool get configurado => baseUrl.isNotEmpty;

  /// POST /dispositivos/{id}/regar com {"duracao_s": N}.
  Future<RespostaApi> regar(String deviceId, {int duracaoS = 5}) {
    return _post(deviceId, 'regar', {'duracao_s': duracaoS}, (r) {
      switch (r.resultado) {
        case 'agendada':
          return mensagemRegaAgendada(duracaoS);
        case 'recusada':
          return mensagemRecusaRega(r.motivo);
        case 'falhou':
          return mensagemFalhaRega(r.motivo);
        default:
          return msgSemServidor;
      }
    });
  }

  Future<RespostaApi> _post(
    String deviceId,
    String acao,
    Map<String, Object> corpo,
    String Function(RespostaApi) mensagemDo,
  ) async {
    if (!configurado) return RespostaApi.erro(msgBackendNaoConfigurado);

    final uri = Uri.parse('$baseUrl/dispositivos/${Uri.encodeComponent(deviceId)}/$acao');
    final http.Response resp;
    try {
      resp = await _client
          .post(
            uri,
            headers: {'Content-Type': 'application/json', 'X-API-Key': chave},
            body: jsonEncode(corpo),
          )
          .timeout(timeout);
    } on TimeoutException {
      return RespostaApi.erro(msgSemServidor);
    } catch (_) {
      // Sem rede, DNS, conexão recusada etc.
      return RespostaApi.erro(msgSemServidor);
    }

    if (resp.statusCode != 200) {
      return RespostaApi.erro(mensagemErroHttp(resp.statusCode));
    }

    try {
      final dados = jsonDecode(utf8.decode(resp.bodyBytes));
      if (dados is! Map || dados['resultado'] is! String) {
        return RespostaApi.erro(msgSemServidor);
      }
      final bruta = RespostaApi(
        resultado: dados['resultado'] as String,
        motivo: dados['motivo'] is String ? dados['motivo'] as String : null,
        id: dados['id'] is String ? dados['id'] as String : null,
        versao: dados['versao'] is String ? dados['versao'] as String : null,
        mensagem: '',
      );
      return RespostaApi(
        resultado: bruta.resultado,
        motivo: bruta.motivo,
        id: bruta.id,
        versao: bruta.versao,
        mensagem: mensagemDo(bruta),
      );
    } catch (_) {
      return RespostaApi.erro(msgSemServidor);
    }
  }
}
