import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';

class AssistantSyncGateway {
  AssistantSyncGateway(this._adapter, this._mode);

  final AssistantSyncAdapter _adapter;
  final AssistantSyncMode _mode;

  AssistantSyncMode get mode => _mode;

  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) {
    return _adapter.pullPolicy(policyVersionHint: policyVersionHint);
  }

  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) {
    return _adapter.pushInteractionEvents(events: events);
  }

  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) {
    return _adapter.pushScorecards(scorecards: scorecards);
  }

  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) {
    return _adapter.syncMemoryRecords(memoryRecords: memoryRecords);
  }
}

