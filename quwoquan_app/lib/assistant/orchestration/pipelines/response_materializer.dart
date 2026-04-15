import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';

/// Typed replacement for `LocalPhaseExecutionOwner.materializeStructuredResponseFromDraft`
/// combined with the response assembly in `SynthesisMaterializer`.
///
/// During the transition period this delegates to the owner. Post-migration
/// the core logic (structured response construction, evidence binding,
/// journey enrichment) will live here directly with strong-typed inputs.
class ResponseMaterializer {
  const ResponseMaterializer({required LocalPhaseExecutionOwner owner})
      : _owner = owner;

  final LocalPhaseExecutionOwner _owner;

  Future<AssistantRunResponse> materialize(
    AssistantRunRequest request, {
    required SynthesisDraft draft,
    void Function(AssistantTraceEvent event)? onTraceEvent,
  }) async {
    final structuredResponse =
        await _owner.materializeStructuredResponseFromDraft(
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
