import 'package:quwoquan_app/cloud/runtime/cloud_request_headers.dart';
import 'package:quwoquan_app/cloud/runtime/cloud_runtime_config.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_api_metadata.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';

/// RecordVisit 的强类型出站输入（ops.VisitRecord 对象契约）。
///
/// wire 形状只含 targetType/targetKey/sessionId/source——访问 actor 由服务端从
/// 已验证主体派生，客户端绝不发送 userId（服务端 DisallowUnknownFields 会拒绝）。
/// [idempotencyKey] 是本次真实访问的稳定业务重放身份：同一次访问的网络重试与
/// 断网补传复用同一 key，服务端据此保证 visitCount 不重复累加。
class OpsVisitReportInput {
  const OpsVisitReportInput({
    required this.idempotencyKey,
    required this.targetType,
    required this.targetKey,
    this.sessionId = '',
    this.source = '',
  });

  final String idempotencyKey;
  final String targetType;
  final String targetKey;
  final String sessionId;
  final String source;

  /// 从本地补传队列恢复（storage 形状含 idempotencyKey，wire 形状不含）。
  factory OpsVisitReportInput.fromStorageJson(Map<String, dynamic> json) {
    return OpsVisitReportInput(
      idempotencyKey: (json['idempotencyKey'] ?? '').toString(),
      targetType: (json['targetType'] ?? '').toString(),
      targetKey: (json['targetKey'] ?? '').toString(),
      sessionId: (json['sessionId'] ?? '').toString(),
      source: (json['source'] ?? '').toString(),
    );
  }

  Map<String, dynamic> toStorageJson() {
    return <String, dynamic>{
      'idempotencyKey': idempotencyKey,
      ...toWireJson(),
    };
  }

  Map<String, dynamic> toWireJson() {
    return <String, dynamic>{
      'targetType': targetType,
      'targetKey': targetKey,
      if (sessionId.trim().isNotEmpty) 'sessionId': sessionId.trim(),
      if (source.trim().isNotEmpty) 'source': source.trim(),
    };
  }
}

/// VisitRecord 对象的 typed append 写面（App consumer 唯一能力 record_visit）。
/// 访问统计读面（GetVisitStats）是 operator 能力，App 端不消费。
abstract class OpsVisitAppendWriter {
  Future<void> recordVisit(OpsVisitReportInput input);
}

class RemoteOpsVisitAppendWriter implements OpsVisitAppendWriter {
  factory RemoteOpsVisitAppendWriter({
    required CloudHttpClient httpClient,
  }) {
    return RemoteOpsVisitAppendWriter._(httpClient);
  }

  RemoteOpsVisitAppendWriter._(this._httpClient);

  final CloudHttpClient _httpClient;

  @override
  Future<void> recordVisit(OpsVisitReportInput input) async {
    final key = input.idempotencyKey.trim();
    if (key.isEmpty) {
      throw ArgumentError.value(
        input.idempotencyKey,
        'idempotencyKey',
        'must not be empty',
      );
    }
    await _httpClient.postJson(
      Uri.parse(
        '${CloudRuntimeConfig.gatewayBaseUrl}${OpsApiMetadata.recordVisitPath}',
      ),
      headers: <String, String>{
        ...CloudRequestHeaders.forPage(OpsRequestPageIds.recordVisit),
        'Idempotency-Key': key,
      },
      body: input.toWireJson(),
    );
  }
}
