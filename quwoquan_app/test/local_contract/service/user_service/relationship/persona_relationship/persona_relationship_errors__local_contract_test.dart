import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.RELATIONSHIP 关系操作错误码契约。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction 恢复语义三件套,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 关系操作契约(USER.RELATIONSHIP)', () {
    test('关系主体无效:400 surface', () {
      expect(
        UserErrorCode.fromCode('USER.RELATIONSHIP.invalid_pair'),
        UserErrorCode.relationshipInvalidPair,
      );
      expect(UserErrorCode.relationshipInvalidPair.httpStatus, 400);
      expect(UserErrorCode.relationshipInvalidPair.recoveryAction, 'surface');
    });

    test('目标用户不存在或不可关注:404 surface', () {
      expect(
        UserErrorCode.fromCode('USER.RELATIONSHIP.target_not_found'),
        UserErrorCode.relationshipTargetNotFound,
      );
      expect(UserErrorCode.relationshipTargetNotFound.httpStatus, 404);
      expect(
        UserErrorCode.relationshipTargetNotFound.recoveryAction,
        'surface',
      );
    });

    test('当前身份无权执行:403 surface', () {
      expect(
        UserErrorCode.fromCode('USER.RELATIONSHIP.actor_forbidden'),
        UserErrorCode.relationshipActorForbidden,
      );
      expect(UserErrorCode.relationshipActorForbidden.httpStatus, 403);
      expect(
        UserErrorCode.relationshipActorForbidden.recoveryAction,
        'surface',
      );
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.RELATIONSHIP)', () {
    test('actor_forbidden 响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.relationshipActorForbidden.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.relationshipActorForbidden.code,
          origin: 'user',
          kind: 'permission',
          nature: 'requiresUserAction',
          businessObject: 'persona_relationship',
          functionModule: 'user',
          userMessage:
              UserErrorCode.relationshipActorForbidden.defaultMessageZh,
          recoveryAction:
              UserErrorCode.relationshipActorForbidden.recoveryAction,
          disruptionLevel:
              UserErrorCode.relationshipActorForbidden.disruptionLevel,
        ),
        requestPath: '/user/relationships',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.relationshipActorForbidden.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'surface');
    });
  });
}
