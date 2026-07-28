import 'dart:convert';

import 'package:quwoquan_app/app/startup/startup_telemetry.dart';
import 'package:quwoquan_app/cloud/runtime/codec/cloud_response_decoder.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';

/// 匿名启动遥测的受限 Remote adapter。
///
/// 这个请求刻意使用无凭证的 [CloudHttpClient]：启动日志不能绑定当前登录账号，也不应
/// 触发 token 刷新。路径与 operation 仍完全来自 metadata codegen。
final class RemoteStartupTelemetryTransport
    implements StartupTelemetryTransport {
  factory RemoteStartupTelemetryTransport({
    required CloudHttpClient httpClient,
    required String baseUrl,
  }) {
    return RemoteStartupTelemetryTransport._(httpClient, baseUrl.trim());
  }

  RemoteStartupTelemetryTransport._(this._httpClient, this._baseUrl);

  final CloudHttpClient _httpClient;
  final String _baseUrl;

  factory RemoteStartupTelemetryTransport.fromRuntimeConfig({
    required CloudHttpClient httpClient,
  }) {
    return RemoteStartupTelemetryTransport(
      httpClient: httpClient,
      baseUrl: CloudRuntimeConfig.gatewayBaseUrl,
    );
  }

  @override
  Future<StartupTelemetryBatchAck> report(
    List<StartupTelemetryEvent> events, {
    required String proof,
  }) async {
    if (events.isEmpty) {
      return const StartupTelemetryBatchAck(
        acceptedCount: 0,
        duplicateCount: 0,
      );
    }
    final decoded = await _httpClient.postJson(
      Uri.parse('$_baseUrl${OpsApiMetadata.reportStartupEventBatchPath}'),
      headers: <String, String>{'X-Qwq-Startup-Proof': proof},
      body: <String, Object?>{
        'events': events.map((event) => event.toJson()).toList(growable: false),
      }.cast<String, dynamic>(),
      requireAuth: false,
    );
    final object = CloudResponseDecoder.asObject(
      decoded is String ? jsonDecode(decoded) : decoded,
      context: OpsApiMetadata.reportStartupEventBatchOperation,
    );
    final serverAcceptedCount = _asInt(object['acceptedCount']);
    final duplicateBatch = object['duplicateBatch'] == true;
    return StartupTelemetryBatchAck(
      acceptedCount: duplicateBatch ? 0 : serverAcceptedCount,
      duplicateCount: duplicateBatch ? serverAcceptedCount : 0,
    );
  }
}

int _asInt(Object? value) {
  if (value is int) {
    return value;
  }
  if (value is num) {
    return value.round();
  }
  return int.tryParse(value?.toString() ?? '') ?? 0;
}
