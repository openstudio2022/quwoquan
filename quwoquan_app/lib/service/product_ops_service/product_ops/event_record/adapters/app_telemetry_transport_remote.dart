import 'dart:convert';

import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/event_record_batch_writer.dart';
import 'package:quwoquan_app/runtime/observability/telemetry/app_telemetry_transport.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;

/// Product Ops 对 [AppTelemetryTransport] 的唯一 production Remote adapter。
final class CloudAppTelemetryTransport implements AppTelemetryTransport {
  const CloudAppTelemetryTransport(this._writer);

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
