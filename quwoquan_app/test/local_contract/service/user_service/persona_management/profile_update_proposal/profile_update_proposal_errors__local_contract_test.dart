import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.PROFILE_PROPOSAL 资料修改提案错误码契约。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction 恢复语义三件套,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 提案基础契约(USER.PROFILE_PROPOSAL)', () {
    test('提案不存在:404 surface', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE_PROPOSAL.not_found'),
        UserErrorCode.profileProposalNotFound,
      );
      expect(UserErrorCode.profileProposalNotFound.httpStatus, 404);
      expect(UserErrorCode.profileProposalNotFound.recoveryAction, 'surface');
    });

    test('提案内容无效:400 surface', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE_PROPOSAL.invalid_argument'),
        UserErrorCode.profileProposalInvalidArgument,
      );
      expect(UserErrorCode.profileProposalInvalidArgument.httpStatus, 400);
      expect(
        UserErrorCode.profileProposalInvalidArgument.recoveryAction,
        'surface',
      );
    });

    test('幂等冲突(重复请求内容不一致):409 surface', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE_PROPOSAL.idempotency_conflict'),
        UserErrorCode.profileProposalIdempotencyConflict,
      );
      expect(UserErrorCode.profileProposalIdempotencyConflict.httpStatus, 409);
      expect(
        UserErrorCode.profileProposalIdempotencyConflict.recoveryAction,
        'surface',
      );
    });
  });

  group('UserErrorCode — 提案状态冲突契约(USER.PROFILE_PROPOSAL)', () {
    test('提案状态已变化:409 retry,刷新后重试即可恢复', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE_PROPOSAL.invalid_transition'),
        UserErrorCode.profileProposalInvalidTransition,
      );
      expect(UserErrorCode.profileProposalInvalidTransition.httpStatus, 409);
      expect(
        UserErrorCode.profileProposalInvalidTransition.recoveryAction,
        'retry',
      );
    });

    test('资料版本冲突:409 retry,刷新后重新确认', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE_PROPOSAL.version_conflict'),
        UserErrorCode.profileProposalVersionConflict,
      );
      expect(UserErrorCode.profileProposalVersionConflict.httpStatus, 409);
      expect(
        UserErrorCode.profileProposalVersionConflict.recoveryAction,
        'retry',
      );
    });

    test('回滚窗口已结束:409 retry,刷新资料获取最新状态', () {
      expect(
        UserErrorCode.fromCode('USER.PROFILE_PROPOSAL.rollback_expired'),
        UserErrorCode.profileProposalRollbackExpired,
      );
      expect(UserErrorCode.profileProposalRollbackExpired.httpStatus, 409);
      expect(
        UserErrorCode.profileProposalRollbackExpired.recoveryAction,
        'retry',
      );
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.PROFILE_PROPOSAL)', () {
    test('rollback_expired 响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.profileProposalRollbackExpired.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.profileProposalRollbackExpired.code,
          origin: 'user',
          kind: 'validation',
          nature: 'transient',
          businessObject: 'profile_update_proposal',
          functionModule: 'user',
          userMessage:
              UserErrorCode.profileProposalRollbackExpired.defaultMessageZh,
          recoveryAction:
              UserErrorCode.profileProposalRollbackExpired.recoveryAction,
          disruptionLevel:
              UserErrorCode.profileProposalRollbackExpired.disruptionLevel,
        ),
        requestPath: '/user/profile-proposals',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.profileProposalRollbackExpired.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'retry');
    });
  });
}
