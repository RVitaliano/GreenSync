import 'package:flutter/material.dart';

/// SnackBar verde (sucesso) ou laranja (recusa/falha).
void mostrarSnack(BuildContext context, String texto, {required bool sucesso}) {
  ScaffoldMessenger.of(context)
    ..hideCurrentSnackBar()
    ..showSnackBar(
      SnackBar(
        content: Text(texto),
        backgroundColor: sucesso ? Colors.green[700] : Colors.orange[800],
      ),
    );
}
