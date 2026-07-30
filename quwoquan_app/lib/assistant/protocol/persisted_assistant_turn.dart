// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 会话持久化消息 Map；子树用 codegen/Codec 收窄。

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/orchestrator_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/contracts/system_context_envelope.dart';
import 'package:quwoquan_app/assistant/contracts/task_graph_contract.dart';
import 'package:quwoquan_app/assistant/contracts/turn_synthesis_state_contract.dart';
import 'package:quwoquan_app/assistant/contracts/understanding_result_contract.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_process_timeline.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';

part 'persisted_assistant_turn_timeline_helpers.dart';

const String assistantJourneyField = 'journey';
const String assistantProcessTimelineField = 'processTimeline';
const String assistantDisplayMarkdownField = 'displayMarkdown';
const String assistantDisplayPlainTextField = 'displayPlainText';
const String assistantFollowupPromptField = 'followupPrompt';
const String assistantActionHintsField = 'actionHints';
const String assistantUnderstandingSnapshotField = 'understandingSnapshot';
const String assistantAnswerProcessingField = 'answerProcessing';
const String assistantHistoricalThinkingSnapshotField =
    'historicalThinkingSnapshot';
const String assistantRetrievalProcessingField = 'retrievalProcessing';
const String assistantProviderReasoningContinuationField =
    'providerReasoningContinuation';
const String assistantSystemContextEnvelopeField = 'systemContextEnvelope';
const String assistantUnderstandingResultField = 'understandingResult';
const String assistantTaskGraphField = 'taskGraph';
const String assistantOrchestratorStateField = 'orchestratorState';
const String assistantTurnSynthesisStateField = 'turnSynthesisState';
const String assistantBoundaryOutcomeField = 'assistantBoundaryOutcome';

AssistantJourney resolvePersistedAssistantJourney(
  Map<String, dynamic> message,
) {
  final raw = (message[assistantJourneyField] as Map?)?.cast<String, dynamic>();
  if (raw != null && raw.isNotEmpty) {
    final parsed = AssistantJourney.fromJson(raw);
    return parsed.isEmpty ? const AssistantJourney() : parsed;
  }
  return const AssistantJourney();
}

/// 只使用当前持久化 schema 产出的规范化 UI 时间轴。
AssistantJourney resolvePersistedAssistantJourneyForDisplay(
  Map<String, dynamic> message,
) {
  return resolvePersistedAssistantJourney(message);
}

List<ProcessTimelineFrame> resolvePersistedAssistantProcessTimeline(
  Map<String, dynamic> message,
) {
  final direct = _parseProcessTimelineList(
    message[assistantProcessTimelineField],
  );
  final supplemented = buildProcessTimelineFromSnapshots(
    processTimeline: hasStructuredProcessTimeline(direct)
        ? direct
        : const <ProcessTimelineFrame>[],
    understandingSnapshot: resolvePersistedAssistantUnderstandingSnapshot(
      message,
    ),
    retrievalProcessing: resolvePersistedAssistantRetrievalProcessing(message),
    answerProcessing: resolvePersistedAssistantAnswerProcessing(message),
  );
  if (hasStructuredProcessTimeline(supplemented)) {
    return supplemented;
  }
  return const <ProcessTimelineFrame>[];
}

List<ProcessTimelineFrame> resolvePersistedAssistantVisibleProcessTimeline(
  Map<String, dynamic> message,
) {
  return buildVisibleProcessTimeline(
    resolvePersistedAssistantProcessTimeline(message),
  );
}

AssistantDisplayState resolvePersistedAssistantDisplayState(
  Map<String, dynamic> message,
) {
  final direct = parseAssistantDisplayStateFromMap(
    (message[assistantDisplayStateField] as Map?)?.cast<String, dynamic>(),
  );
  if (hasAssistantDisplayState(direct)) {
    return direct;
  }
  return const AssistantDisplayState();
}

RunArtifactsUnderstandingSnapshot
resolvePersistedAssistantUnderstandingSnapshot(Map<String, dynamic> message) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantUnderstandingSnapshotField,
  );
  if (raw.isEmpty) {
    return const RunArtifactsUnderstandingSnapshot();
  }
  return parseRunArtifactsUnderstandingSnapshotFromMap(raw);
}

