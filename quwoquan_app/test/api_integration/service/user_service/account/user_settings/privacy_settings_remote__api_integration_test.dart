// spec_ref: specs/feature-tree/user-identity-profile-relationship/settings-and-device-token/notification-privacy-settings/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/user_api_contract_harness.dart';

void main() {
  late UserApiContractHarness harness;

  setUpAll(() async {
    harness = await UserApiContractHarness.create();
    await harness.loginDisposableAccount('privacy-settings');
  });
  tearDownAll(() => harness.close());

  test('privacy blockedKeywords 写入后可回读', () async {
    await harness.settingsCommands.updatePrivacySettings(
      UpdatePrivacySettingsCommand(
        blockedKeywords: const <String>['api_contract_kw'],
      ),
    );
    final settings = await harness.settingsReader.getPrivacySettings();
    expect(settings.blockedKeywords, contains('api_contract_kw'));
  });
}
