import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';

class AssistantPipelineRecoveredStagePayload {
  const AssistantPipelineRecoveredStagePayload({
    required this.reasonShort,
    required this.resultSummary,
    required this.resultInterpretation,
    required this.understandingSnapshot,
    required this.retrievalProcessing,
    required this.answerProcessing,
    required this.historicalThinkingSnapshot,
    required this.slotState,
  });

  factory AssistantPipelineRecoveredStagePayload.fromWireMap(
    Map<String, dynamic> payload,
  ) {
    final resultMap =
        (payload['result'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final understandingSnapshot =
        (payload['understandingSnapshot'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final retrievalProcessing =
        (payload['retrievalProcessing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final answerProcessing =
        (payload['answerProcessing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final historicalThinkingSnapshot =
        (payload['historicalThinkingSnapshot'] as Map?)
                ?.cast<String, dynamic>() ??
            const <String, dynamic>{};
    final slotState =
        (payload['slotState'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return AssistantPipelineRecoveredStagePayload(
      reasonShort: (payload['reasonShort'] as String?)?.trim() ?? '',
      resultSummary: (resultMap['summary'] as String?)?.trim() ?? '',
      resultInterpretation:
          (resultMap['interpretation'] as String?)?.trim() ?? '',
      understandingSnapshot: hasStructuredContent(understandingSnapshot)
          ? AssistantTurnUnderstandingSnapshot.fromJson(understandingSnapshot)
          : const AssistantTurnUnderstandingSnapshot(),
      retrievalProcessing: hasStructuredContent(retrievalProcessing)
          ? RetrievalProcessingSnapshot.fromJson(retrievalProcessing)
          : const RetrievalProcessingSnapshot(),
      answerProcessing: hasStructuredContent(answerProcessing)
          ? AssistantTurnAnswerProcessing.fromJson(answerProcessing)
          : const AssistantTurnAnswerProcessing(),
      historicalThinkingSnapshot:
          hasStructuredContent(historicalThinkingSnapshot)
              ? AssistantTurnHistoricalThinkingSnapshot.fromJson(
                  historicalThinkingSnapshot,
                )
              : const AssistantTurnHistoricalThinkingSnapshot(),
      slotState: hasStructuredContent(slotState)
          ? SlotStateSnapshot.fromJson(slotState)
          : const SlotStateSnapshot(),
    );
  }

  final String reasonShort;
  final String resultSummary;
  final String resultInterpretation;
  final AssistantTurnUnderstandingSnapshot understandingSnapshot;
  final RetrievalProcessingSnapshot retrievalProcessing;
  final AssistantTurnAnswerProcessing answerProcessing;
  final AssistantTurnHistoricalThinkingSnapshot historicalThinkingSnapshot;
  final SlotStateSnapshot slotState;
}

class AssistantPipelineRecoveryPayloadBundle {
  const AssistantPipelineRecoveryPayloadBundle({
    required this.recovery,
    required this.fallback,
  });

  factory AssistantPipelineRecoveryPayloadBundle.fromWireMaps({
    required Map<String, dynamic> recoveryPayload,
    required Map<String, dynamic> fallbackPayload,
  }) {
    return AssistantPipelineRecoveryPayloadBundle(
      recovery: AssistantPipelineRecoveredStagePayload.fromWireMap(
        recoveryPayload,
      ),
      fallback: AssistantPipelineRecoveredStagePayload.fromWireMap(
        fallbackPayload,
      ),
    );
  }

  final AssistantPipelineRecoveredStagePayload recovery;
  final AssistantPipelineRecoveredStagePayload fallback;
}

bool hasStructuredContent(Map<String, dynamic> value) {
  for (final entry in value.entries) {
    final v = entry.value;
    if (v == null) continue;
    if (v is String && v.trim().isEmpty) continue;
    if (v is List && v.isEmpty) continue;
    if (v is Map && v.isEmpty) continue;
    return true;
  }
  return false;
}

