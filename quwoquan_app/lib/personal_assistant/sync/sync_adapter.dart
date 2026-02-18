import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';

abstract class AssistentSyncAdapter {
  Future<AssistentSyncResult> pullPolicy({
    required String policyVersionHint,
  });

  Future<AssistentSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  });

  Future<AssistentSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  });

  Future<AssistentSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  });
}

