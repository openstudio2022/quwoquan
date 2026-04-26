import 'package:quwoquan_app/assistant/contracts/answer_boundary_policy.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_boundary_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_typed_turn_decision_contract.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/retrieval_outcome.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/reasoning/runtime/retrieval_outcome_resolver.dart';

class AnswerGateResolver {
  const AnswerGateResolver({
    RetrievalOutcomeResolver retrievalOutcomeResolver =
        const RetrievalOutcomeResolver(),
  }) : _retrievalOutcomeResolver = retrievalOutcomeResolver;

  final RetrievalOutcomeResolver _retrievalOutcomeResolver;

  bool canAnswerWithCurrentEvidence({
    required RetrievalOutcome retrievalOutcome,
    required AnswerBoundaryPolicy policy,
  }) {
    if (retrievalOutcome.degraded ||
        !retrievalOutcome.terminalPayloadComplete) {
      return false;
    }
    if (policy.evidenceRequired &&
        !_hasRequiredEvidencePayload(retrievalOutcome)) {
      return false;
    }
    return retrievalOutcome.retrievalReady;
  }

  AnswerGateDecision resolve({
    required RetrievalOutcome retrievalOutcome,
    AssistantTypedTurnDecision? typedTurnDecision,
    bool renderableAnswer = false,
    bool degraded = false,
    bool terminalPayloadComplete = true,
  }) {
    final effectiveTerminalPayloadComplete =
        terminalPayloadComplete && retrievalOutcome.terminalPayloadComplete;
    final effectiveDegraded = degraded || retrievalOutcome.degraded;
    final nextAction =
        typedTurnDecision?.nextActionWireName ??
        (retrievalOutcome.retrievalReady
            ? AssistantNextAction.answer.wireName
            : AssistantNextAction.abort.wireName);
    final answerEligibility =
        typedTurnDecision?.answerEligibilityWireName ??
        (retrievalOutcome.retrievalReady &&
                nextAction == AssistantNextAction.answer.wireName
            ? AnswerEligibility.eligible.wireName
            : AnswerEligibility.blocked.wireName);
    final retrievalReady =
        !effectiveDegraded &&
        effectiveTerminalPayloadComplete &&
        retrievalOutcome.retrievalReady;
    final hasRequiredEvidencePayload = _hasRequiredEvidencePayload(
      retrievalOutcome,
    );
    final boundedDeliveryAllowedByState =
        !effectiveDegraded &&
        renderableAnswer &&
        effectiveTerminalPayloadComplete &&
        nextAction == AssistantNextAction.answer.wireName &&
        answerEligibility == AnswerEligibility.eligible.wireName &&
        (!retrievalOutcome.evidenceRequired || hasRequiredEvidencePayload) &&
        typedTurnDecision?.finalAnswerModeType == FinalAnswerMode.boundedAnswer;
    final eligible =
        boundedDeliveryAllowedByState ||
        (renderableAnswer &&
            effectiveTerminalPayloadComplete &&
            nextAction == AssistantNextAction.answer.wireName &&
            answerEligibility == AnswerEligibility.eligible.wireName &&
            retrievalReady);
    final reasonCode = _reasonCode(
      retrievalOutcome: retrievalOutcome,
      eligible: eligible,
      retrievalReady: retrievalReady,
      renderableAnswer: renderableAnswer,
      degraded: effectiveDegraded,
      terminalPayloadComplete: effectiveTerminalPayloadComplete,
      nextAction: nextAction,
      boundedDeliveryAllowedByState: boundedDeliveryAllowedByState,
    );
    final reason = _reasonMessage(
      reasonCode: reasonCode,
      retrievalOutcome: retrievalOutcome,
      renderableAnswer: renderableAnswer,
      nextAction: nextAction,
    );
    return AnswerGateDecision(
      eligible: eligible,
      finalAnswerReady: eligible,
      reasonCode: reasonCode,
      reason: reason,
      nextAction: nextAction,
      answerEligibility: answerEligibility,
      renderable: renderableAnswer,
      retrievalReady: retrievalReady,
      terminalPayloadComplete: effectiveTerminalPayloadComplete,
      degraded: effectiveDegraded,
      incomplete: !effectiveTerminalPayloadComplete,
      coveredDimensions: retrievalOutcome.coveredDimensions,
      missingDimensions: retrievalOutcome.missingDimensions,
      authoritySatisfied: retrievalOutcome.authoritySatisfied,
      freshnessSatisfied: retrievalOutcome.freshnessSatisfied,
    );
  }

  AnswerGateDecision resolveFromStructured({
    required Map<String, dynamic> structured,
    RunArtifacts? runArtifacts,
    bool degraded = false,
  }) {
    final boundaryOutcome = _parseAssistantBoundaryOutcome(structured);
    final blockedByBoundary =
        boundaryOutcome?.status == AssistantBoundaryStatus.failed ||
        boundaryOutcome?.status == AssistantBoundaryStatus.blocked;
    final effectiveDegraded = degraded || blockedByBoundary;
    final retrievalOutcome = _retrievalOutcomeResolver.resolveFromStructured(
      structured: structured,
      runArtifacts: runArtifacts,
      degraded: effectiveDegraded,
    );
    final typedTurnDecision = _parseAssistantTypedTurnDecisionFromTypedState(
      structured,
    );
    final renderableAnswer = _hasRenderableAnswer(structured, runArtifacts);
    final derived = resolve(
      retrievalOutcome: retrievalOutcome,
      typedTurnDecision: typedTurnDecision,
      renderableAnswer: renderableAnswer,
      degraded: effectiveDegraded,
      terminalPayloadComplete:
          retrievalOutcome.terminalPayloadComplete && !blockedByBoundary,
    );
    final raw = (structured[assistantAnswerGateDecisionField] as Map?)
        ?.cast<String, dynamic>();
    if (raw != null && raw.isNotEmpty) {
      try {
        return _reconcileParsedGate(
          parsed: AnswerGateDecision.fromJson(raw),
          derived: derived,
        );
      } catch (_) {
        // Fall through to derived decision.
      }
    }
    return derived;
  }

