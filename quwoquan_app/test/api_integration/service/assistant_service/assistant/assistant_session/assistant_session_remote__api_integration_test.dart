// spec_ref: specs/feature-tree/assistant-run-learning/assistant-runtime-foundation/assistant-object-runtime/spec.md#gwt-001

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/runtime/api_contract/assistant_api_contract_harness.dart';

void main() {
  AssistantApiContractHarness? harness;

  setUpAll(() async {
    harness = await AssistantApiContractHarness.create('assistant-session');
  });
  tearDownAll(() => harness?.close());

  test(
    'production Remote creates, replays, gets and lists one owner session',
    () async {
      final api = harness!;
      final nonce = DateTime.now().toUtc().microsecondsSinceEpoch.toString();
      final requestId = 'assistant-session-create-$nonce';
      final summary = 'api-integration-$nonce';

      final created = await api.sessionRun.createAssistantSession(
        summary: summary,
        clientRequestId: requestId,
      );
      expect(created.sessionId, isNotEmpty);
      expect(created.userId, api.session.ownerId);
      expect(created.summary, summary);
      expect(created.state, 'active');

      final replayed = await api.sessionRun.createAssistantSession(
        summary: summary,
        clientRequestId: requestId,
      );
      expect(replayed.toJson(), created.toJson());

      final fetched = await api.sessionRun.getAssistantSession(
        sessionId: created.sessionId,
      );
      expect(fetched.toJson(), created.toJson());

      final page = await api.sessionRun.listAssistantSessions();
      expect(
        page.items
            .singleWhere((item) => item.sessionId == created.sessionId)
            .toJson(),
        created.toJson(),
      );

      final events = await api.telemetry.waitForEvents(minimumCount: 4);
      expect(events.every((event) => event.succeeded), isTrue);
      expect(
        events.map((event) => event.canonicalOperationId),
        containsAll(<String>[
          AppCloudOperationIds.assistantAssistantSessionCreateAssistantSession,
          AppCloudOperationIds.assistantAssistantSessionGetAssistantSession,
          AppCloudOperationIds.assistantAssistantSessionListAssistantSessions,
        ]),
      );
    },
  );
}
