// spec_ref: specs/feature-tree/runtime/runtime-assistant/context-grounded-answering/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/page_context/application/public/assistant_open_context.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('page-context');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote accepts one bounded structured page context',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final receipt = await api.personalization.reportPageContext(
        context: AssistantOpenContext(
          source: AssistantSource.profile,
          experienceLevel: AssistantExperienceLevel.returning,
          entityId: 'persona-$nonce',
          objectType: 'user.persona',
          hints: const <String, Object?>{'entry': 'profile_header'},
        ),
        userAction: 'opened_profile',
      );

      expect(receipt.accepted, isTrue);
      expect(receipt.contextKey, isNotEmpty);
      final expiresAt = DateTime.tryParse(receipt.expiresAt);
      expect(expiresAt, isNotNull);
      expect(expiresAt!.isAfter(DateTime.now().toUtc()), isTrue);

      final events = await api.telemetry.waitForEvents(minimumCount: 1);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        contains(AppCloudOperationIds.assistantPageContextReportPageContext),
      );
    },
  );
}
