// spec_ref: specs/feature-tree/runtime/system-architecture-and-engineering-guide/app-cloud-business-object-commercial-closure/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('assistant-entry');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote returns one typed owner-scoped entry projection',
    () async {
      final api = harness!;
      final entry = await api.personalization.getAssistantEntry(
        context: const AssistantOpenContext(
          source: AssistantSource.home,
          experienceLevel: AssistantExperienceLevel.firstTime,
        ),
      );

      expect(entry.welcomeMessage, isNotEmpty);
      expect(entry.suggestionLines, isNotEmpty);
      expect(
        <String>{for (final chip in entry.chips) chip.chipId}.length,
        entry.chips.length,
      );
      expect(
        <String>{for (final action in entry.actions) action.actionId}.length,
        entry.actions.length,
      );

      final events = await api.telemetry.waitForEvents(minimumCount: 1);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        contains(
          AppCloudOperationIds.assistantAssistantEntryViewGetAssistantEntry,
        ),
      );
    },
  );
}
