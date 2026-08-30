import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/observability/generated/operation_privacy_catalog.g.dart';
import 'package:quwoquan_app/runtime/observability/operation_privacy_redactor.dart';

/// 端侧 `operation.privacy` 脱敏契约。
///
/// 与云侧 `operation_privacy__redaction__local_contract_test.go` 的 8 个证明用例
/// 逐条同构：同一份 codegen 派生表在两端必须得到同一个脱敏结论，否则「云侧不落盘
/// 的字段被端侧日志落盘」这类漏洞会绕过整条治理链。
void main() {
  const redactor = OperationPrivacyRedactor();

  // 下列 operation 全部取自真实派生表，不是构造的 fixture；一旦契约密级变化，
  // 这些用例会先于生产泄漏失败。
  const secretOperation =
      'integration.connector_authorization.CompleteOAuthConnectorAuthorization';
  const piiRedactedOperation =
      'content.original_access_quota.ReserveOriginalImageAccessGrant';
  const piiMetadataOnlyOperation = 'content.comment.ListCommentsByAuthor';
  const logPolicyNoneOperation = 'circle.gathering.ApplyToGathering';
  const publicRequestOperation =
      'ops.experiment_assignment_fact.GetExperimentAssignment';

  group('secret 载荷永不落端侧日志', () {
    test('secret 请求整条丢弃，连键名都不保留', () {
      final result = redactor.redactLogPayload(
        operationId: secretOperation,
        direction: OperationPayloadDirection.request,
        payload: const <String, Object?>{
          'authorizationCode': 'ac_live_9f2c',
          'codeVerifier': 'cv_7731',
        },
      );

      expect(result, isEmpty);
    });

    test('secret 压过 logPolicy：即便声明可落盘也整条丢弃', () {
      final policy = redactor.policyFor(secretOperation);
      expect(policy, isNotNull);
      expect(policy!.logPolicy, isNot(OperationLogPolicy.none));

      final result = redactor.redactLogPayload(
        operationId: secretOperation,
        direction: OperationPayloadDirection.response,
        payload: const <String, Object?>{'accessToken': 'at_live_1'},
      );

      expect(result, isEmpty);
    });
  });

  group('高敏值被掩码而非原样落盘', () {
    test('pii 请求在 redacted 策略下键保留、值掩码', () {
      final result = redactor.redactLogPayload(
        operationId: piiRedactedOperation,
        direction: OperationPayloadDirection.request,
        payload: const <String, Object?>{
          'mediaAssetId': 'asset_7',
          'requesterUserId': 'user_10086',
          'purpose': 'download',
        },
      );

      expect(result.keys, containsAll(<String>['requesterUserId', 'purpose']));
      expect(
        result.values,
        everyElement(equals(operationPrivacyRedactedValue)),
        reason: 'pii 载荷的任何值都不允许出现在端侧日志里',
      );
      expect(result.values, isNot(contains('user_10086')));
    });

    test('public 请求在 redacted 策略下原样落盘', () {
      final result = redactor.redactLogPayload(
        operationId: publicRequestOperation,
        direction: OperationPayloadDirection.request,
        payload: const <String, Object?>{'experimentId': 'exp_reader_v2'},
      );

      expect(result['experimentId'], 'exp_reader_v2');
    });

    test('同一 operation 的 response 密级更高时独立收紧', () {
      final policy = redactor.policyFor(publicRequestOperation)!;
      expect(policy.requestClassification, OperationPrivacyClass.public);
      expect(policy.responseClassification, OperationPrivacyClass.sensitive);

      final result = redactor.redactLogPayload(
        operationId: publicRequestOperation,
        direction: OperationPayloadDirection.response,
        payload: const <String, Object?>{'variant': 'treatment_b'},
      );

      expect(result['variant'], operationPrivacyRedactedValue);
    });
  });

  test('metadata_only 保留键的存在性但丢弃全部内容', () {
    final result = redactor.redactLogPayload(
      operationId: piiMetadataOnlyOperation,
      direction: OperationPayloadDirection.request,
      payload: const <String, Object?>{
        'authorUserId': 'user_552',
        'cursor': 'c_20',
      },
    );

    expect(result.keys, <String>['authorUserId', 'cursor']);
    expect(result.values, everyElement(equals(operationPrivacyOmittedValue)));
  });

  test('logPolicy none 丢弃整个载荷', () {
    final result = redactor.redactLogPayload(
      operationId: logPolicyNoneOperation,
      direction: OperationPayloadDirection.request,
      payload: const <String, Object?>{'gatheringId': 'g_1', 'note': '带娃同行'},
    );

    expect(result, isEmpty);
  });

  test('埋点维度只保留契约声明的白名单键', () {
    final result = redactor.redactTelemetryAttributes(
      operationId: piiRedactedOperation,
      attributes: const <String, String>{
        'outcome': 'success',
        'purpose': 'download',
        'requesterUserId': 'user_10086',
        'deviceFingerprint': 'fp_abc',
      },
    );

    expect(result, <String, String>{
      'outcome': 'success',
      'purpose': 'download',
    });
    expect(
      result.keys,
      isNot(contains('requesterUserId')),
      reason: '未声明的维度会直接进入指标基数，必须丢弃而不是掩码',
    );
    expect(result.keys, isNot(contains('deviceFingerprint')));
  });

  group('未登记 operation fail-closed', () {
    test('未知 operation 的日志载荷整条丢弃', () {
      final result = redactor.redactLogPayload(
        operationId: 'content.post.OperationThatDoesNotExist',
        direction: OperationPayloadDirection.request,
        payload: const <String, Object?>{'postId': 'p_1'},
      );

      expect(result, isEmpty);
    });

    test('未知 operation 的埋点维度整条丢弃', () {
      final result = redactor.redactTelemetryAttributes(
        operationId: 'content.post.OperationThatDoesNotExist',
        attributes: const <String, String>{'outcome': 'success'},
      );

      expect(result, isEmpty);
    });
  });

  group('派生表本身的完整性', () {
    test('覆盖全部第一方领域', () {
      final domains = generatedOperationPrivacyPolicies.values
          .map((policy) => policy.domain)
          .toSet();

      expect(
        domains,
        containsAll(<String>[
          'assistant',
          'chat',
          'circle',
          'content',
          'integration',
          'notification',
          'ops',
        ]),
      );
    });

    test('每条策略的 operationId 与表键一致，且 metric 非空', () {
      for (final entry in generatedOperationPrivacyPolicies.entries) {
        expect(entry.value.operationId, entry.key);
        expect(entry.value.metric, isNotEmpty, reason: entry.key);
      }
    });

    test('端侧表条目数与同次 codegen 派生计数一致', () {
      // 计数由 codegen 与策略表同次派生；测试不再手写第二个会随 ContractGraph
      // operation 增长而腐化的 magic number。云侧产物由同一工具同时生成。
      expect(
        generatedOperationPrivacyPolicies,
        hasLength(generatedOperationPrivacyPolicyCount),
      );
    });
  });
}
