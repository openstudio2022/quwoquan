import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/runtime/errors/generated/user/user_errors.g.dart';

import '../../../../../support/runtime/errors/error_chain_probe.dart'
    show canonicalRuntimeErrorBody;

/// USER.AUTH 登录会话链路错误码契约(含研究态身份)。
///
/// 断言值以 `lib/runtime/errors/generated/user/user_errors.g.dart` 为准:
/// fromCode 解析、httpStatus、recoveryAction 恢复语义三件套,
/// 并对代表码走 CloudErrorMapper 映射负例。
void main() {
  group('UserErrorCode — 登录同意与凭据契约(USER.AUTH)', () {
    test('未同意协议:400 surface,用户必须先勾选协议', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.consent_required'),
        UserErrorCode.consentRequired,
      );
      expect(UserErrorCode.consentRequired.httpStatus, 400);
      expect(UserErrorCode.consentRequired.recoveryAction, 'surface');
    });

    test('唯一登录方式不可解绑:400 surface', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.last_credential'),
        UserErrorCode.lastCredential,
      );
      expect(UserErrorCode.lastCredential.httpStatus, 400);
      expect(UserErrorCode.lastCredential.recoveryAction, 'surface');
    });

    test('验证码请求幂等冲突:409 surface,须重新获取验证码', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.otp_idempotency_conflict'),
        UserErrorCode.otpIdempotencyConflict,
      );
      expect(UserErrorCode.otpIdempotencyConflict.httpStatus, 409);
      expect(UserErrorCode.otpIdempotencyConflict.recoveryAction, 'surface');
    });
  });

  group('UserErrorCode — 运营商本机号码登录契约(USER.AUTH.carrier_*)', () {
    test('运营商能力不可用:503 fallback 到短信验证码', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.carrier_unavailable'),
        UserErrorCode.carrierUnavailable,
      );
      expect(UserErrorCode.carrierUnavailable.httpStatus, 503);
      expect(UserErrorCode.carrierUnavailable.recoveryAction, 'fallback');
    });

    test('运营商 token 失效:400 fallback 到短信验证码', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.carrier_token_invalid'),
        UserErrorCode.carrierTokenInvalid,
      );
      expect(UserErrorCode.carrierTokenInvalid.httpStatus, 400);
      expect(UserErrorCode.carrierTokenInvalid.recoveryAction, 'fallback');
    });

    test('运营商校验超时:504 retry', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.carrier_provider_timeout'),
        UserErrorCode.carrierProviderTimeout,
      );
      expect(UserErrorCode.carrierProviderTimeout.httpStatus, 504);
      expect(UserErrorCode.carrierProviderTimeout.recoveryAction, 'retry');
    });
  });

  group('UserErrorCode — 账号安全与研究态身份契约', () {
    test('账号安全校验不可用:503 retry 且带退避秒数', () {
      expect(
        UserErrorCode.fromCode('USER.AUTH.account_security_unavailable'),
        UserErrorCode.accountSecurityUnavailable,
      );
      expect(UserErrorCode.accountSecurityUnavailable.httpStatus, 503);
      expect(
        UserErrorCode.accountSecurityUnavailable.recoveryAction,
        'retry',
      );
      expect(
        UserErrorCode.accountSecurityUnavailable.recoveryAfterSeconds,
        greaterThan(0),
      );
      expect(UserErrorCode.accountSecurityUnavailable.recoveryAfterSeconds, 3);
    });

    test('研究态身份无效:403 surface', () {
      expect(
        UserErrorCode.fromCode('USER.USER.research_identity_invalid'),
        UserErrorCode.researchIdentityInvalid,
      );
      expect(UserErrorCode.researchIdentityInvalid.httpStatus, 403);
      expect(UserErrorCode.researchIdentityInvalid.recoveryAction, 'surface');
    });
  });

  group('UserErrorCode — CloudErrorMapper 映射负例(USER.AUTH)', () {
    test('consent_required 响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.consentRequired.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.consentRequired.code,
          origin: 'user',
          kind: 'validation',
          nature: 'requiresUserAction',
          businessObject: 'account_session',
          functionModule: 'user',
          userMessage: UserErrorCode.consentRequired.defaultMessageZh,
          recoveryAction: UserErrorCode.consentRequired.recoveryAction,
          disruptionLevel: UserErrorCode.consentRequired.disruptionLevel,
        ),
        requestPath: '/user/auth/login',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.consentRequired.code,
      );
      final recovery = exception.runtimeFailure.recovery;
      expect(recovery.isPresent, isTrue);
      expect(recovery.action, 'surface');
    });

    test('research_identity_invalid 响应解析为 typed user 域错误', () {
      final exception = CloudErrorMapper.fromStatusCode(
        UserErrorCode.researchIdentityInvalid.httpStatus,
        body: canonicalRuntimeErrorBody(
          code: UserErrorCode.researchIdentityInvalid.code,
          origin: 'user',
          kind: 'permission',
          nature: 'requiresUserAction',
          businessObject: 'account_session',
          functionModule: 'user',
          userMessage: UserErrorCode.researchIdentityInvalid.defaultMessageZh,
          recoveryAction: UserErrorCode.researchIdentityInvalid.recoveryAction,
          disruptionLevel:
              UserErrorCode.researchIdentityInvalid.disruptionLevel,
        ),
        requestPath: '/user/auth/research-identity',
      );

      expect(exception.domainErrorCode?.domain, 'user');
      expect(
        exception.domainErrorCode?.code,
        UserErrorCode.researchIdentityInvalid.code,
      );
      expect(exception.runtimeFailure.recovery.action, 'surface');
    });
  });
}
