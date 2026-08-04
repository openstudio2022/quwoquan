// ignore_for_file: prefer_initializing_formals

import 'dart:convert';

import 'package:quwoquan_app/cloud/services/ops/event_record_batch_writer.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;

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

final class CloudAppTelemetryTransport implements AppTelemetryTransport {
  const CloudAppTelemetryTransport({required OpsEventRecordBatchWriter writer})
    : _writer = writer;

  final OpsEventRecordBatchWriter _writer;

  @override
  Future<AppTelemetryBatchAck> sendSealedBatch({
    required String canonicalBody,
    required String idempotencyKey,
  }) async {
    final decoded = jsonDecode(canonicalBody);
    if (decoded is! Map || decoded.keys.any((key) => key is! String)) {
      throw const FormatException(
        'sealed telemetry batch must be a canonical object',
      );
    }
    final request = ops.EventRecordBatchRequest.fromWire(
      Map<String, Object?>.from(decoded),
    );
    final receipt = await _writer.reportEventBatch(
      request,
      idempotencyKey: idempotencyKey,
    );
    return AppTelemetryBatchAck(
      acceptedCount: receipt.acceptedCount,
      duplicateBatch: receipt.duplicateBatch,
    );
  }
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
