import 'package:cloud_firestore/cloud_firestore.dart';

/// Timestamp do Firestore (ou DateTime) em DateTime; null se faltar ou for de outro tipo.
DateTime? paraData(Object? valor) {
  if (valor is Timestamp) return valor.toDate();
  if (valor is DateTime) return valor;
  return null;
}