RunArtifactsAnswerProcessing resolvePersistedAssistantAnswerProcessing(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantAnswerProcessingField,
  );
  if (raw.isEmpty) {
    return const RunArtifactsAnswerProcessing();
  }
  return RunArtifactsAnswerProcessing.fromJson(raw);
}

RunArtifactsHistoricalThinkingSnapshot
resolvePersistedAssistantHistoricalThinkingSnapshot(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantHistoricalThinkingSnapshotField,
  );
  if (raw.isEmpty) {
    return const RunArtifactsHistoricalThinkingSnapshot();
  }
  return RunArtifactsHistoricalThinkingSnapshot.fromJson(raw);
}

RetrievalProcessingSnapshot resolvePersistedAssistantRetrievalProcessing(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantRetrievalProcessingField,
  );
  if (raw.isEmpty) {
    return const RetrievalProcessingSnapshot();
  }
  return RetrievalProcessingSnapshot.fromJson(raw);
}

SystemContextEnvelope resolvePersistedAssistantSystemContextEnvelope(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantSystemContextEnvelopeField,
  );
  if (raw.isEmpty) {
    return const SystemContextEnvelope();
  }
  return SystemContextEnvelope.fromJson(raw);
}

UnderstandingResult resolvePersistedAssistantUnderstandingResult(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantUnderstandingResultField,
  );
  if (raw.isEmpty) {
    return const UnderstandingResult();
  }
  return UnderstandingResult.fromJson(raw);
}

TaskGraph resolvePersistedAssistantTaskGraph(Map<String, dynamic> message) {
  final raw = _resolvePersistedStructuredMap(message, assistantTaskGraphField);
  if (raw.isEmpty) {
    return const TaskGraph();
  }
  return TaskGraph.fromJson(raw);
}

ConversationOrchestratorState resolvePersistedAssistantOrchestratorState(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantOrchestratorStateField,
  );
  if (raw.isEmpty) {
    return const ConversationOrchestratorState();
  }
  return ConversationOrchestratorState.fromJson(raw);
}

TurnSynthesisState resolvePersistedAssistantTurnSynthesisState(
  Map<String, dynamic> message,
) {
  final raw = _resolvePersistedStructuredMap(
    message,
    assistantTurnSynthesisStateField,
  );
  if (raw.isEmpty) {
    return const TurnSynthesisState();
  }
  return TurnSynthesisState.fromJson(raw);
}

String resolvePersistedAssistantDisplayMarkdown(Map<String, dynamic> message) {
  final displayState = resolvePersistedAssistantDisplayState(message);
  if (displayState.answer.blocks.isNotEmpty) {
    return renderAnswerBlocksToMarkdown(displayState.answer.blocks);
  }
  return AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
    (message[assistantDisplayMarkdownField] as String?) ?? '',
    allowJsonExtraction: false,
  );
}

String resolvePersistedAssistantDisplayPlainText(Map<String, dynamic> message) {
  final displayState = resolvePersistedAssistantDisplayState(message);
  if (displayState.answer.blocks.isNotEmpty) {
    return renderAnswerBlocksToPlainText(displayState.answer.blocks);
  }
  return AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
    (message[assistantDisplayPlainTextField] as String?) ?? '',
    allowJsonExtraction: false,
  );
}

String resolveAssistantFollowupPromptFromMessage(Map<String, dynamic> message) {
  return _sanitizeUserFacingTimelineText(
    (message[assistantFollowupPromptField] as String?) ?? '',
  );
}

List<String> resolveAssistantActionHintsFromMessage(
  Map<String, dynamic> message,
) {
  return ((message[assistantActionHintsField] as List?) ?? const <Object?>[])
      .whereType<String>()
      .map(_sanitizeUserFacingTimelineText)
      .where((item) => item.isNotEmpty)
      .toList(growable: false);
}

