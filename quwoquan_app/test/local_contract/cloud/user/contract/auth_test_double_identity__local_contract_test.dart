import 'dart:io';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/user/generated/prefab_user_metadata.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart'
    show
        accountSessionCommandWriterProvider,
        appCredentialBindingCommandWriterProvider,
        authenticationChallengeCommandWriterProvider,
        credentialBindingQueryProvider;
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/fakes/test_auth_facets.dart';

void main() {
  test('测试专用对象 Facet 可逐一 override 且五种登录返回 metadata 当前身份', () async {
    final originalDirectory = Directory.current;
    const expectedUserId = PrefabUserMetadata.currentUserId;
    const expectedSubAccountId = PrefabUserMetadata.currentSubAccountId;
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

    final results = <AuthSessionGrant>[
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
      await accountSession.loginWithWechat(
        LoginWithWechatCommand(
          wechatCode: 'test-wechat-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      ),
      await accountSession.loginWithQq(
        LoginWithQqCommand(
          qqAuthCode: 'test-qq-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      ),
      await accountSession.loginWithAlipay(
        LoginWithAlipayCommand(
          alipayAuthCode: 'test-alipay-code',
          deviceId: 'device-1',
          platform: 'ios',
        ),
      ),
    ];

    for (final result in results) {
      expect(result.ownerId, expectedUserId);
      expect(result.activeSub?.subAccountId, expectedSubAccountId);
    }

    final otp = await challenge.sendOtp(SendOtpCommand(phone: '18013813909'));
    expect(otp.maskedPhone, '180****3909');

    final binding = await credentialWriter.bindPhoneCredential(
      BindPhoneCredentialCommand(phone: '18013813909', otpCode: '000000'),
    );
    expect(binding.credentialType, 'phone');
    expect(binding.isActive, isTrue);

    final credentials = await credentialQuery.listCredentials(
      const ListCredentialsQuery(),
    );
    expect(credentials.items.single.credentialType, 'phone');
    expect(credentials.items.single.displayLabel, '180****3909');
  });
}
