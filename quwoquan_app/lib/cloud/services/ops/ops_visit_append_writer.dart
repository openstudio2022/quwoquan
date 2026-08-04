import 'package:quwoquan_app/cloud/runtime/generated/ops/ops_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/generated/ops_contracts.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef OpsVisitInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      required String idempotencyKey,
    });

/// RecordVisit 的强类型出站输入（ops.VisitRecord 对象契约）。
///
/// wire 形状只含 targetType/targetKey——访问 actor 与 occurredAt 由服务端从
/// 已验证主体派生，客户端绝不发送 userId（服务端 DisallowUnknownFields 会拒绝）。
/// [idempotencyKey] 是本次真实访问的稳定业务重放身份：同一次访问的网络重试与
/// 断网补传复用同一 key，服务端据此保证 visitCount 不重复累加。
class OpsVisitReportInput {
  const OpsVisitReportInput({
    required this.idempotencyKey,
    required this.targetType,
    required this.targetKey,
  });

  final String idempotencyKey;
  final String targetType;
  final String targetKey;

  /// 从本地补传队列恢复。这是 App 自有 storage codec，不是 Cloud wire decoder。
  factory OpsVisitReportInput.fromStorageJson(Map<String, dynamic> json) {
    const allowedFields = <String>{'idempotencyKey', 'targetType', 'targetKey'};
    final unknownFields = json.keys.toSet().difference(allowedFields);
    if (unknownFields.isNotEmpty) {
      throw FormatException(
        'Ops visit storage record contains unknown fields: '
        '${unknownFields.toList()..sort()}',
      );
    }
    return OpsVisitReportInput(
      idempotencyKey: _requiredStorageString(json, 'idempotencyKey'),
      targetType: _requiredStorageString(json, 'targetType'),
      targetKey: _requiredStorageString(json, 'targetKey'),
    );
  }

  Map<String, dynamic> toStorageJson() {
    return <String, dynamic>{
      'idempotencyKey': idempotencyKey,
      'targetType': targetType,
      'targetKey': targetKey,
    };
  }
}

String _requiredStorageString(Map<String, dynamic> json, String field) {
  final value = json[field];
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('Ops visit storage record requires $field');
  }
  return value.trim();
}

/// VisitRecord 对象的 typed append 写面（App consumer 唯一能力 record_visit）。
/// 访问统计读面（GetVisitStats）是 operator 能力，App 端不消费。
abstract class OpsVisitAppendWriter {
  Future<void> recordVisit(OpsVisitReportInput input);
}

class RemoteOpsVisitAppendWriter implements OpsVisitAppendWriter {
  const RemoteOpsVisitAppendWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final OpsVisitInvocationContextFactory invocationContext;

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
    await client.opsVisitRecordRecordVisit(
      RecordVisitRequest(
        targetType: _visitTargetType(input.targetType),
        targetKey: input.targetKey,
      ),
      context: invocationContext(
        OpsRequestPageIds.recordVisit,
        idempotencyKey: key,
      ),
    );
  }
}

VisitTargetType _visitTargetType(String value) {
  return switch (value.trim()) {
    'page' => VisitTargetType.page,
    'post' => VisitTargetType.post,
    'circle' => VisitTargetType.circle,
    'user' => VisitTargetType.user,
    _ => throw ArgumentError.value(
      value,
      'targetType',
      'must be page, post, circle, or user',
    ),
  };
}
