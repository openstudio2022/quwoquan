import 'package:quwoquan_app/assistant/orchestration/local_phase_execution_owner.dart'
    as phase_owner;
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Phase-side owner for turning a typed synthesis draft into the final response.
class SynthesisMaterializer {
  const SynthesisMaterializer(this._owner);

  final phase_owner.LocalPhaseExecutionOwner _owner;

  Future<AssistantRunResponse> materialize(
    AssistantRunRequest request, {
    required SynthesisDraft draft,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final structuredResponse = await _owner
        .materializeStructuredResponseFromDraft(
          request,
          draft: draft,
          onTraceEvent: onTraceEvent,
        );
    return AssistantRunResponse(
      finalText: draft.finalResult.finalText,
      traces: draft.finalResult.traces,
      runId: draft.runId,
      traceId: draft.traceId,
      degraded: draft.responseDegraded,
      structuredResponse: structuredResponse,
      profileUpdateProposal: draft.profileUpdateProposal,
    );
  }
}
