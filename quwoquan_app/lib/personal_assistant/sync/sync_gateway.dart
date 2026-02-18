import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';

class AssistentSyncGateway {
  AssistentSyncGateway(this._adapter, this._mode);

  final AssistentSyncAdapter _adapter;
  final AssistentSyncMode _mode;

  AssistentSyncMode get mode => _mode;

  Future<AssistentSyncResult> pullPolicy({
    required String policyVersionHint,
  }) {
    return _adapter.pullPolicy(policyVersionHint: policyVersionHint);
  }

  Future<AssistentSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) {
    return _adapter.pushInteractionEvents(events: events);
  }

  Future<AssistentSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) {
    return _adapter.pushScorecards(scorecards: scorecards);
  }

  Future<AssistentSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) {
    return _adapter.syncMemoryRecords(memoryRecords: memoryRecords);
  }
}

