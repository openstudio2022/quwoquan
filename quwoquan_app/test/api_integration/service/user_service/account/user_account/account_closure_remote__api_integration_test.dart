// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/account-lifecycle-self-service-account-closure/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/errors/cloud_exception.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
  });
  tearDownAll(() => harness.close());

  test('CloseAccount 返回不可逆终态并拒绝 refresh 与旧 access', () async {
    final closingSession = await harness.loginDisposableAccount('close');
    final result = await harness.accountLifecycle.closeAccount(
      CloseAccountCommand(
        clientRequestId:
            'close-${DateTime.now().microsecondsSinceEpoch.toString()}',
      ),
    );

    expect(result.accountState, 'closed');
    expect(result.closedAt.isUtc, isTrue);
    expect(result.idempotentReplay, isFalse);
    await expectLater(
      harness.accountSessions.refreshToken(
        RefreshTokenCommand(refreshToken: closingSession.refreshToken),
      ),
      throwsA(isA<CloudException>()),
    );
    await expectLater(
      harness.settingsReader.getNotificationSettings(),
      throwsA(
        isA<CloudException>().having(
          (error) => error.code,
          'canonical account security error',
          anyOf('USER.AUTH.account_deleted', 'USER.AUTH.token_stale'),
        ),
      ),
    );
    final telemetryEvents = await harness.telemetry.waitForEvents(
      minimumCount: 1,
    );
    expect(telemetryEvents.every((event) => event.succeeded), isFalse);
  });
}
