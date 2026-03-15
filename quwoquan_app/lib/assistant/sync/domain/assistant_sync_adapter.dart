import 'package:quwoquan_app/assistant/sync/domain/assistant_sync_models.dart';

abstract class AssistantSyncAdapter {
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  });

  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  });

  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  });

  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  });
}
