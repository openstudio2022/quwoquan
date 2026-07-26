import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock.dart';
import 'package:test/test.dart';

void main() {
  test('Alpha AccountSession 覆盖六路登录并执行 refresh rotation', () async {
    final facet = AlphaAccountSessionFacet();
    final AccountSessionLoginCommandWriter login = facet;
    final AccountSessionLifecycleCommandWriter session = facet;

    final phone = await login.loginWithPhone(
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
    final grants = <AuthSessionGrant>[
      phone,
      await login.loginWithWechat(
        LoginWithWechatCommand(
          wechatCode: 'wechat-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      ),
      await login.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: 'alipay-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      ),
      await login.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: 'qq-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      ),
      await login.loginOneTap(
        LoginOneTapCommand(
          vendor: 'aliyun',
          carrierToken: 'carrier-token',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: 'agreement-current',
          privacyVersion: 'privacy-current',
        ),
      ),
      await login.loginAnonymous(
        LoginAnonymousCommand(
          installId: 'install-1',
          deviceFingerprintHash: 'fingerprint-hash',
          platform: 'ios',
          appVersion: '1.0.0',
        ),
      ),
    ];

    expect(grants.map((grant) => grant.identityOrigin), <String>[
      'phone',
      'wechat',
      'alipay',
      'qq',
      'carrier_phone',
      'anonymous_device',
    ]);
    expect(grants.map((grant) => grant.refreshToken).toSet(), hasLength(6));
    expect(phone.accountHint?.maskedPhone, '138****0000');

    final rotated = await session.refreshToken(
      RefreshTokenCommand(refreshToken: phone.refreshToken),
    );
    await expectLater(
      session.refreshToken(
        RefreshTokenCommand(refreshToken: phone.refreshToken),
      ),
      throwsA(isA<AccountSessionTokenExpiredException>()),
    );
    expect(
      await session.logout(LogoutCommand(refreshToken: rotated.refreshToken)),
      isA<LogoutAck>().having((ack) => ack.revoked, 'revoked', isTrue),
    );
    await expectLater(
      session.refreshToken(
        RefreshTokenCommand(refreshToken: rotated.refreshToken),
      ),
      throwsA(isA<AccountSessionTokenExpiredException>()),
    );
  });

  test('Alpha AuthenticationChallenge 有状态且不回传 OTP 明文', () async {
    final AuthenticationChallengeCommandWriter facet =
        AlphaAuthenticationChallengeFacet();

    final firstOtp = await facet.sendOtp(
      SendOtpCommand(phone: '13800000000', sourceOperation: 'login'),
    );
    final secondOtp = await facet.sendOtp(
      SendOtpCommand(phone: '13800000000', sourceOperation: 'bind_phone'),
    );
    final authorization = await facet.createAlipayAuthorizationRequest(
      CreateAlipayAuthorizationRequestCommand(platform: 'ios'),
    );
    final firstHint = await facet.resolveOneTapLoginHint(
      ResolveOneTapLoginHintCommand(
        vendor: 'aliyun',
        carrierToken: 'carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    );
    final replayedHint = await facet.resolveOneTapLoginHint(
      ResolveOneTapLoginHintCommand(
        vendor: 'aliyun',
        carrierToken: 'carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    );

    expect(firstOtp.maskedPhone, '138****0000');
    expect(firstOtp.challengeId, isNot(secondOtp.challengeId));
    expect(firstOtp.deliveryStatus, 'queued');
    expect(authorization.authorizationPayload, startsWith('alpha-alipay-'));
    expect(replayedHint.providerRequestId, firstHint.providerRequestId);
    expect(firstHint.registered, isTrue);
  });

  test('Alpha CredentialBinding command/query 共享同一状态', () async {
    final facet = AlphaCredentialBindingWriter();
    final CredentialBindingCommandWriter command = facet;
    final CredentialBindingQuery query = facet;

    final phone = await command.bindPhoneCredential(
      BindPhoneCredentialCommand(phone: '13800000000', otpCode: '123456'),
    );
    final replayedPhone = await command.bindPhoneCredential(
      BindPhoneCredentialCommand(phone: '13800000000', otpCode: '123456'),
    );
    await command.bindCarrierPhoneCredential(
      BindCarrierPhoneCredentialCommand(
        vendor: 'aliyun',
        carrierToken: 'carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    );

    final beforeUnbind = await query.listCredentials(
      const ListCredentialsQuery(),
    );
    expect(beforeUnbind.items, hasLength(2));
    expect(beforeUnbind.items.map((item) => item.credentialType), <String>[
      'carrier_phone',
      'phone',
    ]);
    expect(
      beforeUnbind.items
          .singleWhere((item) => item.credentialType == 'phone')
          .displayLabel,
      '138****0000',
    );
    expect(replayedPhone.idempotentReplay, isTrue);
    expect(replayedPhone.version, phone.version);

    final unbound = await command.unbindCredential(
      UnbindCredentialCommand(credentialType: 'carrier_phone'),
    );
    final afterUnbind = await query.listCredentials(
      const ListCredentialsQuery(),
    );
    expect(unbound.isActive, isFalse);
    expect(afterUnbind.items.single.credentialType, 'phone');
    await expectLater(
      command.unbindCredential(
        UnbindCredentialCommand(credentialType: 'carrier_phone'),
      ),
      throwsA(isA<CredentialBindingNotFoundException>()),
    );
    await expectLater(
      command.unbindCredential(
        UnbindCredentialCommand(credentialType: 'phone'),
      ),
      throwsA(isA<LastCredentialUnbindException>()),
    );
  });
}
