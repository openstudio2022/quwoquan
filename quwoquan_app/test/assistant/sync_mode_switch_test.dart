import 'package:quwoquan_app/assistant/internal_legacy/sync/cloud_stub_sync_adapter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/sync/local_mock_sync_adapter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/sync/sync_mode.dart';
import 'package:test/test.dart';

void main() {
  group('Sync mode and adapters', () {
    test('mode parser defaults to local_mock', () {
      expect(AssistantSyncModeParser.parse(''), equals(AssistantSyncMode.localMock));
      expect(
        AssistantSyncModeParser.parse('unknown'),
        equals(AssistantSyncMode.localMock),
      );
      expect(
        AssistantSyncModeParser.parse('cloud_stub'),
        equals(AssistantSyncMode.cloudStub),
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

    test('cloud stub adapter returns placeholder payload', () async {
      const adapter = CloudStubSyncAdapter();
      final pulled = await adapter.pullPolicy(policyVersionHint: 'v1');
      expect(pulled.success, isTrue);
      expect(pulled.mode, equals(AssistantSyncMode.cloudStub));
      expect(pulled.payload['snapshot'], isA<Map<String, dynamic>>());
    });

  });
}

