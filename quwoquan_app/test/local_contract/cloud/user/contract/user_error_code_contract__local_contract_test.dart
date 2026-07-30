import 'package:test/test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/user_errors.g.dart';

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
