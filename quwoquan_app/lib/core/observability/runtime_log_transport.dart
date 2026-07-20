import 'dart:convert';

import 'package:crypto/crypto.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/core/observability/generated/runtime_log_catalog.g.dart';
import 'package:quwoquan_app/core/observability/runtime_log_ports.dart';
import 'package:quwoquan_app/core/observability/runtime_log_record.dart';

/// 已登记的 App runtime diagnostics 远端 adapter。请求路径、operation attribution
/// 与鉴权页标识均由 metadata codegen 提供，禁止调用方重新拼接业务路由。
final class CloudRuntimeLogTransport implements RuntimeLogTransport {
  factory CloudRuntimeLogTransport({
    required CloudHttpClient httpClient,
    String? baseUrl,
  }) {
    return CloudRuntimeLogTransport._(
      httpClient,
      (baseUrl ?? CloudRuntimeConfig.gatewayBaseUrl).trim(),
    );
  }

  CloudRuntimeLogTransport._(this._httpClient, this._baseUrl);

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  @override
  Future<int> send(List<RuntimeLogRecord> records) async {
    if (records.isEmpty) return 0;
    if (records.length > RuntimeLogCatalog.maxBatchItems) {
      throw ArgumentError.value(records.length, 'records', '超过日志批次上限');
    }
    final body = _canonicalJsonEncode(<String, Object?>{
      'records': records
          .map((record) => record.toWire())
          .toList(growable: false),
    });
    final path = OpsApiMetadata.reportRuntimeLogBatchPath;
    final response = await _httpClient.post(
      Uri.parse('$_baseUrl$path'),
      headers: <String, String>{
        ...CloudRequestHeaders.forPage(OpsRequestPageIds.reportRuntimeLogBatch),
        'Content-Type': 'application/json',
        'Idempotency-Key': sha256.convert(utf8.encode(body)).toString(),
      },
      body: body,
      encoding: utf8,
    );
    if (response.statusCode < 200 || response.statusCode >= 300) {
      final status = response.statusCode;
      final transient =
          status == 401 ||
          status == 408 ||
          status == 425 ||
          status == 429 ||
          status >= 500;
      throw RuntimeLogTransportException(
        permanent: !transient,
        reason: 'http_$status',
      );
    }
    final decoded = jsonDecode(response.body);
    if (decoded is! Map) {
      throw CloudErrorMapper.invalidResponse(
        message: 'runtime log batch ACK must be an object',
        requestPath: path,
      );
    }
    final accepted = _asInt(decoded['acceptedCount']);
    if (accepted < 0 || accepted > records.length) {
      throw CloudErrorMapper.invalidResponse(
        message: 'runtime log batch ACK has invalid acceptedCount',
        requestPath: path,
      );
    }
    return accepted;
  }

  static int _asInt(Object? value) {
    if (value is int) return value;
    return int.tryParse(value?.toString() ?? '') ?? -1;
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