  AssistantBoundaryOutcome? _parseAssistantBoundaryOutcome(
    Map<String, dynamic> structured,
  ) {
    final raw = (structured['assistantBoundaryOutcome'] as Map?)
        ?.cast<String, dynamic>();
    if (raw == null || raw.isEmpty) return null;
    try {
      return AssistantBoundaryOutcome.fromJson(raw);
    } catch (_) {
      return null;
    }
  }

  String _reasonCode({
    required RetrievalOutcome retrievalOutcome,
    required bool eligible,
    required bool retrievalReady,
    required bool renderableAnswer,
    required bool degraded,
    required bool terminalPayloadComplete,
    required String nextAction,
    required bool boundedDeliveryAllowedByState,
  }) {
    if (degraded) {
      return terminalPayloadComplete
          ? 'degraded_response'
          : 'incomplete_response';
    }
    if (!terminalPayloadComplete) return 'missing_terminal_payload';
    if (eligible) {
      return boundedDeliveryAllowedByState && !retrievalReady
          ? 'bounded_delivery'
          : 'evidence_ready';
    }
    if (!retrievalReady) {
      if (retrievalOutcome.evidenceRequired &&
          !_hasRequiredEvidencePayload(retrievalOutcome)) {
        return 'missing_required_evidence';
      }
      if (retrievalOutcome.authorityRequired &&
          !retrievalOutcome.authoritySatisfied) {
        return 'authority_unsatisfied';
      }
      if (retrievalOutcome.timeWindowRequired &&
          !retrievalOutcome.timeWindowKnown) {
        return 'historical_window_unknown';
      }
      if (retrievalOutcome.timeWindowRequired &&
          !retrievalOutcome.timeWindowSatisfied) {
        return 'historical_window_mismatch';
      }
      if (retrievalOutcome.freshnessRequired &&
          !retrievalOutcome.freshnessKnown) {
        return 'freshness_unknown';
      }
      if (retrievalOutcome.freshnessRequired &&
          !retrievalOutcome.freshnessSatisfied) {
        return 'freshness_unsatisfied';
      }
      if (retrievalOutcome.missingDimensions.isNotEmpty) {
        return 'missing_dimensions';
      }
      return 'missing_required_evidence';
    }
    if (nextAction != AssistantNextAction.answer.wireName) {
      return nextAction == AssistantNextAction.askUser.wireName
          ? 'ask_user'
          : 'blocked_by_state';
    }
    if (!renderableAnswer) return 'no_renderable_answer';
    return 'evidence_ready';
  }

  bool _hasRequiredEvidencePayload(RetrievalOutcome retrievalOutcome) {
    return retrievalOutcome.referenceCount > 0 ||
        retrievalOutcome.acceptedDocumentCount > 0;
  }

  AnswerGateDecision _reconcileParsedGate({
    required AnswerGateDecision parsed,
    required AnswerGateDecision derived,
  }) {
    final parsedWidensReadiness =
        (parsed.finalAnswerReady && !derived.finalAnswerReady) ||
        (parsed.eligible && !derived.eligible) ||
        (parsed.retrievalReady && !derived.retrievalReady) ||
        (parsed.terminalPayloadComplete && !derived.terminalPayloadComplete) ||
        (!parsed.degraded && derived.degraded) ||
        (parsed.nextAction == AssistantNextAction.answer.wireName &&
            derived.nextAction != AssistantNextAction.answer.wireName) ||
        (parsed.answerEligibility == AnswerEligibility.eligible.wireName &&
            derived.answerEligibility != AnswerEligibility.eligible.wireName);
    if (parsedWidensReadiness) {
      return derived;
    }
    return parsed;
  }

  String _reasonMessage({
    required String reasonCode,
    required RetrievalOutcome retrievalOutcome,
    required bool renderableAnswer,
    required String nextAction,
  }) {
    return retrievalOutcome.summary.trim();
  }

  AssistantTypedTurnDecision? _parseAssistantTypedTurnDecisionFromTypedState(
    Map<String, dynamic> structured,
  ) {
    final orchestratorRaw = structured[assistantOrchestratorStateField];
    final synthesisRaw = structured[assistantTurnSynthesisStateField];
    if (orchestratorRaw is! Map && synthesisRaw is! Map) {
      return null;
    }
    try {
      final orchestratorState = orchestratorRaw is Map
          ? ConversationOrchestratorState.fromJson(
              orchestratorRaw.cast<String, dynamic>(),
            )
          : const ConversationOrchestratorState();
      final synthesisState = synthesisRaw is Map
          ? TurnSynthesisState.fromJson(synthesisRaw.cast<String, dynamic>())
          : const TurnSynthesisState();
      return AssistantTypedTurnDecision.fromTypedState(
        orchestratorState: orchestratorState,
        turnSynthesisState: synthesisState,
      );
    } catch (_) {
      return null;
    }
  }

  bool _hasRenderableAnswer(
    Map<String, dynamic> structured,
    RunArtifacts? runArtifacts,
  ) {
    final markdown =
        runArtifacts?.displayMarkdown.trim() ??
        ((structured['userMarkdown'] as String?)?.trim() ?? '');
    if (markdown.isNotEmpty) return true;
    final plain =
        runArtifacts?.displayPlainText.trim() ??
        (((structured['result'] as Map?)?['text'] as String?)?.trim() ?? '');
    return plain.isNotEmpty;
  }
}
