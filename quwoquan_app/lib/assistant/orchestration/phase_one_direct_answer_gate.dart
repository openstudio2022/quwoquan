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
    bool executionSignalsPresent = false,
  }) {
    final parseResult = LlmResponseParser.parse(rawFinalText);
    if (!parseResult.ok || parseResult.json == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_structured',
      );
    }
    final parsed = parseResult.json!;
    final turn = tryParseAssistantTurnOutput(parsed);
    if (turn == null) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_not_contract_turn',
      );
    }
    final normalizedTurn = AssistantDisplayTextResolver.normalizeTurn(turn);
    final projection = AssistantDisplayTextResolver.projectTurn(normalizedTurn);
    final rawToolCalls =
        (parsed['toolCalls'] as List?)?.whereType<Object>().toList() ??
        const <Object>[];
    final phaseId = (parsed['phaseId'] as String?)?.trim() ?? '';
    final actionCode = (parsed['actionCode'] as String?)?.trim() ?? '';
    final reasonCode = (parsed['reasonCode'] as String?)?.trim() ?? '';
    final rawResult =
        (parsed['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final rawResultText = (rawResult['text'] as String?)?.trim() ?? '';
    final staleProgressCompat =
        rawToolCalls.isEmpty &&
        projection.hasRenderableContent &&
        normalizedTurn.messageKindType == AssistantMessageKind.progress &&
        (phaseId == 'answering' || rawResultText.isNotEmpty);
    if (staleProgressCompat && !executionSignalsPresent) {
      final recoveredTurn = AssistantTurnOutput(
        contractId: kAssistantTurnCurrentContractId,
        decision: const AssistantTurnDecisionPayload(
          nextAction: AssistantNextAction.answer,
        ),
        messageKind: AssistantMessageKind.answer,
        userMarkdown: projection.markdown,
        result: AssistantTurnResult(
          text: projection.plainText,
          summary: projection.summary,
          interpretation: 'recovered_from_progress_compat',
        ),
        selfCheck: const AssistantTurnSelfCheck(
          goalSatisfied: true,
          constraintSatisfied: true,
          safetyBoundarySatisfied: true,
        ),
        diagnostics: const AssistantTurnDiagnostics(
          notes: <String>['phase_one_progress_answer_compat'],
        ),
        modelSelfScore: const AssistantTurnModelSelfScore(
          score: 78,
          reason: 'phase_one_progress_answer_compat',
        ),
      );
      return PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: true,
        reason: 'phase_one_compat_direct_answer',
        normalizedEnvelopeText: jsonEncode(recoveredTurn.toEnvelopeMap()),
      );
    }
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
    final hasDirectAnswerContract =
        phaseId == 'answering' &&
        actionCode == 'compose_answer' &&
        reasonCode == 'evidence_ready';
    if (!hasDirectAnswerContract) {
      if (!synthesisReadiness.ready) {
        return const PhaseOneDirectAnswerDecision(
          shouldSkipSynthesis: false,
          reason: 'synthesis_not_ready',
        );
      }
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'phase_one_contract_incomplete',
      );
    }
    if (executionSignalsPresent) {
      return const PhaseOneDirectAnswerDecision(
        shouldSkipSynthesis: false,
        reason: 'execution_signals_require_synthesis',
      );
    }
    return PhaseOneDirectAnswerDecision(
      shouldSkipSynthesis: true,
      reason: 'phase_one_direct_answer',
      normalizedEnvelopeText: jsonEncode(normalizedTurn.toEnvelopeMap()),
    );
  }
}
