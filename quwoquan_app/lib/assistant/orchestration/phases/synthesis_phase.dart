import 'package:quwoquan_app/assistant/conversation/orchestration/agent_loop.dart'
    as legacy_agent;
import 'package:quwoquan_app/assistant/orchestration/answer_outcome_resolver.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_materializer.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/synthesis_runner.dart';
import 'package:quwoquan_app/assistant/orchestration/phases/phase_types.dart';
import 'package:quwoquan_app/assistant/protocol/run_request.dart';

/// Synthesis: finalize answer and hydrate grounding state for phase owners.
class SynthesisPhase implements Phase {
  SynthesisPhase(
    legacy_agent.PersonalAssistantAgentLoop legacy, {
    SynthesisMaterializer? materializer,
    AnswerOutcomeResolver? outcomeResolver,
    SynthesisRunner? runner,
  }) : _runner =
           runner ??
           SynthesisRunner(
             buildDraft: legacy.synthesizeDraftBridge,
             materialize:
                 (request, {required draft, onTraceEvent}) =>
                     (materializer ?? SynthesisMaterializer(legacy))
                         .materialize(
                           request,
                           draft: draft,
                           onTraceEvent: onTraceEvent,
                         ),
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
    if (pendingResponse == null &&
        input.state.executionBridgeSnapshot.isNotEmpty) {
      final request = input.request as AssistantRunRequest;
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
      fallbackProcessJournal: input.state.processJournal,
      fallbackLiveCursor: input.state.liveCursor,
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
        processJournal: outcome.processJournal,
        liveCursor: outcome.liveCursor,
        synthesisReadiness: outcome.synthesisReadiness,
      ),
    );
  }
}
