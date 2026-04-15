import 'package:quwoquan_app/assistant/orchestration/pipelines/assistant_pipeline_engine.dart'
    as phase_owner;
import 'package:quwoquan_app/assistant/orchestration/answer_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/response_materializer.dart';
import 'package:quwoquan_app/assistant/orchestration/pipelines/synthesis_pipeline.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_materializer.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/orchestration/state/execution_phase_snapshot.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

/// Synthesis: finalize answer and hydrate grounding state.
class SynthesisPhase implements Phase {
  /// Preferred pipeline-based constructor.
  SynthesisPhase({
    required SynthesisPipeline synthesisPipeline,
    required ResponseMaterializer responseMaterializer,
    AnswerOutcomeResolver? outcomeResolver,
    SynthesisRunner? runner,
  }) : _runner =
           runner ??
           SynthesisRunner(
             buildDraft: synthesisPipeline.buildDraft,
             materialize: responseMaterializer.materialize,
           ),
       _outcomeResolver = outcomeResolver;

  /// Legacy constructor for backward compatibility with tests.
  @Deprecated('Use the named-parameter pipeline constructor')
  SynthesisPhase.fromOwner(
    phase_owner.LocalPhaseExecutionOwner owner, {
    // ignore: deprecated_member_use_from_same_package
    SynthesisMaterializer? materializer,
    AnswerOutcomeResolver? outcomeResolver,
    SynthesisRunner? runner,
  }) : _runner =
           runner ??
           SynthesisRunner(
             buildDraft: owner.synthesizeDraftBridge,
             materialize:
                 materializer != null
                     ? materializer.materialize
                     : ResponseMaterializer(owner: owner).materialize,
           ),
       _outcomeResolver = outcomeResolver;

  final SynthesisRunner _runner;
  final AnswerOutcomeResolver? _outcomeResolver;

  @override
  String get phaseId => 'synthesis';

  @override
  Future<PhaseOutput> run(PhaseInput input) async {
    var synthesisDraft = input.state.synthesisDraft;
    var pendingResponse = input.state.pendingResponse;
    final snapshot = input.state.executionPhaseSnapshot;
    // ignore: deprecated_member_use_from_same_package
    final hasExecution = snapshot is ExecutionPhaseSuccess ||
        input.state.executionBridgeSnapshot.isNotEmpty;
    if (pendingResponse == null && hasExecution) {
      final request = input.request as AssistantRunRequest;
      // ignore: deprecated_member_use_from_same_package
      synthesisDraft = await _runner.buildDraft(
        request,
        executionSnapshot: input.state.executionBridgeSnapshot,
        onTraceEvent: input.onTraceEvent == null
            ? null
            : (event) => input.onTraceEvent!(event),
      );
      pendingResponse = await _runner.materialize(
        request,
        draft: synthesisDraft,
        onTraceEvent: input.onTraceEvent == null
            ? null
            : (event) => input.onTraceEvent!(event),
      );
    }
    if (pendingResponse == null) {
      return PhaseOutput(state: input.state);
    }
    final runArtifacts = pendingResponse.runArtifacts;
    final outcome = (_outcomeResolver ?? const AnswerOutcomeResolver()).resolve(
      structured: pendingResponse.structuredResponse,
      runArtifacts: runArtifacts,
      fallbackEvidenceLedger: input.state.evidenceLedger,
      fallbackAnswerEvidenceBindings: input.state.answerEvidenceBindings,
      fallbackEvidenceEvaluation: input.state.evidenceEvaluation,
      fallbackAggregationState: input.state.aggregationState,
      fallbackConversationStateDecision: input.state.conversationStateDecision,
      fallbackSynthesisReadiness: input.state.synthesisReadiness,
      fallbackSlotState: input.state.slotState,
      fallbackDomainPolicyBundle: input.state.domainPolicyBundle,
      fallbackJourney: input.state.journey,
    );
    return PhaseOutput(
      state: input.state.copyWith(
        synthesisDraft: synthesisDraft,
        pendingResponse: pendingResponse,
        previousRunArtifacts: runArtifacts ?? input.state.previousRunArtifacts,
        slotState: outcome.slotState,
        evidenceLedger: outcome.evidenceLedger,
        answerEvidenceBindings: outcome.answerEvidenceBindings,
        aggregationState: outcome.aggregationState,
        evidenceEvaluation: outcome.evidenceEvaluation,
        domainPolicyBundle: outcome.domainPolicyBundle,
        conversationStateDecision: outcome.conversationStateDecision,
        journey: outcome.journey,
        synthesisReadiness: outcome.synthesisReadiness,
      ),
    );
  }
}
