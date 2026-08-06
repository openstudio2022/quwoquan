// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/settings-audit/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
    await harness.loginDisposableAccount('settings');
  });
  tearDownAll(() => harness.close());

  test('UserSettings notification/call roundtrip 与稳定命令回执', () async {
    final notification = await harness.settingsReader.getNotificationSettings();
    expect(notification.userId, harness.session.ownerId);
    expect(notification.updatedAt, isNotNull);

    final originalMarketing = notification.enableMarketing;
    final notificationReceipt = await harness.settingsCommands
        .updateNotificationSettings(
          UpdateNotificationSettingsCommand(
            enableMarketing: !originalMarketing,
          ),
        );
    expect(notificationReceipt.userId, harness.session.ownerId);
    expect(notificationReceipt.version, greaterThanOrEqualTo(1));

    final notificationReadback = await harness.settingsReader
        .getNotificationSettings();
    expect(notificationReadback.enableMarketing, !originalMarketing);

    final call = await harness.settingsReader.getCallSettings();
    expect(call.userId, harness.session.ownerId);
    expect(call.updatedAt, isNotNull);

    final originalVibration = call.enableCallVibration;
    final callReceipt = await harness.settingsCommands.updateCallSettings(
      UpdateCallSettingsCommand(enableCallVibration: !originalVibration),
    );
    expect(callReceipt.userId, harness.session.ownerId);
    expect(callReceipt.version, greaterThanOrEqualTo(1));
    final callReadback = await harness.settingsReader.getCallSettings();
    expect(callReadback.enableCallVibration, !originalVibration);

    await harness.settingsCommands.updateNotificationSettings(
      UpdateNotificationSettingsCommand(enableMarketing: originalMarketing),
    );
    await harness.settingsCommands.updateCallSettings(
      UpdateCallSettingsCommand(enableCallVibration: originalVibration),
    );
    final telemetryEvents = await harness.telemetry.waitForEvents(
      minimumCount: 1,
    );
    expect(telemetryEvents.every((event) => event.succeeded), isTrue);
  });
}
