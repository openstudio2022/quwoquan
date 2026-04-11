import 'package:quwoquan_app/assistant/sync/assistant_sync.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:test/test.dart';

void main() {
  group('Sync mode and adapters', () {
    test('mode parser maps auto-fallback values correctly', () {
      expect(
        AssistantSyncModeParser.parse(''),
        equals(AssistantSyncMode.localMock),
      );
      expect(
        AssistantSyncModeParser.parse('unknown'),
        equals(AssistantSyncMode.localMock),
      );
      expect(
        AssistantSyncModeParser.parse('cloud_stub'),
        equals(AssistantSyncMode.remote),
      );
      expect(
        AssistantSyncModeParser.parse('remote'),
        equals(AssistantSyncMode.remote),
      );
    });

    test('local mock adapter stores pushed payloads', () async {
      final adapter = LocalMockSyncAdapter();
      final pushEvents = await adapter.pushInteractionEvents(
        events: <Map<String, dynamic>>[
          <String, dynamic>{'eventId': 'e1'},
        ],
      );
      final pushScores = await adapter.pushScorecards(
        scorecards: <Map<String, dynamic>>[
          <String, dynamic>{'scoreId': 's1'},
        ],
      );
      expect(pushEvents.success, isTrue);
      expect(pushScores.success, isTrue);
      expect(adapter.interactionEvents.length, equals(1));
      expect(adapter.scorecards.length, equals(1));
    });

    test('remote adapter delegates to repository', () async {
      final adapter = RemoteAssistantSyncAdapter(
        repository: _FakeAssistantRepository(),
      );
      final pulled = await adapter.pullPolicy(policyVersionHint: 'v1');
      final pushed = await adapter.pushInteractionEvents(
        events: const <Map<String, dynamic>>[
          <String, dynamic>{'eventId': 'e1', 'runId': 'r1'},
        ],
      );
      expect(pulled.success, isTrue);
      expect(pulled.mode, equals(AssistantSyncMode.remote));
      expect(pulled.payload['snapshot'], isA<Map<String, dynamic>>());
      expect(pushed.success, isTrue);
      expect(pushed.payload['acceptedCount'], equals(1));
    });
  });
}

class _FakeAssistantRepository implements AssistantRepository {
  @override
  Future<AssistantPolicyView> getPolicySnapshot({
    String policyVersionHint = '',
  }) async {
    return AssistantPolicyView(
      version: policyVersionHint.isEmpty ? 'v1' : policyVersionHint,
      values: const <String, dynamic>{'learningSyncEnabled': true},
    );
  }

  @override
  Future<AssistantInteractionReportBatchAck> reportInteractionEvents({
    required List<InteractionEvent> events,
  }) async {
    return AssistantInteractionReportBatchAck(
      accepted: true,
      acceptedCount: events.length,
      count: events.length,
      resource: 'interaction_event_batch',
    );
  }

  @override
  Future<AssistantScorecardReportBatchAck> reportScorecards({
    required List<Scorecard> scorecards,
  }) async {
    return AssistantScorecardReportBatchAck(
      accepted: true,
      acceptedCount: scorecards.length,
      count: scorecards.length,
      resource: 'scorecard_batch',
    );
  }

  @override
  Future<AssistantSkillConsent> grantSkillConsent({
    required String skillId,
    String grantedScope = kPersonalContentAccessSkillId,
  }) async {
    return AssistantSkillConsent(
      skillId: skillId,
      grantedScope: grantedScope,
      granted: true,
      updatedAt: DateTime.now(),
    );
  }

  @override
  Future<List<AssistantUserMemoryView>> listAssistantMemories({
    int limit = 32,
  }) {
    return Future<List<AssistantUserMemoryView>>.value(
      const <AssistantUserMemoryView>[],
    );
  }

  @override
  Future<List<AssistantUserTaskView>> listAssistantTasks({
    int limit = 32,
    String? status,
  }) {
    return Future<List<AssistantUserTaskView>>.value(
      const <AssistantUserTaskView>[],
    );
  }

  @override
  Future<List<AssistantSkillConsent>> listConsents() {
    return Future<List<AssistantSkillConsent>>.value(
      const <AssistantSkillConsent>[],
    );
  }

  @override
  Future<List<AssistantSkillCatalogItemView>> listSkillCatalog({
    int limit = 64,
  }) {
    return Future<List<AssistantSkillCatalogItemView>>.value(
      const <AssistantSkillCatalogItemView>[],
    );
  }

  @override
  Future<void> revokeSkillConsent({required String skillId}) {
    return Future<void>.value();
  }

  @override
  Future<AssistantSearchResultView> searchXiaoquResults({
    required String query,
    String searchIntensity = 'balanced',
  }) {
    return Future<AssistantSearchResultView>.value(
      const AssistantSearchResultView(queryEcho: 'q'),
    );
  }
}
