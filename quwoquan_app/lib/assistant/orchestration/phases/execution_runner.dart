import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

typedef ExecuteBridgeFromState =
    Future<Map<String, dynamic>> Function(
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
    final executionSnapshot = await executeBridgeFromState(
      request,
      state: input.state,
      runId: input.runId,
      traceId: input.traceId,
      onTraceEvent: input.onTraceEvent == null
          ? null
          : (event) => input.onTraceEvent!(event),
    );
    final shortCircuitResponse =
        executionSnapshot['shortCircuitResponse'] as AssistantRunResponse?;
    if (shortCircuitResponse != null) {
      return PhaseOutput(
        state: input.state.copyWith(
          pendingResponse: shortCircuitResponse,
          executionBridgeSnapshot: const <String, dynamic>{},
        ),
      );
    }
    return PhaseOutput(
      state: input.state.copyWith(
        executionBridgeSnapshot: executionSnapshot,
        synthesisReadiness: executionSnapshot['synthesisReadiness'] as dynamic,
      ),
    );
  }
}
