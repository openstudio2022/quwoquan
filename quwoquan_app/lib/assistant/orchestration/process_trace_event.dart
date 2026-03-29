import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

AssistantTraceEvent buildSyntheticProcessTrace({
  required UserEventType type,
  required UserEventScope scope,
  required JourneyStageId stageId,
  ProcessStepId processStepId = ProcessStepId.unknown,
  required String runId,
  required String traceId,
  String message = '',
  String nodeId = '',
  String phaseId = '',
  String actionCode = '',
  String reasonCode = '',
  Map<String, dynamic> payload = const <String, dynamic>{},
}) {
  final enrichedPayload = <String, dynamic>{
    ...payload,
    'syntheticUserEvent': true,
    'userEventType': _userEventTypeWire(type),
    'userEventScope': _userEventScopeWire(scope),
    'stageId': stageId.wireName,
    if (processStepId != ProcessStepId.unknown)
      'processStepId': processStepId.wireName,
    if (nodeId.trim().isNotEmpty) 'nodeId': nodeId.trim(),
    if (phaseId.trim().isNotEmpty) 'phaseId': phaseId.trim(),
    if (actionCode.trim().isNotEmpty) 'actionCode': actionCode.trim(),
    if (reasonCode.trim().isNotEmpty) 'reasonCode': reasonCode.trim(),
  };
  final resolvedMessage =
      message.trim().isNotEmpty
      ? message.trim()
      : (payload['headline'] as String?)?.trim() ?? '';
  return AssistantTraceEvent(
    type: AssistantTraceEventType.lifecycleStart,
    message: resolvedMessage,
    timestamp: DateTime.now(),
    runId: runId,
    traceId: traceId,
    visibility: TraceVisibility.userVisible,
    data: enrichedPayload,
  );
}

String _userEventTypeWire(UserEventType type) {
  switch (type) {
    case UserEventType.processReplace:
      return 'process_replace';
    case UserEventType.processAppend:
      return 'process_append';
    case UserEventType.processCommit:
      return 'process_commit';
    case UserEventType.answerDelta:
      return 'answer_delta';
    case UserEventType.unknown:
      return 'unknown';
  }
}

String _userEventScopeWire(UserEventScope scope) {
  switch (scope) {
    case UserEventScope.root:
      return 'root';
    case UserEventScope.skill:
      return 'skill';
    case UserEventScope.aggregation:
      return 'aggregation';
    case UserEventScope.unknown:
      return 'unknown';
  }
}
