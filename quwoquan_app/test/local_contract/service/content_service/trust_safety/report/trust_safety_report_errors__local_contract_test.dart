// trust_safety/report 对象 generated 错误码的端侧断言覆盖:
// report_not_found 与 gathering_safety_*(安全处置授权,服务侧声明于
// trust_safety/report/errors.yaml)的枚举解析、恢复语义,并以
// gathering_safety_authority_unavailable 走 CloudErrorMapper 映射负例。
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart';

typedef _DeclaredCase = ({
  String wire,
  ContentErrorCode value,
  String recoveryAction,
  int recoveryAfterSeconds,
  int httpStatus,
});

void main() {
  const declared = <_DeclaredCase>[
    (
      wire: 'CONTENT.USER.report_not_found',
      value: ContentErrorCode.reportNotFound,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 404,
    ),
    (
      wire: 'CONTENT.USER.gathering_safety_authorization_invalid',
      value: ContentErrorCode.gatheringSafetyAuthorizationInvalid,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 400,
    ),
    (
      wire: 'CONTENT.USER.gathering_safety_authorization_denied',
      value: ContentErrorCode.gatheringSafetyAuthorizationDenied,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 403,
    ),
    (
      wire: 'CONTENT.USER.gathering_safety_authorization_conflict',
      value: ContentErrorCode.gatheringSafetyAuthorizationConflict,
      recoveryAction: 'surface',
      recoveryAfterSeconds: 0,
      httpStatus: 409,
    ),
    (
      wire: 'CONTENT.SYSTEM.gathering_safety_authority_unavailable',
      value: ContentErrorCode.gatheringSafetyAuthorityUnavailable,
      recoveryAction: 'retry',
      recoveryAfterSeconds: 3,
      httpStatus: 503,
    ),
  ];

  group('ContentErrorCode — trust_safety/report 错误码契约', () {
    for (final entry in declared) {
      test('${entry.wire} 解析与恢复语义与声明一致', () {
        final parsed = ContentErrorCode.fromCode(entry.wire);
        expect(parsed, entry.value);
        expect(parsed.code, entry.wire);
        expect(parsed.httpStatus, entry.httpStatus);
        expect(parsed.recoveryAction, entry.recoveryAction);
        expect(parsed.recoveryAfterSeconds, entry.recoveryAfterSeconds);
        expect(ContentErrorMessages.zh[parsed], isNotEmpty);
        expect(ContentErrorMessages.en[parsed], isNotEmpty);
      });
    }

    test('恢复语义横向不变量:授权类终态 surface,系统不可用 retry 带退避', () {
      // 授权无效/被拒/已变化都需要用户或授权方介入,不得静默自动重试。
      expect(
        ContentErrorCode.gatheringSafetyAuthorizationInvalid.recoveryAction,
        'surface',
      );
      expect(
        ContentErrorCode.gatheringSafetyAuthorizationDenied.recoveryAction,
        'surface',
      );
      expect(
        ContentErrorCode.gatheringSafetyAuthorizationConflict.recoveryAction,
        'surface',
      );
      // 授权服务本身不可用属瞬态,retry 且必须带退避秒数。
      expect(
        ContentErrorCode.gatheringSafetyAuthorityUnavailable.recoveryAction,
        'retry',
      );
      expect(
        ContentErrorCode
            .gatheringSafetyAuthorityUnavailable.recoveryAfterSeconds,
        greaterThan(0),
      );
    });
  });

  group('CloudErrorMapper — trust_safety/report 代表性映射负例', () {
    test('503 gathering_safety_authority_unavailable → typed 解析 + retry', () {
      final exception = CloudErrorMapper.fromStatusCode(
        503,
        body: canonicalRuntimeErrorBody(
          code: 'CONTENT.SYSTEM.gathering_safety_authority_unavailable',
          origin: 'remoteDependency',
          kind: 'unavailable',
          nature: 'transient',
          businessObject: 'report',
          functionModule: 'trust_safety',
          recoveryAction: 'retry',
          recoveryAfterSeconds: 3,
          requestId: 'req-report-errors-1',
          traceId: 'trace-report-errors-1',
        ),
        requestPath: '/content/trust-safety/gathering-safety',
      );

      expect(
        exception.code,
        'CONTENT.SYSTEM.gathering_safety_authority_unavailable',
      );
      expect(exception.domainErrorCode?.domain, 'content');
      expect(
        exception.domainErrorCode?.value,
        ContentErrorCode.gatheringSafetyAuthorityUnavailable,
      );
      expect(exception.runtimeFailure.kind, RuntimeFailureKind.unavailable);
      expect(exception.runtimeFailure.transportStatus, 503);
      expect(exception.runtimeFailure.recovery.action, 'retry');
      expect(exception.runtimeFailure.recovery.afterSeconds, 3);
    });
  });
}