Map<String, dynamic> buildPersistedAssistantTurnFields({
  required AssistantJourney journey,
  required String displayMarkdown,
  required String displayPlainText,
  required String followupPrompt,
  required List<String> actionHints,
  required int elapsedMs,
  Map<String, dynamic> displayState = const <String, dynamic>{},
  List<ProcessTimelineFrame> processTimeline = const <ProcessTimelineFrame>[],
  Map<String, dynamic> understandingSnapshot = const <String, dynamic>{},
  Map<String, dynamic> answerProcessing = const <String, dynamic>{},
  Map<String, dynamic> historicalThinkingSnapshot = const <String, dynamic>{},
  Map<String, dynamic> retrievalProcessing = const <String, dynamic>{},
  Map<String, dynamic> systemContextEnvelope = const <String, dynamic>{},
  Map<String, dynamic> understandingResult = const <String, dynamic>{},
  Map<String, dynamic> taskGraph = const <String, dynamic>{},
  Map<String, dynamic> orchestratorState = const <String, dynamic>{},
  Map<String, dynamic> turnSynthesisState = const <String, dynamic>{},
  Map<String, dynamic> assistantBoundaryOutcome = const <String, dynamic>{},
  String providerReasoningContinuation = '',
}) {
  final persistedProcessTimeline = hasStructuredProcessTimeline(processTimeline)
      ? normalizeProcessTimeline(processTimeline)
      : buildProcessTimelineFromSnapshots(
          understandingSnapshot: parseRunArtifactsUnderstandingSnapshotFromMap(
            understandingSnapshot,
          ),
          retrievalProcessing: RetrievalProcessingSnapshot.fromJson(
            retrievalProcessing,
          ),
          answerProcessing: RunArtifactsAnswerProcessing.fromJson(
            answerProcessing,
          ),
        );
  final normalizedDisplayMarkdown =
      AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(
        displayMarkdown,
        allowJsonExtraction: false,
      );
  final normalizedDisplayPlainText =
      AssistantDisplayTextResolver.normalizeCompletedPlainTextCandidate(
        displayPlainText,
        allowJsonExtraction: false,
      );
  return <String, dynamic>{
    assistantJourneyField: journey.toJson(),
    if (persistedProcessTimeline.isNotEmpty)
      assistantProcessTimelineField: persistedProcessTimeline
          .map((item) => item.toJson())
          .toList(growable: false),
    if (_hasStructuredContent(understandingSnapshot))
      assistantUnderstandingSnapshotField: _copyStructuredMap(
        understandingSnapshot,
      ),
    if (_hasStructuredContent(answerProcessing))
      assistantAnswerProcessingField: _copyStructuredMap(answerProcessing),
    if (_hasStructuredContent(historicalThinkingSnapshot))
      assistantHistoricalThinkingSnapshotField: _copyStructuredMap(
        historicalThinkingSnapshot,
      ),
    if (_hasStructuredContent(retrievalProcessing))
      assistantRetrievalProcessingField: _copyStructuredMap(
        retrievalProcessing,
      ),
    if (_hasStructuredContent(systemContextEnvelope))
      assistantSystemContextEnvelopeField: _copyStructuredMap(
        systemContextEnvelope,
      ),
    if (_hasStructuredContent(understandingResult))
      assistantUnderstandingResultField: _copyStructuredMap(
        understandingResult,
      ),
    if (_hasStructuredContent(taskGraph))
      assistantTaskGraphField: _copyStructuredMap(taskGraph),
    if (_hasStructuredContent(orchestratorState))
      assistantOrchestratorStateField: _copyStructuredMap(orchestratorState),
    if (_hasStructuredContent(turnSynthesisState))
      assistantTurnSynthesisStateField: _copyStructuredMap(turnSynthesisState),
    if (_hasStructuredContent(assistantBoundaryOutcome))
      assistantBoundaryOutcomeField: _copyStructuredMap(
        assistantBoundaryOutcome,
      ),
    if (providerReasoningContinuation.trim().isNotEmpty)
      assistantProviderReasoningContinuationField: providerReasoningContinuation
          .trim(),
    if (_hasStructuredContent(displayState))
      assistantDisplayStateField: _copyStructuredMap(displayState),
    assistantDisplayMarkdownField: normalizedDisplayMarkdown,
    assistantDisplayPlainTextField: normalizedDisplayPlainText,
    assistantFollowupPromptField: _sanitizeUserFacingTimelineText(
      followupPrompt,
    ),
    assistantActionHintsField: actionHints
        .map(_sanitizeUserFacingTimelineText)
        .where((item) => item.isNotEmpty)
        .toList(growable: false),
    'assistantElapsedMs': elapsedMs,
  };
}
