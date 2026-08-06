// ignore_for_file: prefer_initializing_formals

import 'dart:convert';

final class AppTelemetryBatchAck {
  const AppTelemetryBatchAck({
    required this.acceptedCount,
    required this.duplicateBatch,
  });

  final int acceptedCount;
  final bool duplicateBatch;
}

abstract interface class AppTelemetryTransport {
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  });
}

String canonicalJsonEncode(Object? value) => jsonEncode(_canonicalize(value));

Object? _canonicalize(Object? value) {
  if (value is Map) {
    final keys = value.keys.map((key) => key.toString()).toList()..sort();
    return <String, Object?>{
      for (final key in keys) key: _canonicalize(value[key]),
    };
  }
  if (value is Iterable) {
    return value.map(_canonicalize).toList(growable: false);
  }
  return value;
}
