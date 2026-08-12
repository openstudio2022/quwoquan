import 'package:quwoquan_app/runtime/observability/generated/operation_privacy_catalog.g.dart';

/// 决定该用 request 还是 response 的密级。
enum OperationPayloadDirection { request, response }

/// 掩码后的占位值；高密级字段的值一律折成它。
const String operationPrivacyRedactedValue = '[REDACTED]';

/// metadata_only 下的占位值：保留键的存在性，丢弃全部内容。
const String operationPrivacyOmittedValue = '[OMITTED]';

/// 密级的敏感度序，与 `OperationPrivacyClass` 的声明顺序一致。
int _sensitivity(OperationPrivacyClass value) => value.index;

/// 在端侧日志与埋点出口执行 `operation.privacy` 声明的脱敏策略。
///
/// 与云侧 `OperationPrivacyRedactor` 消费同一份 codegen 派生表，语义逐条对齐：
/// 查不到策略时 fail-closed（未知 operation 按 SECRET + none 处理）。静默放行
/// 未登记的 operation 等于把「契约没覆盖到」变成「运行时泄漏」。
final class OperationPrivacyRedactor {
  /// 绑定 codegen 派生的策略表。
  const OperationPrivacyRedactor()
    : _policies = generatedOperationPrivacyPolicies;

  /// 只服务测试，允许注入受控策略表。
  const OperationPrivacyRedactor.withPolicies(
    Map<String, OperationPrivacyPolicy> policies,
  ) : _policies = policies;

  final Map<String, OperationPrivacyPolicy> _policies;

  /// 返回 operation 的派生策略；`null` 表示该 operation 未登记。
  OperationPrivacyPolicy? policyFor(String operationId) =>
      _policies[operationId.trim()];

  /// 全部已登记 operation，供门禁与测试枚举。
  List<String> get operationIds =>
      _policies.keys.toList(growable: false)..sort();

  /// 按 `operation.privacy` 对将要落日志的载荷脱敏。
  ///
  /// `logPolicy` 决定「值能否落盘」，classification 决定「哪些值必须掩码、
  /// 哪些键必须整条丢弃」：
  /// - [OperationLogPolicy.none]：整个载荷不落盘。
  /// - [OperationLogPolicy.metadataOnly]：保留键，值折成 [operationPrivacyOmittedValue]。
  /// - [OperationLogPolicy.redacted]：public / internal 值原样落盘，
  ///   sensitive / pii 值掩码。
  ///
  /// secret 无论 `logPolicy` 如何都整条丢弃：掩码值本身也会暴露该字段存在。
  Map<String, Object?> redactLogPayload({
    required String operationId,
    required OperationPayloadDirection direction,
    required Map<String, Object?> payload,
  }) {
    final policy = policyFor(operationId);
    if (policy == null) {
      return const <String, Object?>{};
    }
    final classification = direction == OperationPayloadDirection.request
        ? policy.requestClassification
        : policy.responseClassification;
    if (policy.logPolicy == OperationLogPolicy.none ||
        classification == OperationPrivacyClass.secret) {
      return const <String, Object?>{};
    }
    final result = <String, Object?>{};
    for (final entry in payload.entries) {
      if (policy.logPolicy == OperationLogPolicy.metadataOnly) {
        result[entry.key] = operationPrivacyOmittedValue;
      } else if (_sensitivity(classification) >=
          _sensitivity(OperationPrivacyClass.sensitive)) {
        result[entry.key] = operationPrivacyRedactedValue;
      } else {
        result[entry.key] = entry.value;
      }
    }
    return result;
  }

  /// 把埋点维度收敛到契约声明的白名单。
  ///
  /// 埋点是无差别外发的高基数入口：任何没有在 `telemetry.attributes` 里声明的键
  /// 都可能是业务载荷，直接丢弃而不是掩码——掩码后的键仍会进入指标维度并制造基数。
  Map<String, String> redactTelemetryAttributes({
    required String operationId,
    required Map<String, String> attributes,
  }) {
    final policy = policyFor(operationId);
    if (policy == null) {
      return const <String, String>{};
    }
    final result = <String, String>{};
    for (final entry in attributes.entries) {
      if (policy.telemetryAttributes.contains(entry.key)) {
        result[entry.key] = entry.value;
      }
    }
    return result;
  }
}
