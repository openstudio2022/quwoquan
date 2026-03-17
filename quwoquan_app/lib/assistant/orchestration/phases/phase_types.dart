import 'package:quwoquan_app/assistant/orchestration/state/agent_execution_state.dart';

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

  final dynamic request;
  final AgentExecutionState state;
  final String runId;
  final String traceId;
  final String sessionId;
  final void Function(dynamic event)? onTraceEvent;
}

/// Result from a phase; may contain updated state and/or a terminal response.
class PhaseResult {
  const PhaseResult({
    this.state,
    this.response,
  });

  final AgentExecutionState? state;
  final dynamic response;

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
  final dynamic response;
  final bool earlyExit;
}
