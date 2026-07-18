import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/user/auth_login_result_dto.g.dart';
import 'package:quwoquan_app/cloud/user/generated/prefab_user_metadata.g.dart';
import '../../../../support/fakes/test_auth_repository.dart';

void main() {
  test('测试专用 Auth double 的五种登录统一返回 metadata 当前身份', () async {
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

    final repository = TestAuthRepository();
    final results = <AuthLoginResultDto>[
      await repository.login(
        credentialType: 'phone',
        credentialKey: '18013813909',
        otpCode: '000000',
      ),
      await repository.loginOneTap(
        vendor: 'cmcc',
        carrierToken: 'test-carrier-token',
        deviceId: 'device-1',
        platform: 'ios',
        agreementVersion: '2026-07',
        privacyVersion: '2026-07',
      ),
      await repository.loginWechat(
        wechatCode: 'test-wechat-code',
        deviceId: 'device-1',
        platform: 'ios',
      ),
      await repository.loginQq(
        qqAuthCode: 'test-qq-code',
        deviceId: 'device-1',
        platform: 'ios',
      ),
      await repository.loginAlipay(
        alipayAuthCode: 'test-alipay-code',
        deviceId: 'device-1',
        platform: 'ios',
      ),
    ];

    for (final result in results) {
      expect(result.ownerId, expectedUserId);
      expect(result.activeSub?['subAccountId'], expectedSubAccountId);
    }
  });
}
