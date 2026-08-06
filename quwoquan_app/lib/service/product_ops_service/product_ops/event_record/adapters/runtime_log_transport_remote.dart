import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/service/product_ops_service/product_ops/event_record/adapters/event_record_batch_writer.dart';
import 'package:quwoquan_app/runtime/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/runtime/observability/runtime_log_record.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart' as ops;

/// 已登记的 App runtime diagnostics 远端 adapter。请求路径、operation attribution
/// 与鉴权页标识均由 metadata codegen 提供，禁止调用方重新拼接业务路由。
final class CloudRuntimeLogTransport implements RuntimeLogTransport {
  const CloudRuntimeLogTransport({required this._writer});

  final OpsEventRecordBatchWriter _writer;

  @override
  Future<int> send(List<RuntimeLogRecord> records) async {
    if (records.isEmpty) return 0;
    if (records.length > RuntimeLogCatalog.maxBatchItems) {
      throw ArgumentError.value(records.length, 'records', '超过日志批次上限');
    }
    final request = ops.RuntimeLogBatchRequest(
      records: records
          .map((record) => ops.RuntimeLogRecordWire.fromWire(record.toWire()))
          .toList(growable: false),
    );
    final body = _canonicalJsonEncode(request.toWire());
    final receipt = await _writer.reportRuntimeLogBatch(
      request,
      idempotencyKey: sha256.convert(utf8.encode(body)).toString(),
    );
    final accepted = receipt.acceptedCount;
    if (accepted < 0 || accepted > records.length) {
      throw const FormatException(
        'runtime log batch receipt has invalid acceptedCount',
      );
    }
    return accepted;
  }
}

String _canonicalJsonEncode(Object? value) => jsonEncode(_canonicalize(value));

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
