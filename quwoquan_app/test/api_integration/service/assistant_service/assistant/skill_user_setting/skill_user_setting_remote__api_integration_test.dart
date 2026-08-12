// spec_ref: specs/feature-tree/assistant-run-learning/skill-product-integration-platform/skill-user-lifecycle/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialSkillId = 'travel_companion';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('skill-user-setting');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote persists, replays and reads one schema-bound setting',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final detail = await api.skillCatalog.getSkillCatalogItem(
        skillId: _officialSkillId,
      );
      final digest = detail.item.configurationSchemaDigest;
      expect(digest, startsWith('sha256:'));
      expect(
        await api.skillUserSettings.listSkillUserSettings(),
        isNot(
          contains(
            isA<SkillUserSetting>().having(
              (setting) => setting.skillId,
              'skillId',
              _officialSkillId,
            ),
          ),
        ),
      );

      final requestId = 'skill-setting-disable-$nonce';
      final disabled = await api.skillUserSettings.putSkillUserSetting(
        skillId: _officialSkillId,
        status: SkillUserSettingStatus.disabled,
        configurationData: const <String, Object?>{},
        configurationSchemaDigest: digest,
        memoryPolicy: SkillMemoryPolicy.packageDefault,
        connectorConnectionRefs: const <String>[],
        expectedRevision: 0,
        clientRequestId: requestId,
      );
      expect(disabled.setting.accountId, api.session.ownerId);
      expect(disabled.setting.status, SkillUserSettingStatus.disabled);
      expect(disabled.setting.revision, greaterThan(0));

      final replayed = await api.skillUserSettings.putSkillUserSetting(
        skillId: _officialSkillId,
        status: SkillUserSettingStatus.disabled,
        configurationData: const <String, Object?>{},
        configurationSchemaDigest: digest,
        memoryPolicy: SkillMemoryPolicy.packageDefault,
        connectorConnectionRefs: const <String>[],
        expectedRevision: 0,
        clientRequestId: requestId,
      );
      expect(replayed.setting.toJson(), disabled.setting.toJson());
      expect(replayed.replayed, isTrue);

      final fetched = await api.skillUserSettings.getSkillUserSetting(
        skillId: _officialSkillId,
      );
      expect(fetched.toJson(), disabled.setting.toJson());
      final listed = await api.skillUserSettings.listSkillUserSettings();
      expect(
        listed.singleWhere((item) => item.skillId == _officialSkillId).toJson(),
        disabled.setting.toJson(),
      );

      final restored = await api.skillUserSettings.putSkillUserSetting(
        skillId: _officialSkillId,
        status: SkillUserSettingStatus.enabled,
        configurationData: const <String, Object?>{},
        configurationSchemaDigest: digest,
        memoryPolicy: SkillMemoryPolicy.packageDefault,
        connectorConnectionRefs: const <String>[],
        expectedRevision: disabled.setting.revision,
        clientRequestId: 'skill-setting-restore-$nonce',
      );
      expect(restored.setting.status, SkillUserSettingStatus.enabled);
      expect(restored.setting.revision, greaterThan(disabled.setting.revision));

      final readback = await api.skillUserSettings.getSkillUserSetting(
        skillId: _officialSkillId,
      );
      expect(readback.toJson(), restored.setting.toJson());

      final events = await api.telemetry.waitForEvents(minimumCount: 9);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        containsAll(<String>[
          AppCloudOperationIds.assistantSkillUserSettingPutSkillUserSetting,
          AppCloudOperationIds.assistantSkillUserSettingGetSkillUserSetting,
          AppCloudOperationIds.assistantSkillUserSettingListSkillUserSettings,
        ]),
      );
    },
  );
}
