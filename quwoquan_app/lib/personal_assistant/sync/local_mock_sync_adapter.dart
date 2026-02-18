import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';

class LocalMockSyncAdapter implements AssistentSyncAdapter {
  LocalMockSyncAdapter({
    this.policySnapshot = const <String, dynamic>{
      'version': 'local_mock_v1',
      'values': <String, dynamic>{},
    },
  });

  Map<String, dynamic> policySnapshot;
  final List<Map<String, dynamic>> interactionEvents = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> scorecards = <Map<String, dynamic>>[];
  final List<Map<String, dynamic>> memoryRecords = <Map<String, dynamic>>[];

  @override
  Future<AssistentSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.localMock,
      resource: AssistentSyncResource.policy,
      message: 'Local mock policy loaded.',
      payload: <String, dynamic>{
        'policyVersionHint': policyVersionHint,
        'snapshot': policySnapshot,
      },
    );
  }

  @override
  Future<AssistentSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    interactionEvents.addAll(events);
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.localMock,
      resource: AssistentSyncResource.interactionEvents,
      message: 'Local mock interaction events accepted.',
      payload: <String, dynamic>{
        'count': events.length,
        'total': interactionEvents.length,
      },
    );
  }

  @override
  Future<AssistentSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    this.scorecards.addAll(scorecards);
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.localMock,
      resource: AssistentSyncResource.scorecards,
      message: 'Local mock scorecards accepted.',
      payload: <String, dynamic>{
        'count': scorecards.length,
        'total': this.scorecards.length,
      },
    );
  }

  @override
  Future<AssistentSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    this.memoryRecords.addAll(memoryRecords);
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.localMock,
      resource: AssistentSyncResource.memoryRecords,
      message: 'Local mock memory records accepted.',
      payload: <String, dynamic>{
        'count': memoryRecords.length,
        'total': this.memoryRecords.length,
      },
    );
  }
}

