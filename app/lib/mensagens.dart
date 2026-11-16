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

// ------------------------------------------------------------ atualização ----

const String msgAtualizacaoSolicitada = 'Pedido de atualização enviado';

String mensagemRecusaAtualizar(String? motivo) {
  switch (motivo) {
    case 'sem_firmware':
      return 'Nenhuma versão disponível';
    case 'sem_dados':
      return 'Não consegui confirmar o estado do vaso agora';
    case 'offline':
      return 'O vaso está offline';
    case 'bomba_ligada':
      return 'Aguarde a bomba desligar';
    case 'versao_igual':
      return 'O vaso já está na versão mais recente';
    case 'ota_em_curso':
      return 'Já existe uma atualização em andamento';
    case 'firmware_invalido':
      return 'Versão indisponível no momento';
    default:
      return 'Não foi possível pedir a atualização agora';
  }
}

String mensagemFalhaAtualizar(String? motivo) {
  if (_incerto(motivo)) {
    return 'O pedido pode ter chegado ao vaso: aguarde alguns minutos antes de tentar de novo';
  }
  return 'Não foi possível pedir a atualização agora';
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

// ------------------------------------------------------- progresso do OTA ----

/// Código curto de erro do vaso (campo `motivo` do mapa `ota`) em português.
String traduzirMotivoOta(String? codigo) {
  switch (codigo) {
    case 'hash':
      return 'arquivo corrompido';
    case 'download':
      return 'não consegui baixar';
    case 'bomba_ligada':
      return 'bomba em uso';
    case 'versao_igual':
      return 'já estava nessa versão';
    case 'espaco':
      return 'sem espaço no vaso';
    case 'host':
      return 'origem não permitida';
    default: // inclui "desconhecido" e qualquer código novo
      return 'erro desconhecido';
  }
}

/// Texto do estado da atualização (`ota.estado`). Vazio se o estado não for conhecido.
String textoProgressoOta(String? estado, String? motivo) {
  switch (estado) {
    case 'solicitada':
      return 'Pedido enviado';
    case 'baixando':
      return 'Baixando…';
    case 'aplicando':
      return 'Instalando…';
    case 'ok':
      return 'Atualizado com sucesso';
    case 'falhou':
      return 'Falhou: ${traduzirMotivoOta(motivo)}';
    case 'revertido':
      return 'Voltou à versão anterior';
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
