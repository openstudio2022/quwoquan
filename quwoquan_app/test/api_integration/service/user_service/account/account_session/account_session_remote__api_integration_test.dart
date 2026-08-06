// spec_ref: specs/feature-tree/user-identity-profile-relationship/auth-profile-snapshot/spec.md#sit-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
    await harness.loginDisposableAccount('session');
  });
  tearDownAll(() => harness.close());

  test('匿名登录签发完整 AccountSession', () {
    expect(harness.session.accessToken, isNotEmpty);
    expect(harness.session.refreshToken, isNotEmpty);
    expect(harness.session.ownerId, isNotEmpty);
    expect(harness.session.activePersona?.personaId, isNotEmpty);
  });

  test('相同安装身份匿名登录幂等复用 Owner 与 Persona', () async {
    final original = harness.session;
    final replay = await harness.replayAnonymousLogin();

    expect(replay.ownerId, original.ownerId);
    expect(replay.activePersona?.personaId, original.activePersona?.personaId);
    expect(replay.accessToken, isNotEmpty);
    expect(replay.refreshToken, isNotEmpty);
  });

  test('Logout 吊销 refresh session 且返回稳定 ack', () async {
    final ack = await harness.accountSessions.logout(
      LogoutCommand(
        refreshToken: harness.session.refreshToken,
        deviceId: userApiContractDeviceId,
      ),
    );
    expect(ack.revoked, true);
  });
}
