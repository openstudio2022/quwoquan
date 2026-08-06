import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart'
    show
        accountSessionCommandWriterProvider,
        appCredentialBindingCommandWriterProvider,
        authenticationChallengeCommandWriterProvider,
        credentialBindingQueryProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/user_service/account/account_session/test_auth_facets.dart';
import '../../../../../support/service/user_service/account/user_account/user_account_resolver_typed_double.dart';

void main() {
  test('测试专用对象 Facet 可逐一 override 且五种登录返回 metadata 当前身份', () async {
    final originalDirectory = Directory.current;
    final expectedUserId = FixtureUserResolver.currentUserVariantUserId;
    final expectedPersonaId = FixtureUserResolver.currentUserVariantPersonaId;
    final isolatedDirectory = await Directory.systemTemp.createTemp(
      'qwq_auth_test_double_',
    );
    addTearDown(() async {
      Directory.current = originalDirectory;
      await isolatedDirectory.delete(recursive: true);
    });
    Directory.current = isolatedDirectory;

    final facets = TestAuthFacets();
    final container = ProviderContainer(
      overrides: [
        accountSessionCommandWriterProvider.overrideWithValue(facets),
        authenticationChallengeCommandWriterProvider.overrideWithValue(facets),
        appCredentialBindingCommandWriterProvider.overrideWithValue(facets),
        credentialBindingQueryProvider.overrideWithValue(facets),
      ],
    );
    addTearDown(container.dispose);

    final accountSession = container.read(accountSessionCommandWriterProvider);
    final challenge = container.read(
      authenticationChallengeCommandWriterProvider,
    );
    final credentialWriter = container.read(
      appCredentialBindingCommandWriterProvider,
    );
    final credentialQuery = container.read(credentialBindingQueryProvider);
    expect(accountSession, same(facets));
    expect(challenge, same(facets));
    expect(credentialWriter, same(facets));
    expect(credentialQuery, same(facets));

    final directResults = <AuthSessionGrant>[
      await accountSession.loginWithPhone(
        LoginWithPhoneCommand(
          phone: '18013813909',
          otpCode: '000000',
          deviceId: 'device-1',
          platform: 'ios',
          appVersion: 'local-contract',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      ),
      await accountSession.loginOneTap(
        LoginOneTapCommand(
          vendor: 'cmcc',
          carrierToken: 'test-carrier-token',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      ),
    ];
    final federatedResults = <FederatedLoginOutcome>[
      await accountSession.loginWithWechat(
        LoginWithWechatCommand(
          wechatCode: 'test-wechat-code',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      ),
      await accountSession.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: 'test-qq-code',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      ),
      await accountSession.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: 'test-alipay-code',
          deviceId: 'device-1',
          platform: 'ios',
          agreementVersion: '2026-07',
          privacyVersion: '2026-07',
        ),
      ),
    ];

    final results = <AuthSessionGrant>[
      ...directResults,
      ...federatedResults.map((outcome) => outcome.session!),
    ];

    for (final result in results) {
      expect(result.ownerId, expectedUserId);
      expect(result.activePersona?.personaId, expectedPersonaId);
    }

    final otp = await challenge.sendOtp(SendOtpCommand(phone: '18013813909'));
    expect(otp.maskedPhone, '180****3909');

    final binding = await credentialWriter.bindPhoneCredential(
      BindPhoneCredentialCommand(phone: '18013813909', otpCode: '000000'),
    );
    expect(binding.credentialType, CredentialType.phone);
    expect(binding.isActive, isTrue);

    final completed = await credentialWriter.completeFederatedPhoneBinding(
      CompleteFederatedPhoneBindingCommand(
        bindingTicket: 'test-binding-ticket',
        phone: '18013813909',
        otpCode: '000000',
        challengeId: 'test-otp-challenge',
        deviceId: 'device-1',
        platform: 'ios',
        appVersion: 'local-contract',
        agreementVersion: '2026-07',
        privacyVersion: '2026-07',
      ),
    );
    expect(completed.ownerId, expectedUserId);

    final credentials = await credentialQuery.listCredentials(
      ListCredentialsQuery(),
    );
    expect(credentials.credentials.single.credentialType, CredentialType.phone);
    expect(credentials.credentials.single.displayLabel, '180****3909');
  });
}
