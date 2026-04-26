import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

typedef ExecuteBridgeFromState =
    Future<ExecutionPhaseSnapshot> Function(
      AssistantRunRequest request, {
      required AgentExecutionState state,
      String? runId,
      String? traceId,
      void Function(AssistantTraceEvent event)? onTraceEvent,
    });

class ExecutionRunner {
  const ExecutionRunner({required this.executeBridgeFromState});

  final ExecuteBridgeFromState executeBridgeFromState;

  Future<PhaseOutput> run(PhaseInput input) async {
    final request = coerceAssistantRunRequest(input.request);
    final snapshot = await executeBridgeFromState(
      request,
      state: input.state,
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent == null
          ? null
          : (event) => input.onTraceEvent!(event),
    );
    return switch (snapshot) {
      ExecutionPhaseShortCircuit(:final response) => PhaseOutput(
        state: input.state.copyWith(
          pendingResponse: response,
          executionPhaseSnapshot: snapshot,
        ),
      ),
      ExecutionPhaseSuccess() => PhaseOutput(
        state: input.state.copyWith(
          executionPhaseSnapshot: snapshot,
          synthesisReadiness: snapshot.synthesisReadiness,
          understandingResult: snapshot.understandingResult,
          taskGraph: snapshot.taskGraph,
          orchestratorState: snapshot.orchestratorState,
          turnSynthesisState: snapshot.turnSynthesisState,
        ),
      ),
    };
  }
}
