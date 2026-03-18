import 'dart:convert';

import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/synthesis_readiness_result.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/infrastructure/llm/llm_response_parser.dart';

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
    if (normalizedTurn.nextActionType != AssistantNextAction.answer) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_answer',
      );
    }
    if (normalizedTurn.messageKindType == AssistantMessageKind.progress) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_is_progress_message',
      );
    }
    if (!projection.hasRenderableContent) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_renderable',
      );
    }
    return PhaseOneDirectAnswerDecision(
      shouldSkipSynthesis: true,
      reason: 'phase_one_direct_answer',
      normalizedEnvelopeText: jsonEncode(normalizedTurn.toEnvelopeMap()),
    );
  }
}
