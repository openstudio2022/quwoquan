import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/subagent_plan.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/conversation/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/conversation/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';
import 'package:quwoquan_app/assistant/reasoning/contracts/planner_contracts.dart';

class PhaseOneDirectAnswerDecision {
  const PhaseOneDirectAnswerDecision({
    required this.shouldSkipSynthesis,
    required this.reason,
    this.normalizedEnvelopeText = '',
  });

  final bool shouldSkipSynthesis;
  final String reason;
  final String normalizedEnvelopeText;
}

class PhaseOneDirectAnswerGate {
  const PhaseOneDirectAnswerGate();

  static const String directTemplateVersion = 'phase_one_direct_answer';

  PhaseOneDirectAnswerDecision evaluate({
    required String rawFinalText,
    required SynthesisReadinessResult synthesisReadiness,
  }) {
    if (!synthesisReadiness.ready) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'synthesis_not_ready',
      );
    }
    final parsed = LlmResponseParser.parse(rawFinalText).json;
    if (parsed == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_structured',
      );
    }
    final turn = tryParseAssistantTurnOutput(parsed);
    if (turn == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_contract_turn',
      );
    }
    final normalizedTurn = AssistantDisplayTextResolver.normalizeTurn(turn);
    final projection = AssistantDisplayTextResolver.projectTurn(normalizedTurn);
    final compatDirectAnswerTurn = _coerceCompatDirectAnswerTurn(
      normalizedTurn,
      projection,
    );
    if (normalizedTurn.nextActionType != AssistantNextAction.answer &&
        compatDirectAnswerTurn == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_answer',
      );
    }
    if (normalizedTurn.messageKindType == AssistantMessageKind.progress &&
        compatDirectAnswerTurn == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_is_progress_message',
      );
    }
    final effectiveTurn = compatDirectAnswerTurn ?? normalizedTurn;
    final effectiveProjection = compatDirectAnswerTurn != null
        ? AssistantDisplayTextResolver.projectTurn(compatDirectAnswerTurn)
        : projection;
    if (!effectiveProjection.hasRenderableContent) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_renderable',
      );
    }
    return PhaseOneDirectAnswerDecision(
      shouldSkipSynthesis: true,
      reason: compatDirectAnswerTurn != null
          ? 'phase_one_compat_direct_answer'
          : 'phase_one_direct_answer',
      normalizedEnvelopeText: jsonEncode(effectiveTurn.toEnvelopeMap()),
    );
  }

  AssistantTurnOutput? _coerceCompatDirectAnswerTurn(
    AssistantTurnOutput turn,
    AssistantDisplayProjection projection,
  ) {
    if (!projection.hasRenderableContent) return null;
    if (turn.phaseIdType != PlannerPhaseId.unknown ||
        turn.actionCodeType != PlannerActionCode.unknown ||
        turn.reasonCodeType != PlannerReasonCode.unknownReason) {
      return null;
    }
    if (AssistantContentFilters.isProgressPlaceholder(projection.markdown)) {
      return null;
    }
    if (turn.toolCalls.isNotEmpty || turn.toolPlan.isNotEmpty) return null;
    if (turn.subagentPlan.isNotEmpty ||
        turn.hasAskUser ||
        turn.missingContextSlots.isNotEmpty) {
      return null;
    }
    if (turn.nextActionType == AssistantNextAction.answer &&
        turn.messageKindType != AssistantMessageKind.progress) {
      return null;
    }
    return AssistantTurnOutput(
      contractVersion: turn.contractVersion,
      decision: const AssistantTurnDecisionPayload(
        nextAction: AssistantNextAction.answer,
      ),
      messageKind: AssistantMessageKind.answer,
      userMarkdown: projection.markdown,
      result: AssistantTurnResult(
        text: projection.plainText,
        summary: projection.summary,
        interpretation: turn.result.interpretation,
        actionHints: turn.result.actionHints,
      ),
      evidence: turn.evidence,
      reasoningBasis: turn.reasoningBasis,
      selfCheck: turn.selfCheck,
      diagnostics: turn.diagnostics,
      modelSelfScore: turn.modelSelfScore,
      askUser: const AssistantTurnAskUser(),
      toolCalls: const <AssistantTurnToolCall>[],
      slotState: turn.slotState,
      subagentPlan: const <SubagentPlan>[],
      intentGraph: turn.intentGraph,
      skillRuns: turn.skillRuns,
      aggregationState: turn.aggregationState,
      userEvents: turn.userEvents,
      uiProcessTimeline: turn.uiProcessTimeline,
      toolPlan: const <AssistantTurnToolCall>[],
      missingContextSlots: const <String>[],
      fillGuidance: const <AssistantTurnFillGuidanceItem>[],
      followupPrompt: turn.followupPrompt,
      processSummary: turn.processSummary,
      processReferenceCount: turn.processReferenceCount,
      phaseId: PlannerPhaseId.answering,
      actionCode: PlannerActionCode.composeAnswer,
      reasonCode: PlannerReasonCode.evidenceReady,
      reasonShort: turn.reasonShort,
      narrativeSource: turn.narrativeSource,
      narrativeReferences: turn.narrativeReferences,
      sessionPreferenceFacts: turn.sessionPreferenceFacts,
      longTermPreferenceFacts: turn.longTermPreferenceFacts,
    );
  }
}
