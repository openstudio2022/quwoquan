// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/auth-token-lifecycle/spec.md#gwt-002
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/four-environment-commercial-login-maturity/spec.md#gwt-001
// spec_ref: specs/feature-tree/user-identity-profile-relationship/onboarding-and-identity-entry/two-state-one-tap-login-commercial-login-entry/spec.md#gwt-003
// readiness_case: account_session_login_with_phone_app_local
// readiness_case: account_session_login_with_wechat_app_local
// readiness_case: account_session_login_with_alipay_app_local
// readiness_case: account_session_login_with_qq_app_local
// readiness_case: account_session_login_one_tap_app_local
// readiness_case: account_session_login_anonymous_app_local
// readiness_case: account_session_refresh_token_app_local
// readiness_case: account_session_logout_app_local

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/user_service/account/user_account/adapters/account_lifecycle_remote.dart';
import 'package:quwoquan_app/service/user_service/account/account_session/adapters/account_session_remote.dart';
import 'package:quwoquan_app/service/user_service/account/authentication_challenge/adapters/authentication_challenge_remote.dart';
import 'package:quwoquan_app/service/user_service/account/credential_binding/adapters/credential_binding_remote.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

void main() {
  test(
    'AccountSession login 与 lifecycle 子 Facet 只调用 generated client',
    () async {
      final executor = _RecordingExecutor(_responseFor);
      final client = GeneratedCloudOperationClient(executor);
      final login = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: _context,
      );
      final session = RemoteAccountSessionCommandWriter(
        client: client,
        invocationContext: _context,
      );

      final phoneGrant = await login.loginWithPhone(
        LoginWithPhoneCommand(
          phone: '13800000000',
          otpCode: '123456',
          deviceId: 'device-1',
          platform: 'ios',
          appVersion: '1.0.0',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      );
      final wechatOutcome = await login.loginWithWechat(
        LoginWithWechatCommand(
          wechatCode: 'wechat-code',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      );
      final alipayOutcome = await login.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: 'alipay-code',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      );
      final qqOutcome = await login.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: 'qq-code',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      );
      final oneTapGrant = await login.loginOneTap(
        LoginOneTapCommand(
          vendor: 'aliyun',
          carrierToken: 'carrier-token',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: 'agreement-current',
          privacyVersion: 'privacy-current',
        ),
      );
      final anonymousGrant = await login.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'install-1',
          deviceFingerprintHash: 'fingerprint-hash',
          platform: 'ios',
          appVersion: '1.0.0',
        ),
      );
      final refreshGrant = await session.refreshToken(
        RefreshTokenCommand(refreshToken: 'refresh-token'),
      );
      final logoutAck = await session.logout(
        LogoutCommand(refreshToken: 'refresh-token'),
      );

      expect(
        executor.calls.map((call) => call.operation.canonicalOperationId),
        <String>[
          AppCloudOperationIds.userAccountSessionLoginWithPhone,
          AppCloudOperationIds.userAccountSessionLoginWithWechat,
          AppCloudOperationIds.userAccountSessionLoginWithAlipay,
          AppCloudOperationIds.userAccountSessionLoginWithQq,
          AppCloudOperationIds.userAccountSessionLoginOneTap,
          AppCloudOperationIds.userAccountSessionLoginAnonymous,
          AppCloudOperationIds.userAccountSessionRefreshToken,
          AppCloudOperationIds.userAccountSessionLogout,
        ],
      );
      expect(executor.calls.first.payload.body, <String, Object?>{
        'phone': '13800000000',
        'otpCode': '123456',
        'deviceId': 'device-1',
        'platform': 'ios',
        'appVersion': '1.0.0',
        'agreementVersion': '2026-07',
        'privacyVersion': '2026-07',
      });
      expect(executor.calls[1].payload.body, <String, Object?>{
        'wechatCode': 'wechat-code',
        'deviceId': 'device-1',
        'platform': 'ios',
        'agreementVersion': '2026-07',
        'privacyVersion': '2026-07',
      });
      expect(executor.calls[2].payload.body, <String, Object?>{
        'alipayAuthCode': 'alipay-code',
        'deviceId': 'device-1',
        'platform': 'ios',
        'agreementVersion': '2026-07',
        'privacyVersion': '2026-07',
      });
      expect(executor.calls[3].payload.body, <String, Object?>{
        'qqAuthCode': 'qq-code',
        'deviceId': 'device-1',
        'platform': 'ios',
        'agreementVersion': '2026-07',
        'privacyVersion': '2026-07',
      });
      expect(executor.calls[4].payload.body, <String, Object?>{
        'vendor': 'aliyun',
        'carrierToken': 'carrier-token',
        'deviceId': 'device-1',
        'platform': 'ios',
        'agreementVersion': 'agreement-current',
        'privacyVersion': 'privacy-current',
      });
      expect(executor.calls[5].payload.body, <String, Object?>{
        'installId': 'install-1',
        'deviceFingerprintHash': 'fingerprint-hash',
        'platform': 'ios',
        'appVersion': '1.0.0',
      });
      expect(executor.calls[6].payload.body, <String, Object?>{
        'refreshToken': 'refresh-token',
      });
      expect(executor.calls[7].payload.body, <String, Object?>{
        'refreshToken': 'refresh-token',
      });
      expect(phoneGrant.ownerId, 'owner-1');
      expect(oneTapGrant.activePersona?.personaId, 'sub-1');
      expect(anonymousGrant.identityOrigin, 'phone');
      expect(
        <FederatedLoginOutcome>[wechatOutcome, alipayOutcome, qqOutcome].every(
          (outcome) =>
              outcome.status == FederatedLoginStatus.authenticated &&
              outcome.session?.ownerId == 'owner-1',
        ),
        isTrue,
      );
      expect(refreshGrant.accessToken, 'access-token-next');
      expect(refreshGrant.refreshToken, 'refresh-token-next');
      expect(logoutAck.revoked, isTrue);
      expect(
        executor.calls.every(
          (call) => call.context.clientPageId.startsWith('user.'),
        ),
        isTrue,
      );
      final anonymousLoginCall = executor.calls.singleWhere(
        (call) =>
            call.operation.canonicalOperationId ==
            AppCloudOperationIds.userAccountSessionLoginAnonymous,
      );
      final anonymousLogin = anonymousLoginCall.operation;
      expect(
        anonymousLogin.timeoutMilliseconds,
        greaterThanOrEqualTo(anonymousLogin.latencyP95Milliseconds),
      );
      expect(
        anonymousLoginCall.context.idempotencyKey,
        allOf(
          startsWith('login-anonymous-'),
          hasLength('login-anonymous-'.length + 64),
          isNot(contains('fingerprint-hash')),
          isNot(contains('install-1')),
        ),
        reason: '匿名登录必须让 metadata 声明的第二次尝试真正 replay-safe，且不能把设备标识写入请求头。',
      );
    },
  );

  test('Challenge 与 App CredentialBinding 命令保持 operation parity', () async {
    final executor = _RecordingExecutor(_responseFor);
    final client = GeneratedCloudOperationClient(executor);
    final challenge = RemoteAuthenticationChallengeCommandWriter(
      client: client,
      invocationContext: _context,
    );
    final credentials = RemoteAppCredentialBindingCommandWriter(
      client: client,
      invocationContext: _context,
    );

    await challenge.sendOtp(
      SendOtpCommand(
        phone: '13800000000',
        platform: OtpClientPlatform.ios,
        sourceOperation: 'bind_phone',
        bindingTicket: 'binding-ticket-1',
      ),
      idempotencyKey: 'account-identity-facets-otp-000001',
    );
    await challenge.createAlipayAuthorizationRequest(
      CreateAlipayAuthorizationRequestCommand(platform: 'ios'),
    );
    await challenge.resolveOneTapLoginHint(
      ResolveOneTapLoginHintCommand(
        vendor: 'aliyun',
        carrierToken: 'carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    );
    await credentials.bindPhoneCredential(
      BindPhoneCredentialCommand(phone: '13800000000', otpCode: '123456'),
    );
    await credentials.completeFederatedPhoneBinding(
      CompleteFederatedPhoneBindingCommand(
        bindingTicket: 'binding-ticket-1',
        phone: '13800000000',
        otpCode: '123456',
        challengeId: 'challenge-1',
        deviceId: 'device-1',
        platform: 'ios',
        appVersion: '1.0.0',
        agreementVersion: '2026-07',
        privacyVersion: '2026-07',
      ),
    );
    await credentials.bindCarrierPhoneCredential(
      BindCarrierPhoneCredentialCommand(
        vendor: 'aliyun',
        carrierToken: 'carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    );
    await credentials.unbindCredential(
      UnbindCredentialCommand(credentialType: 'carrier_phone'),
    );

    expect(
      executor.calls.map((call) => call.operation.canonicalOperationId),
      <String>[
        AppCloudOperationIds.userAuthenticationChallengeSendOtp,
        AppCloudOperationIds
            .userAuthenticationChallengeCreateAlipayAuthorizationRequest,
        AppCloudOperationIds.userAuthenticationChallengeResolveOneTapLoginHint,
        AppCloudOperationIds.userCredentialBindingBindPhoneCredential,
        AppCloudOperationIds.userCredentialBindingCompleteFederatedPhoneBinding,
        AppCloudOperationIds.userCredentialBindingBindCarrierPhoneCredential,
        AppCloudOperationIds.userCredentialBindingUnbindCredential,
      ],
    );
    expect(executor.calls[3].payload.body, <String, Object?>{
      'phone': '13800000000',
      'otpCode': '123456',
    });
    expect(executor.calls[4].payload.body, <String, Object?>{
      'bindingTicket': 'binding-ticket-1',
      'phone': '13800000000',
      'otpCode': '123456',
      'challengeId': 'challenge-1',
      'deviceId': 'device-1',
      'platform': 'ios',
      'appVersion': '1.0.0',
      'agreementVersion': '2026-07',
      'privacyVersion': '2026-07',
    });
    expect(executor.calls.last.payload.pathParameters, <String, String>{
      'credentialType': 'carrier_phone',
    });
  });

  test('CredentialBinding query contract 严格拒绝 SECRET 与别名字段', () {
    final slice = decodeListCredentialsSlice(<String, Object?>{
      'credentials': <Object?>[
        <String, Object?>{
          'id': 'credential-1',
          'credentialType': 'phone',
          'displayLabel': '138****0000',
          'isActive': true,
          'boundAt': '2026-07-20T00:00:00Z',
          'version': 1,
        },
      ],
    });

    expect(slice.credentials.single.credentialType, CredentialType.phone);
    expect(slice.credentials.single.boundAt.isUtc, isTrue);
    expect(
      encodeUserCredentialBindingListCredentialsGeneratedRequest(
        ListCredentialsQuery(),
      ).body,
      isNull,
    );
    expect(
      () => decodeListCredentialsSlice(<String, Object?>{
        'credentials': <Object?>[
          <String, Object?>{
            'id': 'credential-1',
            'credentialType': 'phone',
            'credentialKey': 'must-not-cross-wire',
            'displayLabel': '138****0000',
            'isActive': true,
            'boundAt': '2026-07-20T00:00:00Z',
            'version': 1,
          },
        ],
      }),
      throwsFormatException,
    );
    expect(
      () => decodeListCredentialsSlice(<Object?, Object?>{1: 'non-string-key'}),
      throwsFormatException,
    );
  });

  test('UserAccount CloseAccount 只调用 generated command 且严格解析终态回执', () async {
    final executor = _RecordingExecutor(_responseFor);
    final lifecycle = RemoteAccountLifecycleCommandWriter(
      client: GeneratedCloudOperationClient(executor),
      invocationContext: _context,
    );

    final result = await lifecycle.closeAccount(
      CloseAccountCommand(clientRequestId: 'close-request-1'),
    );

    expect(result.accountState, AccountState.closed);
    expect(result.closedAt, DateTime.utc(2026, 7, 20, 12));
    expect(result.idempotentReplay, isFalse);
    expect(executor.calls, hasLength(1));
    expect(
      executor.calls.single.operation.canonicalOperationId,
      AppCloudOperationIds.userUserAccountCloseAccount,
    );
    expect(executor.calls.single.payload.body, <String, Object?>{
      'clientRequestId': 'close-request-1',
    });
  });

  test('Remote 不吞 CloudException，RuntimeFailure 原样到调用边界', () async {
    final failure = CloudErrorMapper.fromStatusCode(
      401,
      requestPath: '/redacted',
    );
    final remote = RemoteAccountSessionCommandWriter(
      client: GeneratedCloudOperationClient(_FailingExecutor(failure)),
      invocationContext: _context,
    );

    await expectLater(
      remote.logout(LogoutCommand(refreshToken: 'revoked-token')),
      throwsA(
        isA<CloudException>()
            .having(
              (error) => identical(error, failure),
              'same instance',
              isTrue,
            )
            .having(
              (error) => error.runtimeFailure.kind,
              'runtimeFailure.kind',
              RuntimeFailureKind.auth,
            ),
      ),
    );
  });
}

CloudOperationInvocationContext _context(
  String clientPageId, {
  String? idempotencyKey,
}) => CloudOperationInvocationContext(
  surfaceId: 'login',
  clientPageId: clientPageId,
  idempotencyKey: idempotencyKey,
  actor: const CloudOperationActorContext(accountId: 'owner-1'),
);

Object? _responseFor(CloudOperationContract operation) {
  return switch (operation.canonicalOperationId) {
    AppCloudOperationIds.userAccountSessionRefreshToken => <String, Object?>{
      'accessToken': 'access-token-next',
      'refreshToken': 'refresh-token-next',
      'sessionRememberTtlSeconds': 2592000,
    },
    AppCloudOperationIds.userAccountSessionLogout => <String, Object?>{
      'revoked': true,
    },
    AppCloudOperationIds.userAuthenticationChallengeSendOtp =>
      <String, Object?>{
        'maskedPhone': '138****0000',
        'expiresInSeconds': 300,
        'deliveryStatus': 'queued',
        'retryAfterSeconds': 60,
        'requestId': 'otp-request-1',
        'challengeId': 'otp-challenge-1',
      },
    AppCloudOperationIds
        .userAuthenticationChallengeCreateAlipayAuthorizationRequest =>
      <String, Object?>{
        'authorizationPayload': 'signed-authorization',
        'expiresAt': '2026-07-20T01:00:00Z',
      },
    AppCloudOperationIds.userAuthenticationChallengeResolveOneTapLoginHint =>
      <String, Object?>{
        'state': 'ready',
        'maskedPhone': '138****0000',
        'registered': true,
        'expiresInSeconds': 120,
      },
    AppCloudOperationIds.userAccountSessionLoginWithWechat ||
    AppCloudOperationIds.userAccountSessionLoginWithAlipay ||
    AppCloudOperationIds.userAccountSessionLoginWithQq => <String, Object?>{
      'status': 'authenticated',
      'session': _authSessionResponse(),
      'expiresInSeconds': 300,
    },
    AppCloudOperationIds.userCredentialBindingCompleteFederatedPhoneBinding =>
      _authSessionResponse(),
    AppCloudOperationIds.userCredentialBindingBindPhoneCredential ||
    AppCloudOperationIds.userCredentialBindingBindCarrierPhoneCredential ||
    AppCloudOperationIds.userCredentialBindingUnbindCredential =>
      <String, Object?>{
        'credentialType': 'phone',
        'isActive': true,
        'version': 1,
        'idempotentReplay': false,
      },
    AppCloudOperationIds.userUserAccountCloseAccount => <String, Object?>{
      'accountState': 'closed',
      'closedAt': '2026-07-20T12:00:00Z',
      'idempotentReplay': false,
    },
    _ => _authSessionResponse(),
  };
}

Map<String, Object?> _authSessionResponse() => <String, Object?>{
  'accessToken': 'access-token',
  'refreshToken': 'refresh-token',
  'ownerId': 'owner-1',
  'accountState': 'active',
  'identityOrigin': 'phone',
  'logicalShard': 0,
  'anonymousRetentionPolicy': 'retained',
  'personaCount': 1,
  'sessionRememberTtlSeconds': 2592000,
  'activePersona': <String, Object?>{'personaId': 'sub-1'},
};

final class _RecordedCall {
  const _RecordedCall({
    required this.operation,
    required this.context,
    required this.payload,
  });

  final CloudOperationContract operation;
  final CloudOperationInvocationContext context;
  final CloudOperationRequestPayload payload;
}

final class _RecordingExecutor implements CloudOperationExecutor {
  _RecordingExecutor(this.responseFor);

  final Object? Function(CloudOperationContract operation) responseFor;
  final List<_RecordedCall> calls = <_RecordedCall>[];

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    final payload = requestEncoder();
    calls.add(
      _RecordedCall(operation: operation, context: context, payload: payload),
    );
    return responseDecoder(responseFor(operation));
  }
}

final class _FailingExecutor implements CloudOperationExecutor {
  const _FailingExecutor(this.error);

  final Object error;

  @override
  Future<TResponse> send<TResponse>(
    CloudOperationContract operation, {
    required CloudOperationInvocationContext context,
    required CloudOperationResponseDecoder<TResponse> responseDecoder,
    required CloudOperationRequestEncoder requestEncoder,
  }) async {
    throw error;
  }
}
