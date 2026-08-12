// spec_ref: specs/feature-tree/assistant-run-learning/world-class-trinity-experience-baseline/skill-progressive-disclosure-routing/spec.md#gwt-003

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

const _officialSkillId = 'travel_companion';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('skill-catalog');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote returns one active official package consistently',
    () async {
      final api = harness!;
      final items = await api.skillCatalog.listSkillCatalog();
      final listed = items.singleWhere(
        (item) => item.skillId == _officialSkillId,
      );
      expect(listed.packageId, isNotEmpty);
      expect(listed.releaseDigest, startsWith('sha256:'));
      expect(listed.displayName, isNotEmpty);
      expect(listed.configurationSchemaDigest, startsWith('sha256:'));

      final detail = await api.skillCatalog.getSkillCatalogItem(
        skillId: _officialSkillId,
      );
      expect(detail.item.toJson(), listed.toJson());
      expect(detail.configurationSchema, isA<Map>());
      expect((detail.configurationSchema as Map)['type'], 'object');

      final events = await api.telemetry.waitForEvents(minimumCount: 2);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        containsAll(<String>[
          AppCloudOperationIds.assistantSkillCatalogListSkills,
          AppCloudOperationIds.assistantSkillCatalogGetSkillCatalogItem,
        ]),
      );
    },
  );
}
