import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/user_events.dart';
import 'package:quwoquan_app/assistant/orchestration/process_trace_event.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

class ProcessTimelineEmitter {
  ProcessTimelineEmitter({
    required this.runId,
    required this.traceId,
    required void Function(AssistantTraceEvent event)? onTraceEvent,
  }) : _onTraceEvent = onTraceEvent;

  final String runId;
  final String traceId;
  final void Function(AssistantTraceEvent event)? _onTraceEvent;
  final Set<ProcessStepId> _startedSteps = <ProcessStepId>{};

  void pushDelta({
    required ProcessStepId stepId,
    required UserEventScope scope,
    required String delta,
    String phaseId = '',
    String actionCode = '',
    String reasonCode = '',
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) {
    final text = delta.trim();
    if (text.isEmpty || _onTraceEvent == null) return;
    final type = _startedSteps.add(stepId)
        ? UserEventType.processReplace
        : UserEventType.processAppend;
    _onTraceEvent(
      buildSyntheticProcessTrace(
        type: type,
        scope: scope,
        stageId: assistantJourneyStageForProcessStep(stepId),
        processStepId: stepId,
        runId: runId,
        traceId: traceId,
        phaseId: phaseId,
        actionCode: actionCode,
        reasonCode: reasonCode,
        payload: <String, dynamic>{...payload, 'headline': text},
      ),
    );
  }

  void replace({
    required ProcessStepId stepId,
    required UserEventScope scope,
    String headline = '',
    String detail = '',
    String phaseId = '',
    String actionCode = '',
    String reasonCode = '',
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) {
    if (_onTraceEvent == null) return;
    _startedSteps.add(stepId);
    _onTraceEvent(
      buildSyntheticProcessTrace(
        type: UserEventType.processReplace,
        scope: scope,
        stageId: assistantJourneyStageForProcessStep(stepId),
        processStepId: stepId,
        runId: runId,
        traceId: traceId,
        phaseId: phaseId,
        actionCode: actionCode,
        reasonCode: reasonCode,
        payload: <String, dynamic>{
          ...payload,
          'headline': headline.trim(),
          'detail': detail.trim(),
        },
      ),
    );
  }

  void commit({
    required ProcessStepId stepId,
    required UserEventScope scope,
    String headline = '',
    String detail = '',
    String phaseId = '',
    String actionCode = '',
    String reasonCode = '',
    Map<String, dynamic> payload = const <String, dynamic>{},
  }) {
    if (_onTraceEvent == null) return;
    _startedSteps.add(stepId);
    _onTraceEvent(
      buildSyntheticProcessTrace(
        type: UserEventType.processCommit,
        scope: scope,
        stageId: assistantJourneyStageForProcessStep(stepId),
        processStepId: stepId,
        runId: runId,
        traceId: traceId,
        phaseId: phaseId,
        actionCode: actionCode,
        reasonCode: reasonCode,
        payload: <String, dynamic>{
          ...payload,
          'headline': headline.trim(),
          'detail': detail.trim(),
        },
      ),
    );
  }
}
