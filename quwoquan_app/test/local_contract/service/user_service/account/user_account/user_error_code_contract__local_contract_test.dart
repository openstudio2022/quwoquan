import 'package:test/test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

void main() {
  group('UserErrorCode — 常规契约', () {
    test('所有错误码存在且 code 非空', () {
      for (final e in UserErrorCode.values) {
        expect(
          e.code,
          isNotEmpty,
          reason: '${e.name} code should not be empty',
        );
        expect(
          e.defaultMessage,
          isNotEmpty,
          reason: '${e.name} defaultMessage should not be empty',
        );
        expect(
          e.httpStatus,
          greaterThan(0),
          reason: '${e.name} httpStatus should be > 0',
        );
      }
    });

    test('user/**/errors.yaml 聚合错误码均已覆盖', () {
      final codes = UserErrorCode.values
          .map((value) => value.code)
          .toList(growable: false);
      expect(codes.toSet(), hasLength(codes.length));
      for (final value in UserErrorCode.values) {
        expect(UserErrorCode.fromCode(value.code), value);
      }
      expect(
        UserErrorCode.contactDiscoveryRateLimited.code,
        'USER.CONTACT.rate_limited',
      );
      expect(
        UserErrorCode.alipayAuthFailed.code,
        'USER.AUTH.alipay_auth_failed',
      );
      expect(UserErrorCode.qqAuthFailed.code, 'USER.AUTH.qq_auth_failed');
      expect(
        UserErrorCode.socialProviderCancelled.code,
        'USER.AUTH.social_provider_cancelled',
      );
      expect(
        UserErrorCode.socialProviderUnavailable.code,
        'USER.AUTH.social_provider_unavailable',
      );
      expect(
        UserErrorCode.tooManyContacts.code,
        'USER.CONTACT.too_many_contacts',
      );
      expect(
        UserErrorCode.greetingAlreadyContact.code,
        'USER.GREETING.already_contact',
      );
      // B3 关系与个人投影：新对象错误码同源覆盖（invite_record 已删除）。
      expect(
        UserErrorCode.relationshipFollowBlocked.code,
        'USER.RELATIONSHIP.follow_blocked',
      );
      expect(
        UserErrorCode.subjectFollowInvalidSubjectType.code,
        'USER.SUBJECT_FOLLOW.invalid_subject_type',
      );
      expect(UserErrorCode.userNotFound.code, 'USER.USER.not_found');
      expect(UserErrorCode.unauthorized.code, 'USER.USER.unauthorized');
      expect(UserErrorCode.forbidden.code, 'USER.USER.forbidden');
      expect(UserErrorCode.invalidArgument.code, 'USER.USER.invalid_argument');
      expect(
        UserErrorCode.invalidCallRingtone.code,
        'USER.SETTING.invalid_call_ringtone',
      );
      expect(UserErrorCode.otpExpired.code, 'USER.AUTH.otp_expired');
      expect(UserErrorCode.personaNotFound.code, 'USER.PERSONA.not_found');
      expect(
        UserErrorCode.retiredPersonaGuard.code,
        'USER.PERSONA.retired_guard',
      );
      expect(
        UserErrorCode.primaryPersonaGuard.code,
        'USER.PERSONA.primary_guard',
      );
      expect(
        UserErrorCode.activePersonaGuard.code,
        'USER.PERSONA.active_guard',
      );
      expect(UserErrorCode.lastPersona.code, 'USER.PERSONA.last_persona');
      expect(
        UserErrorCode.personaHandleTaken.code,
        'USER.PERSONA.handle_taken',
      );
      expect(UserErrorCode.internalError.code, 'USER.SYSTEM.internal_error');
    });

    test('fromCode 反向查找正确', () {
      expect(
        UserErrorCode.fromCode('USER.USER.not_found'),
        UserErrorCode.userNotFound,
      );
      expect(
        UserErrorCode.fromCode('USER.GREETING.already_contact'),
        UserErrorCode.greetingAlreadyContact,
      );
      expect(
        UserErrorCode.fromCode('USER.SUBJECT_FOLLOW.invalid_subject_type'),
        UserErrorCode.subjectFollowInvalidSubjectType,
      );
      expect(
        UserErrorCode.fromCode('USER.SYSTEM.internal_error'),
        UserErrorCode.internalError,
      );
    });

    test('HTTP 状态码与 errors.yaml 一致', () {
      expect(UserErrorCode.contactDiscoveryRateLimited.httpStatus, 429);
      expect(UserErrorCode.tooManyContacts.httpStatus, 400);
      expect(UserErrorCode.greetingAlreadyContact.httpStatus, 409);
      expect(UserErrorCode.relationshipFollowBlocked.httpStatus, 403);
      expect(UserErrorCode.subjectFollowInvalidSubjectType.httpStatus, 400);
      expect(UserErrorCode.userNotFound.httpStatus, 404);
      expect(UserErrorCode.unauthorized.httpStatus, 401);
      expect(UserErrorCode.forbidden.httpStatus, 403);
      expect(UserErrorCode.invalidArgument.httpStatus, 400);
      expect(UserErrorCode.invalidCallRingtone.httpStatus, 400);
      expect(UserErrorCode.otpExpired.httpStatus, 400);
      expect(UserErrorCode.personaNotFound.httpStatus, 404);
      expect(UserErrorCode.retiredPersonaGuard.httpStatus, 400);
      expect(UserErrorCode.primaryPersonaGuard.httpStatus, 400);
      expect(UserErrorCode.activePersonaGuard.httpStatus, 400);
      expect(UserErrorCode.lastPersona.httpStatus, 400);
      expect(UserErrorCode.personaHandleTaken.httpStatus, 409);
      expect(UserErrorCode.internalError.httpStatus, 500);
    });
  });

  group('UserErrorCode — 单轨契约', () {
    test('fromCode 对未知 code 返回 null', () {
      expect(UserErrorCode.fromCode('NONEXISTENT.CODE'), isNull);
      expect(UserErrorCode.fromCode(''), isNull);
    });
  });

  group('UserErrorCode — 账号申诉与处置契约(USER.ACCOUNT)', () {
    test('申诉凭据三态:invalid 可重验、expired 下发即失效、consumed 一次性', () {
      expect(
        UserErrorCode.fromCode(
          'USER.ACCOUNT.account_appeal_credential_invalid',
        ),
        UserErrorCode.accountAppealCredentialInvalid,
      );
      expect(UserErrorCode.accountAppealCredentialInvalid.httpStatus, 400);
      expect(
        UserErrorCode.accountAppealCredentialInvalid.recoveryAction,
        'retry',
      );

      // 凭据过期属于「下发即失效」:410 Gone,恢复动作是重新验证身份。
      expect(
        UserErrorCode.fromCode(
          'USER.ACCOUNT.account_appeal_credential_expired',
        ),
        UserErrorCode.accountAppealCredentialExpired,
      );
      expect(UserErrorCode.accountAppealCredentialExpired.httpStatus, 410);
      expect(
        UserErrorCode.accountAppealCredentialExpired.recoveryAction,
        'retry',
      );

      // 凭据已使用是一次性资源冲突:重试同一凭据无意义,只能 surface。
      expect(
        UserErrorCode.fromCode(
          'USER.ACCOUNT.account_appeal_credential_consumed',
        ),
        UserErrorCode.accountAppealCredentialConsumed,
      );
      expect(UserErrorCode.accountAppealCredentialConsumed.httpStatus, 409);
      expect(
        UserErrorCode.accountAppealCredentialConsumed.recoveryAction,
        'surface',
      );
    });

    test('申诉 intake 三态:not_found/account_mismatch/claimed', () {
      expect(
        UserErrorCode.fromCode('USER.ACCOUNT.account_appeal_intake_not_found'),
        UserErrorCode.accountAppealIntakeNotFound,
      );
      expect(UserErrorCode.accountAppealIntakeNotFound.httpStatus, 404);
      expect(
        UserErrorCode.accountAppealIntakeNotFound.recoveryAction,
        'surface',
      );

      expect(
        UserErrorCode.fromCode(
          'USER.ACCOUNT.account_appeal_intake_account_mismatch',
        ),
        UserErrorCode.accountAppealIntakeAccountMismatch,
      );
      expect(UserErrorCode.accountAppealIntakeAccountMismatch.httpStatus, 409);
      expect(
        UserErrorCode.accountAppealIntakeAccountMismatch.recoveryAction,
        'surface',
      );

      expect(
        UserErrorCode.fromCode('USER.ACCOUNT.account_appeal_intake_claimed'),
        UserErrorCode.accountAppealIntakeClaimed,
      );
      expect(UserErrorCode.accountAppealIntakeClaimed.httpStatus, 409);
      expect(UserErrorCode.accountAppealIntakeClaimed.recoveryAction, 'surface');
    });

    test('申诉前置状态与幂等冲突均为 409 surface', () {
      expect(
        UserErrorCode.fromCode('USER.ACCOUNT.account_appeal_not_suspended'),
        UserErrorCode.accountAppealNotSuspended,
      );
      expect(UserErrorCode.accountAppealNotSuspended.httpStatus, 409);
      expect(UserErrorCode.accountAppealNotSuspended.recoveryAction, 'surface');

      expect(
        UserErrorCode.fromCode(
          'USER.ACCOUNT.account_appeal_idempotency_conflict',
        ),
        UserErrorCode.accountAppealIdempotencyConflict,
      );
      expect(UserErrorCode.accountAppealIdempotencyConflict.httpStatus, 409);
      expect(
        UserErrorCode.accountAppealIdempotencyConflict.recoveryAction,
        'surface',
      );
    });

    test('账号处置:决策无效 400、状态冲突 409,均 surface', () {
      expect(
        UserErrorCode.fromCode('USER.ACCOUNT.enforcement_decision_invalid'),
        UserErrorCode.accountEnforcementDecisionInvalid,
      );
      expect(UserErrorCode.accountEnforcementDecisionInvalid.httpStatus, 400);
      expect(
        UserErrorCode.accountEnforcementDecisionInvalid.recoveryAction,
        'surface',
      );

      expect(
        UserErrorCode.fromCode('USER.ACCOUNT.state_conflict'),
        UserErrorCode.accountStateConflict,
      );
      expect(UserErrorCode.accountStateConflict.httpStatus, 409);
      expect(UserErrorCode.accountStateConflict.recoveryAction, 'surface');
    });

    test('申诉限流:429 必须 retry 且带正退避秒数', () {
      expect(
        UserErrorCode.fromCode('USER.ACCOUNT.account_appeal_rate_limited'),
        UserErrorCode.accountAppealRateLimited,
      );
      expect(UserErrorCode.accountAppealRateLimited.httpStatus, 429);
      expect(UserErrorCode.accountAppealRateLimited.recoveryAction, 'retry');
      expect(
        UserErrorCode.accountAppealRateLimited.recoveryAfterSeconds,
        greaterThan(0),
      );
      expect(UserErrorCode.accountAppealRateLimited.recoveryAfterSeconds, 600);
    });

    test('CloudErrorMapper 负例:申诉限流响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.accountAppealRateLimited.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.accountAppealRateLimited.code,
          origin: 'user',
          kind: 'rateLimited',
          nature: 'transient',
          businessObject: 'user_account',
          functionModule: 'user',
          userMessage: UserErrorCode.accountAppealRateLimited.defaultMessageZh,
          recoveryAction: UserErrorCode.accountAppealRateLimited.recoveryAction,
          recoveryAfterSeconds:
              UserErrorCode.accountAppealRateLimited.recoveryAfterSeconds,
          disruptionLevel:
              UserErrorCode.accountAppealRateLimited.disruptionLevel,
        ),
        requestPath: '/user/account/appeal',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.accountAppealRateLimited.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'retry');
      expect(recovery.afterSeconds, 600);
    });
  });

  group('UserErrorCode — 邀请契约(USER.INVITATION)', () {
    test('邀请不存在/已过期:404 与 410,均 surface', () {
      expect(
        UserErrorCode.fromCode('USER.INVITATION.not_found'),
        UserErrorCode.invitationNotFound,
      );
      expect(UserErrorCode.invitationNotFound.httpStatus, 404);
      expect(UserErrorCode.invitationNotFound.recoveryAction, 'surface');

      // 过期邀请属于「下发即失效」:重试同一邀请无意义,只能 surface。
      expect(
        UserErrorCode.fromCode('USER.INVITATION.expired'),
        UserErrorCode.invitationExpired,
      );
      expect(UserErrorCode.invitationExpired.httpStatus, 410);
      expect(UserErrorCode.invitationExpired.recoveryAction, 'surface');
    });

    test('邀请状态迁移冲突:409 surface', () {
      expect(
        UserErrorCode.fromCode('USER.INVITATION.invalid_transition'),
        UserErrorCode.invitationInvalidTransition,
      );
      expect(UserErrorCode.invitationInvalidTransition.httpStatus, 409);
      expect(
        UserErrorCode.invitationInvalidTransition.recoveryAction,
        'surface',
      );
    });

    test('邀请每日限额:429 retry 且退避一天', () {
      expect(
        UserErrorCode.fromCode('USER.INVITATION.daily_limit_exceeded'),
        UserErrorCode.invitationDailyLimitExceeded,
      );
      expect(UserErrorCode.invitationDailyLimitExceeded.httpStatus, 429);
      expect(
        UserErrorCode.invitationDailyLimitExceeded.recoveryAction,
        'retry',
      );
      expect(
        UserErrorCode.invitationDailyLimitExceeded.recoveryAfterSeconds,
        greaterThan(0),
      );
      expect(
        UserErrorCode.invitationDailyLimitExceeded.recoveryAfterSeconds,
        86400,
      );
    });

    test('CloudErrorMapper 负例:过期邀请响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.invitationExpired.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.invitationExpired.code,
          origin: 'user',
          kind: 'validation',
          nature: 'permanent',
          businessObject: 'invitation',
          functionModule: 'user',
          userMessage: UserErrorCode.invitationExpired.defaultMessageZh,
          recoveryAction: UserErrorCode.invitationExpired.recoveryAction,
          disruptionLevel: UserErrorCode.invitationExpired.disruptionLevel,
        ),
        requestPath: '/user/invitations',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.invitationExpired.code,
      );
      expect(exception.runtimeFailure.recovery.action, 'surface');
    });
  });

  group('UserErrorCode — 异常/边界契约', () {
    test('defaultMessage 中文非空', () {
      expect(
        UserErrorCode.greetingAlreadyContact.defaultMessage,
        contains('正式私信'),
      );
      expect(
        UserErrorCode.relationshipFollowBlocked.defaultMessage,
        contains('关注'),
      );
      expect(
        UserErrorCode.contactDiscoveryRateLimited.defaultMessage,
        contains('通讯录'),
      );
      expect(UserErrorCode.userNotFound.defaultMessage, '用户不存在');
      expect(UserErrorCode.unauthorized.defaultMessage, '请先登录');
      expect(UserErrorCode.retiredPersonaGuard.defaultMessage, contains('退役'));
      expect(UserErrorCode.primaryPersonaGuard.defaultMessage, contains('主分身'));
      expect(UserErrorCode.activePersonaGuard.defaultMessage, contains('切换'));
      expect(UserErrorCode.lastPersona.defaultMessage, contains('最后一个账号'));
      expect(UserErrorCode.personaHandleTaken.defaultMessage, contains('分身号'));
    });
  });
}
