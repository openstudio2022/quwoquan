import 'package:quwoquan_app/personal_assistant/sync/sync_adapter.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_mode.dart';
import 'package:quwoquan_app/personal_assistant/sync/sync_models.dart';

class CloudStubSyncAdapter implements AssistentSyncAdapter {
  const CloudStubSyncAdapter();

  @override
  Future<AssistentSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.cloudStub,
      resource: AssistentSyncResource.policy,
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
  Future<AssistentSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.cloudStub,
      resource: AssistentSyncResource.interactionEvents,
      message: 'Cloud stub accepted interaction events placeholder.',
      payload: <String, dynamic>{'count': events.length},
    );
  }

  @override
  Future<AssistentSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.cloudStub,
      resource: AssistentSyncResource.scorecards,
      message: 'Cloud stub accepted scorecards placeholder.',
      payload: <String, dynamic>{'count': scorecards.length},
    );
  }

  @override
  Future<AssistentSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    return AssistentSyncResult(
      success: true,
      mode: AssistentSyncMode.cloudStub,
      resource: AssistentSyncResource.memoryRecords,
      message: 'Cloud stub accepted memory records placeholder.',
      payload: <String, dynamic>{'count': memoryRecords.length},
    );
  }
}

