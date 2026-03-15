import 'package:quwoquan_app/assistant/internal_legacy/sync/sync_adapter.dart';
import 'package:quwoquan_app/assistant/internal_legacy/sync/sync_mode.dart';
import 'package:quwoquan_app/assistant/internal_legacy/sync/sync_models.dart';

class CloudStubSyncAdapter implements AssistantSyncAdapter {
  const CloudStubSyncAdapter();

  @override
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.policy,
      message: 'Cloud stub policy placeholder returned.',
      payload: <String, dynamic>{
        'policyVersionHint': policyVersionHint,
        'snapshot': <String, dynamic>{
          'version': 'cloud_stub_v1',
          'values': <String, dynamic>{},
        },
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.interactionEvents,
      message: 'Cloud stub accepted interaction events placeholder.',
      payload: <String, dynamic>{'count': events.length},
    );
  }

  @override
  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.scorecards,
      message: 'Cloud stub accepted scorecards placeholder.',
      payload: <String, dynamic>{'count': scorecards.length},
    );
  }

  @override
  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.cloudStub,
      resource: AssistantSyncResource.memoryRecords,
      message: 'Cloud stub accepted memory records placeholder.',
      payload: <String, dynamic>{'count': memoryRecords.length},
    );
  }
}

