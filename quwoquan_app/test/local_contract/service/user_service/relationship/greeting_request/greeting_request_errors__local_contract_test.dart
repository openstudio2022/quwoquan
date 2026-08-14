import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.GREETING 打招呼请求错误码契约。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction 恢复语义三件套,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 打招呼请求契约(USER.GREETING)', () {
    test('重复待处理招呼:409 surface,等待对方回复', () {
      expect(
        UserErrorCode.fromCode('USER.GREETING.duplicate_pending'),
        UserErrorCode.greetingDuplicatePending,
      );
      expect(UserErrorCode.greetingDuplicatePending.httpStatus, 409);
      expect(UserErrorCode.greetingDuplicatePending.recoveryAction, 'surface');
    });

    test('招呼请求不存在:404 surface', () {
      expect(
        UserErrorCode.fromCode('USER.GREETING.not_found'),
        UserErrorCode.greetingNotFound,
      );
      expect(UserErrorCode.greetingNotFound.httpStatus, 404);
      expect(UserErrorCode.greetingNotFound.recoveryAction, 'surface');
    });

    test('招呼状态已变更:409 surface,操作不可用', () {
      expect(
        UserErrorCode.fromCode('USER.GREETING.invalid_status_transition'),
        UserErrorCode.greetingInvalidStatusTransition,
      );
      expect(UserErrorCode.greetingInvalidStatusTransition.httpStatus, 409);
      expect(
        UserErrorCode.greetingInvalidStatusTransition.recoveryAction,
        'surface',
      );
    });

    test('招呼限流:429 retry 且退避一天', () {
      expect(
        UserErrorCode.fromCode('USER.GREETING.rate_limited'),
        UserErrorCode.greetingRateLimited,
      );
      expect(UserErrorCode.greetingRateLimited.httpStatus, 429);
      expect(UserErrorCode.greetingRateLimited.recoveryAction, 'retry');
      expect(
        UserErrorCode.greetingRateLimited.recoveryAfterSeconds,
        greaterThan(0),
      );
      expect(UserErrorCode.greetingRateLimited.recoveryAfterSeconds, 86400);
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.GREETING)', () {
    test('rate_limited 响应解析为 typed user 域错误并保留退避语义', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.greetingRateLimited.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.greetingRateLimited.code,
          origin: 'user',
          kind: 'rateLimited',
          nature: 'transient',
          businessObject: 'greeting_request',
          functionModule: 'user',
          userMessage: UserErrorCode.greetingRateLimited.defaultMessageZh,
          recoveryAction: UserErrorCode.greetingRateLimited.recoveryAction,
          recoveryAfterSeconds:
              UserErrorCode.greetingRateLimited.recoveryAfterSeconds,
          disruptionLevel: UserErrorCode.greetingRateLimited.disruptionLevel,
        ),
        requestPath: '/user/greetings',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.greetingRateLimited.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'retry');
      expect(recovery.afterSeconds, 86400);
    });
  });
}
