import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Typed replacement for `LocalPhaseExecutionOwner.executeBridgeFromState`.
///
/// During the transition period this delegates to the owner's bridge method.
/// Post-migration the owner dependency will be removed and the core logic
/// (template variable assembly, LLM call, evidence processing) will live here
/// directly.
class ExecutionPipeline {
  const ExecutionPipeline({required LocalPhaseExecutionOwner owner})
      : _owner = owner;

  final LocalPhaseExecutionOwner _owner;

  Future<ExecutionPhaseSnapshot> execute(
    AssistantRunRequest request, {
    required AgentExecutionState state,
    String? runId,
    String? traceId,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) {
    return _owner.executeBridgeFromState(
      request,
      state: state,
      runId: runId,
      traceId: traceId,
      onTraceEvent: onTraceEvent,
    );
  }
}
