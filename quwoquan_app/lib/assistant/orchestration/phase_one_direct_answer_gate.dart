import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';

enum PhaseOneDirectAnswerReason {
  notStructured,
  notContractTurn,
  compatDirectAnswer,
  notAnswer,
  progressMessage,
  notRenderable,
  synthesisNotReady,
  contractIncomplete,
  executionSignalsRequireSynthesis,
  directAnswer,
  artifactIgnored,
}

extension PhaseOneDirectAnswerReasonX on PhaseOneDirectAnswerReason {
  String get wireName {
    switch (this) {
      case PhaseOneDirectAnswerReason.notStructured:
        return 'phase_one_not_structured';
      case PhaseOneDirectAnswerReason.notContractTurn:
        return 'phase_one_not_contract_turn';
      case PhaseOneDirectAnswerReason.compatDirectAnswer:
        return 'phase_one_compat_direct_answer';
      case PhaseOneDirectAnswerReason.notAnswer:
        return 'phase_one_not_answer';
      case PhaseOneDirectAnswerReason.progressMessage:
        return 'phase_one_is_progress_message';
      case PhaseOneDirectAnswerReason.notRenderable:
        return 'phase_one_not_renderable';
      case PhaseOneDirectAnswerReason.synthesisNotReady:
        return 'synthesis_not_ready';
      case PhaseOneDirectAnswerReason.contractIncomplete:
        return 'phase_one_contract_incomplete';
      case PhaseOneDirectAnswerReason.executionSignalsRequireSynthesis:
        return 'execution_signals_require_synthesis';
      case PhaseOneDirectAnswerReason.directAnswer:
        return 'phase_one_direct_answer';
      case PhaseOneDirectAnswerReason.artifactIgnored:
        return 'phase_one_artifact_ignored';
    }
  }

  bool get repairable =>
      this == PhaseOneDirectAnswerReason.notStructured ||
      this == PhaseOneDirectAnswerReason.notContractTurn ||
      this == PhaseOneDirectAnswerReason.contractIncomplete;
}

class PhaseOneDirectAnswerDecision {
  const PhaseOneDirectAnswerDecision({
    required this.shouldSkipSynthesis,
    required this.reason,
    this.normalizedEnvelopeText = '',
  });

  final bool shouldSkipSynthesis;
  final PhaseOneDirectAnswerReason reason;
  final String normalizedEnvelopeText;

  String get reasonWireName => reason.wireName;
}

class PhaseOneDirectAnswerGate {
  const PhaseOneDirectAnswerGate();

  static const String directTemplateVersion = 'phase_one_direct_answer';

  PhaseOneDirectAnswerDecision evaluate({
    required String rawFinalText,
    required SynthesisReadinessResult synthesisReadiness,
    bool executionSignalsPresent = false,
  }) {
    final parseResult = LlmResponseParser.parse(rawFinalText);
    if (!parseResult.ok || parseResult.json == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.notStructured,
      );
    }
    final parsed = parseResult.json!;
    final turn = tryParseAssistantTurnOutput(parsed);
    if (turn == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.notContractTurn,
      );
    }
    final normalizedTurn = AssistantDisplayTextResolver.normalizeTurn(turn);
    final projection = AssistantDisplayTextResolver.projectTurn(normalizedTurn);
    final rawToolCalls = normalizedTurn.toolCalls;
    final phaseId = normalizedTurn.phaseIdType;
    final actionCode = normalizedTurn.actionCodeType;
    final reasonCode = normalizedTurn.reasonCodeType;
    final rawResultText = normalizedTurn.result.text.trim();
    final staleProgressCompat =
        rawToolCalls.isEmpty &&
        projection.hasRenderableContent &&
        normalizedTurn.messageKindType == AssistantMessageKind.progress &&
        (phaseId == PlannerPhaseId.answering || rawResultText.isNotEmpty);
    if (staleProgressCompat && !executionSignalsPresent) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.compatDirectAnswer,
      );
    }
    if (normalizedTurn.nextActionType != AssistantNextAction.answer) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.notAnswer,
      );
    }
    if (normalizedTurn.messageKindType == AssistantMessageKind.progress) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.progressMessage,
      );
    }
    if (!projection.hasRenderableContent) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.notRenderable,
      );
    }
    final hasDirectAnswerContract =
        phaseId == PlannerPhaseId.answering &&
        actionCode == PlannerActionCode.composeAnswer &&
        reasonCode == PlannerReasonCode.evidenceReady;
    if (!hasDirectAnswerContract) {
      if (!synthesisReadiness.ready) {
        return const PhaseOneDirectAnswerDecision(
          shouldSkipSynthesis: false,
          reason: PhaseOneDirectAnswerReason.synthesisNotReady,
        );
      }
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.contractIncomplete,
      );
    }
    if (executionSignalsPresent) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: PhaseOneDirectAnswerReason.executionSignalsRequireSynthesis,
      );
    }
    return PhaseOneDirectAnswerDecision(
      shouldSkipSynthesis: true,
      reason: PhaseOneDirectAnswerReason.directAnswer,
      normalizedEnvelopeText: jsonEncode(normalizedTurn.toEnvelopeMap()),
    );
  }
}
