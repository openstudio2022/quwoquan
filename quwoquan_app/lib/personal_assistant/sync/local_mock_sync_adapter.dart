import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';

class LocalMockSyncAdapter implements AssistantSyncAdapter {
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
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.policy,
      message: 'Local mock policy loaded.',
      payload: <String, dynamic>{
        'policyVersionHint': policyVersionHint,
        'snapshot': policySnapshot,
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    interactionEvents.addAll(events);
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.interactionEvents,
      message: 'Local mock interaction events accepted.',
      payload: <String, dynamic>{
        'count': events.length,
        'total': interactionEvents.length,
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    this.scorecards.addAll(scorecards);
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.scorecards,
      message: 'Local mock scorecards accepted.',
      payload: <String, dynamic>{
        'count': scorecards.length,
        'total': this.scorecards.length,
      },
    );
  }

  @override
  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    this.memoryRecords.addAll(memoryRecords);
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.localMock,
      resource: AssistantSyncResource.memoryRecords,
      message: 'Local mock memory records accepted.',
      payload: <String, dynamic>{
        'count': memoryRecords.length,
        'total': this.memoryRecords.length,
      },
    );
  }
}

