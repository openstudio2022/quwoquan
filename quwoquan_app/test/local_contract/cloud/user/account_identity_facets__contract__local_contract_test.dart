import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/remote/user/account/account_lifecycle_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/account_session/account_session_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/authentication_challenge/authentication_challenge_remote.dart';
import 'package:quwoquan_app/cloud/remote/user/credential_binding/credential_binding_remote.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
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

      await login.loginWithPhone(
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
      await login.loginWithWechat(
        LoginWithWechatCommand(
          wechatCode: 'wechat-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      );
      await login.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: 'alipay-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      );
      await login.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: 'qq-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      );
      await login.loginOneTap(
        LoginOneTapCommand(
          vendor: 'aliyun',
          carrierToken: 'carrier-token',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: 'agreement-current',
          privacyVersion: 'privacy-current',
        ),
      );
      await login.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'install-1',
          deviceFingerprintHash: 'fingerprint-hash',
          platform: 'ios',
          appVersion: '1.0.0',
        ),
      );
      await session.refreshToken(
        RefreshTokenCommand(refreshToken: 'refresh-token'),
      );
      await session.logout(LogoutCommand(refreshToken: 'refresh-token'));

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
      SendOtpCommand(phone: '13800000000', sourceOperation: 'bind_phone'),
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
        AppCloudOperationIds.userCredentialBindingBindCarrierPhoneCredential,
        AppCloudOperationIds.userCredentialBindingUnbindCredential,
      ],
    );
    expect(executor.calls[3].payload.body, <String, Object?>{
      'phone': '13800000000',
      'otpCode': '123456',
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

    expect(slice.items.single.credentialType, 'phone');
    expect(slice.items.single.boundAt.isUtc, isTrue);
    expect(
      encodeListCredentialsQuery(const ListCredentialsQuery()).body,
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
      () =>
          decodeCredentialBindingView(<Object?, Object?>{1: 'non-string-key'}),
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
      const CloseAccountCommand(clientRequestId: 'close-request-1'),
    );

    expect(result.accountState, 'closed');
    expect(result.closedAt, '2026-07-20T12:00:00Z');
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

CloudOperationInvocationContext _context(String clientPageId) =>
    CloudOperationInvocationContext(
      surfaceId: 'login',
      clientPageId: clientPageId,
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
    _ => <String, Object?>{
      'accessToken': 'access-token',
      'refreshToken': 'refresh-token',
      'ownerId': 'owner-1',
    },
  };
}

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
