import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_boundary_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_draft.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/trace_events.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

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
    final structuredResponse = await _owner
        .materializeStructuredResponseFromDraft(
          request,
          draft: draft,
          onTraceEvent: onTraceEvent,
        );
    final materializedUnderstandingSnapshot = _materializeUnderstandingSnapshot(
      structuredResponse: structuredResponse,
      draft: draft,
    );
    final normalizedStructuredResponse = <String, dynamic>{
      ...structuredResponse,
      if (materializedUnderstandingSnapshot.isNotEmpty)
        assistantUnderstandingSnapshotField: materializedUnderstandingSnapshot,
      'assistantBoundaryOutcome': _boundaryOutcomeForDraft(draft).toJson(),
      'qualityMetrics': <String, dynamic>{
        'decisionParseSuccess': true,
        'heuristicFallbackUsed': false,
        'evidenceSufficient': true,
        ...((structuredResponse['qualityMetrics'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{}),
      },
    };
    return AssistantRunResponse(
      finalText: draft.finalResult.finalText,
      traces: draft.finalResult.traces,
      runId: draft.runId,
      traceId: draft.traceId,
      degraded: draft.responseDegraded,
      structuredResponse: normalizedStructuredResponse,
      profileUpdateProposal: draft.profileUpdateProposal,
    );
  }

  Map<String, dynamic> _materializeUnderstandingSnapshot({
    required Map<String, dynamic> structuredResponse,
    required SynthesisDraft draft,
  }) {
    final structuredSnapshot =
        structuredResponse[assistantUnderstandingSnapshotField] is Map
        ? normalizeRunArtifactsUnderstandingSnapshotJson(
            (structuredResponse[assistantUnderstandingSnapshotField] as Map)
                .cast<String, dynamic>(),
          )
        : const <String, dynamic>{};
    if (_hasUnderstandingSnapshotContent(structuredSnapshot)) {
      return structuredSnapshot;
    }
    return normalizeRunArtifactsUnderstandingSnapshotJson(
      draft.understandingSnapshot,
    );
  }

  bool _hasUnderstandingSnapshotContent(Map<String, dynamic> raw) {
    if (raw.isEmpty) return false;
    final parsed = RunArtifactsUnderstandingSnapshot.fromJson(raw);
    return parsed.intentSummary.trim().isNotEmpty ||
        parsed.userFacingSummary.trim().isNotEmpty ||
        parsed.retrievalDesignNarrative.trim().isNotEmpty ||
        parsed.concernPoints.isNotEmpty ||
        parsed.resolutionItems.isNotEmpty ||
        parsed.assumptions.isNotEmpty ||
        parsed.mismatchSignal.trim().isNotEmpty ||
        parsed.carryForwardFacts.isNotEmpty ||
        parsed.discardedAssumptions.isNotEmpty;
  }

  AssistantBoundaryOutcome _boundaryOutcomeForDraft(SynthesisDraft draft) {
    if (!draft.responseDegraded) {
      return const AssistantBoundaryOutcome.ok(
        boundary: 'assistant_turn',
        stage: 'finalize',
      );
    }
    return AssistantBoundaryOutcome(
      status: draft.finalResult.finalText.trim().isNotEmpty
          ? AssistantBoundaryStatus.partial
          : AssistantBoundaryStatus.failed,
      boundary: 'assistant_turn',
      stage: 'finalize',
      failure: draft.finalResult.runtimeFailure,
      disruptionLevel: draft.finalResult.finalText.trim().isNotEmpty
          ? UserDisruptionLevel.passiveIndicator
          : UserDisruptionLevel.inlineCard,
      canContinue: false,
      canAnswerPartially: draft.finalResult.finalText.trim().isNotEmpty,
    );
  }
}
