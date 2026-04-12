import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Input passed to each phase.
class PhaseInput {
  const PhaseInput({
    required this.request,
    required this.state,
    required this.runId,
    required this.traceId,
    this.sessionId = 'default',
    this.onTraceEvent,
  });

  /// 通常为 [AssistantRunRequest]；亦允许 Map / 网关桥接对象（见 `coerceAssistantRunRequest`）。
  final Object? request;
  final AgentExecutionState state;
  final String runId;
  final String traceId;
  final String sessionId;
  final AssistantTraceEventSink? onTraceEvent;
}

/// Result from a phase; may contain updated state and/or a terminal response.
class PhaseResult {
  const PhaseResult({
    this.state,
    this.response,
  });

  final AgentExecutionState? state;
  final Object? response;

  bool get hasResponse => response != null;
}

/// Output from [Phase.run]; state may be updated, response terminates the pipeline.
class PhaseOutput {
  const PhaseOutput({
    this.state,
    this.response,
    this.earlyExit = false,
  });

  final AgentExecutionState? state;
  final Object? response;
  final bool earlyExit;
}
