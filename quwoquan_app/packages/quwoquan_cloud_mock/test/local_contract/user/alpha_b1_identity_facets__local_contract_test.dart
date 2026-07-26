import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_cloud_mock/quwoquan_cloud_mock_identity.dart';
import 'package:test/test.dart';

void main() {
  test('UserSettings alpha facet 的写回可由 named Reader 观察', () async {
    final facet = AlphaUserSettingsFacet();

    final before = await facet.getNotificationSettings();
    expect(before.enablePush, isTrue);

    await facet.updateNotificationSettings(
      const UpdateNotificationSettingsCommand(enablePush: false),
    );
    final after = await facet.getNotificationSettings();
    expect(after.enablePush, isFalse);
    expect(after.version, greaterThan(before.version));
  });

  test('CredentialBinding alpha facet 共享命令与脱敏 Slice 状态', () async {
    final facet = AlphaCredentialBindingWriter();

    await facet.bindPhoneCredential(
      BindPhoneCredentialCommand(
        phone: '13800000000',
        otpCode: '123456',
        displayLabel: '138****0000',
      ),
    );
    final bound = await facet.listCredentials(const ListCredentialsQuery());
    expect(bound.items, hasLength(1));
    expect(bound.items.single.displayLabel, '138****0000');

    await expectLater(
      facet.unbindCredential(UnbindCredentialCommand(credentialType: 'phone')),
      throwsA(isA<LastCredentialUnbindException>()),
    );

    await facet.bindCarrierPhoneCredential(
      BindCarrierPhoneCredentialCommand(
        vendor: 'alpha',
        carrierToken: 'carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    );
    await facet.unbindCredential(
      UnbindCredentialCommand(credentialType: 'phone'),
    );
    final unbound = await facet.listCredentials(const ListCredentialsQuery());
    expect(unbound.items, hasLength(1));
    expect(unbound.items.single.credentialType, 'carrier_phone');
  });

  test('Profile alpha command 返回递增版本的 typed snapshot', () async {
    final writer = AlphaProfileCommandWriter();
    final result = await writer.updateUserProfile(
      UpdateUserProfileCommand(nickname: '新昵称'),
    );

    expect(result.nickname, '新昵称');
    expect(result.nicknameCustomized, isTrue);
    expect(result.profileVersion, greaterThan(1));
  });
}
