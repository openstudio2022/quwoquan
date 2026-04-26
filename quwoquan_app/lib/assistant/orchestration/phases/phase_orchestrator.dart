import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Orchestrates phases in order: bootstrap → understand → retrieval-design →
/// execution → synthesis → finalize.
///
/// Execution and synthesis already enter through typed pipeline phases; the
/// heavy bridge logic still lives in `assistant_pipeline_engine.dart` during the
/// migration window.
class PhaseOrchestrator {
  PhaseOrchestrator({required List<Phase> phases})
    : _phases = List<Phase>.unmodifiable(phases);

  final List<Phase> _phases;

  Future<PhaseOrchestratorResult> run(PhaseOrchestratorInput input) async {
    var state = input.initialState;
    dynamic response;

    for (final phase in _phases) {
      final narrative = _phaseNarrativeFor(phase.phaseId);
      if (narrative != null && phase.phaseId != 'bootstrap') {
        input.onTraceEvent?.call(
          _phaseNarrativeEvent(
            narrative: narrative,
            phaseId: phase.phaseId,
            runId: input.runId,
            traceId: input.traceId,
          ),
        );
      }
      final result = await phase.run(
        PhaseInput(
          request: input.request,
          state: state,
          runId: input.runId,
          traceId: input.traceId,
          sessionId: input.sessionId ?? 'default',
          onTraceEvent: input.onTraceEvent,
        ),
      );
      state = result.state ?? state;
      if (result.response != null) {
        response = result.response;
      }
      if (result.earlyExit) {
        break;
      }
    }

    return PhaseOrchestratorResult(state: state, response: response);
  }
}

class PhaseOrchestratorInput {
  const PhaseOrchestratorInput({
    required this.request,
    required this.runId,
    required this.traceId,
    this.sessionId,
    this.initialState = const AgentExecutionState(),
    this.onTraceEvent,
  });

  final dynamic request;
  final String runId;
  final String traceId;
  final String? sessionId;
  final AgentExecutionState initialState;
  final void Function(dynamic event)? onTraceEvent;
}

class PhaseOrchestratorResult {
  const PhaseOrchestratorResult({required this.state, this.response});

  final AgentExecutionState state;
  final dynamic response;
}

AssistantTraceEvent _phaseNarrativeEvent({
  required String narrative,
  required String phaseId,
  required String runId,
  required String traceId,
}) {
  return AssistantTraceEvent(
    type: AssistantTraceEventType.lifecycleStart,
    message: narrative,
    timestamp: DateTime.now(),
    data: <String, dynamic>{
      'phaseNarrative': true,
      'narrative': narrative,
      'phaseId': phaseId,
    },
    runId: runId,
    traceId: traceId,
    visibility: TraceVisibility.userVisible,
  );
}

String? _phaseNarrativeFor(String phaseId) {
  return null;
}
