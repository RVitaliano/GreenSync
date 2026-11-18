// Frases mostradas ao usuário. Funções puras (sem Flutter nem rede), fáceis de testar.

const String msgBackendNaoConfigurado = 'Backend não configurado';
const String msgSemServidor = 'Não consegui falar com o servidor, tente de novo';

String _minusculas(String? s) => (s ?? '').toLowerCase();

bool _incerto(String? motivo) => _minusculas(motivo).contains('não tenho certeza');

// ------------------------------------------------------------------ rega ----

String mensagemRegaAgendada(int segundos) =>
    'Regando por $segundos ${segundos == 1 ? 'segundo' : 'segundos'}…';

/// Frase para o `motivo` de uma rega recusada (código curto do backend).
String mensagemRecusaRega(String? motivo) {
  switch (motivo) {
    case 'sem_dados':
      return 'Não consegui confirmar o estado do vaso agora';
    case 'offline':
      return 'O vaso está offline';
    case 'solo_encharcado':
      return 'O solo já está úmido';
    case 'bomba_ligada':
      return 'A bomba já está ligada';
    case 'intervalo':
      return 'Aguarde alguns minutos para regar de novo';
    case 'duracao_grande':
    case 'duracao_invalida':
      return 'Duração inválida';
    default:
      return 'Não foi possível regar agora';
  }
}

/// Frase para uma rega que falhou na hora de executar (`motivo` é texto livre).
String mensagemFalhaRega(String? motivo) {
  if (_incerto(motivo)) {
    return 'A rega pode ter acontecido: aguarde alguns minutos antes de tentar de novo';
  }
  return 'Não foi possível regar agora';
}

// -------------------------------------------------------------------- http ----

/// Frase para respostas HTTP que não são 200.
String mensagemErroHttp(int status) {
  switch (status) {
    case 401:
      return 'Chave de acesso inválida';
    case 422:
      return 'Pedido inválido';
    case 429:
      return 'Muitas tentativas';
    default: // 502, 503 e qualquer outro erro do servidor
      return msgSemServidor;
  }
}

// --------------------------------------------- estado do OTA (só informativo) ----

/// Texto do estado da atualização automática (`devices/{id}.ota.estado`), só para mostrar.
/// O app não pede nem controla atualização: o backend atualiza os vasos sozinho.
/// [emAndamento] = a atualização ainda está andando (não ficou parada além do prazo);
/// [versao] = versão instalada, usada no "ok". Vazio se não houver nada a mostrar.
String textoEstadoOta(String? estado, {bool emAndamento = true, String? versao}) {
  switch (estado) {
    case 'solicitada':
    case 'baixando':
    case 'aplicando':
      return emAndamento ? 'Atualizando o vaso...' : '';
    case 'ok':
      return (versao == null || versao.isEmpty)
          ? 'Vaso atualizado'
          : 'Vaso atualizado (versão $versao)';
    case 'falhou':
      return 'A atualização falhou, o vaso continua na versão anterior';
    case 'revertido':
      return 'Vaso voltou para a versão anterior';
    default:
      return '';
  }
}

// ------------------------------------------------- Wi-Fi pelo BLE (resposta) ----

const String msgVasoNaoEncontrado =
    'Vaso não encontrado. Ele está ligado e longe do Wi-Fi conhecido?';
const String msgSemRespostaDoVaso = 'Sem resposta do vaso';
const String msgEnviadoSemConfirmacao = 'Enviado (o vaso não confirma)';
const String msgErroNaConexao = 'Erro na conexão';
const String msgPermissaoBluetooth = 'Permita o Bluetooth para configurar o vaso';

/// Confere o SSID e a senha antes de enviar ao vaso. Devolve null se estiver ok, ou a mensagem.
/// O vaso recebe "ssid,senha", então o SSID não pode ter vírgula; a senha pode.
String? validarCredenciaisWifi(String ssid, String senha) {
  if (ssid.isEmpty || senha.isEmpty) return 'Preencha o SSID e a Senha!';
  if (ssid.contains(',')) return 'O nome da rede não pode ter vírgula';
  return null;
}

/// O que uma notificação do vaso (texto UTF-8) significa para a tela.
class NotificacaoWifi {
  final String status;

  /// true = é o resultado final (a espera termina).
  final bool terminal;

  /// true = conectou ao Wi-Fi.
  final bool sucesso;

  const NotificacaoWifi(this.status, {required this.terminal, required this.sucesso});
}

/// Interpreta "conectando", "ok" e "erro:*". Devolve null para texto desconhecido (ignorado).
NotificacaoWifi? interpretarNotificacaoWifi(String texto) {
  final t = texto.trim().toLowerCase();
  if (t == 'conectando') {
    return const NotificacaoWifi('Vaso conectando ao Wi-Fi…', terminal: false, sucesso: false);
  }
  if (t == 'ok') {
    return const NotificacaoWifi('Conectado ao Wi-Fi!', terminal: true, sucesso: true);
  }
  if (t.startsWith('erro:')) {
    switch (t) {
      case 'erro:senha':
        return const NotificacaoWifi('Senha incorreta', terminal: true, sucesso: false);
      case 'erro:rede':
        return const NotificacaoWifi('Rede não encontrada', terminal: true, sucesso: false);
      case 'erro:timeout':
        return const NotificacaoWifi('Não consegui conectar a tempo', terminal: true, sucesso: false);
      default:
        return const NotificacaoWifi('Não foi possível conectar', terminal: true, sucesso: false);
    }
  }
  return null;
}
