import 'package:quwoquan_app/assistant/sync/domain/assistant_sync_adapter.dart';
import 'package:quwoquan_app/assistant/sync/domain/assistant_sync_mode.dart';
import 'package:quwoquan_app/assistant/sync/domain/assistant_sync_models.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';

class RemoteAssistantSyncAdapter implements AssistantSyncAdapter {
  const RemoteAssistantSyncAdapter({required AssistantRepository repository})
    : _repository = repository;

  final AssistantRepository _repository;

  @override
  Future<AssistantSyncResult> pullPolicy({
    required String policyVersionHint,
  }) async {
    final snapshot = await _repository.getPolicySnapshot(
      policyVersionHint: policyVersionHint,
    );
    return AssistantSyncResult(
      success: snapshot.version.trim().isNotEmpty,
      mode: AssistantSyncMode.remote,
      resource: AssistantSyncResource.policy,
      message: 'Remote assistant policy loaded.',
      payload: <String, dynamic>{
        'policyVersionHint': policyVersionHint,
        'snapshot': snapshot.toJson(),
      },
    );
  }

  @override
  Future<AssistantSyncResult> pushInteractionEvents({
    required List<Map<String, dynamic>> events,
  }) async {
    final ack = await _repository.reportInteractionEvents(
      events: events
          .map((m) => InteractionEvent.fromJson(m.cast<String, dynamic>()))
          .toList(growable: false),
    );
    return AssistantSyncResult(
      success: ack.accepted,
      mode: AssistantSyncMode.remote,
      resource: AssistantSyncResource.interactionEvents,
      message: 'Remote assistant interaction events synced.',
      payload: ack.toJson(),
    );
  }

  @override
  Future<AssistantSyncResult> pushScorecards({
    required List<Map<String, dynamic>> scorecards,
  }) async {
    final ack = await _repository.reportScorecards(
      scorecards: scorecards
          .map((m) => Scorecard.fromJson(m.cast<String, dynamic>()))
          .toList(growable: false),
    );
    return AssistantSyncResult(
      success: ack.accepted,
      mode: AssistantSyncMode.remote,
      resource: AssistantSyncResource.scorecards,
      message: 'Remote assistant scorecards synced.',
      payload: ack.toJson(),
    );
  }

  @override
  Future<AssistantSyncResult> syncMemoryRecords({
    required List<Map<String, dynamic>> memoryRecords,
  }) async {
    return AssistantSyncResult(
      success: true,
      mode: AssistantSyncMode.remote,
      resource: AssistantSyncResource.memoryRecords,
      message: 'Remote assistant memory records are server-managed.',
      payload: <String, dynamic>{'count': memoryRecords.length},
    );
  }
}
