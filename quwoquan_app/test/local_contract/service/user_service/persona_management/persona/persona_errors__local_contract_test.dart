import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.PERSONA 分身管理错误码契约(quota/handle)。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction 恢复语义三件套,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 分身配额与圈号契约(USER.PERSONA)', () {
    test('分身数量达上限:400 surface,须先整理现有分身', () {
      expect(
        UserErrorCode.fromCode('USER.PERSONA.quota_reached'),
        UserErrorCode.personaQuotaReached,
      );
      expect(UserErrorCode.personaQuotaReached.httpStatus, 400);
      expect(UserErrorCode.personaQuotaReached.recoveryAction, 'surface');
    });

    test('圈号系统分配只读:400 surface,不支持手动修改', () {
      expect(
        UserErrorCode.fromCode('USER.PERSONA.handle_readonly'),
        UserErrorCode.personaHandleReadonly,
      );
      expect(UserErrorCode.personaHandleReadonly.httpStatus, 400);
      expect(UserErrorCode.personaHandleReadonly.recoveryAction, 'surface');
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.PERSONA)', () {
    test('quota_reached 响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.personaQuotaReached.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.personaQuotaReached.code,
          origin: 'user',
          kind: 'validation',
          nature: 'requiresUserAction',
          businessObject: 'persona',
          functionModule: 'user',
          userMessage: UserErrorCode.personaQuotaReached.defaultMessageZh,
          recoveryAction: UserErrorCode.personaQuotaReached.recoveryAction,
          disruptionLevel: UserErrorCode.personaQuotaReached.disruptionLevel,
        ),
        requestPath: '/user/personas',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.personaQuotaReached.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'surface');
    });
  });
}
