import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_persisted_value_types.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/domain/persisted_assistant_turn.dart'
    as internal;

const String assistantJourneyField = internal.assistantJourneyField;
const String assistantProcessTimelineField =
    internal.assistantProcessTimelineField;
const String assistantDisplayMarkdownField =
    internal.assistantDisplayMarkdownField;
const String assistantDisplayPlainTextField =
    internal.assistantDisplayPlainTextField;
const String assistantUnderstandingSnapshotField =
    internal.assistantUnderstandingSnapshotField;
const String assistantAnswerProcessingField =
    internal.assistantAnswerProcessingField;
const String assistantRetrievalProcessingField =
    internal.assistantRetrievalProcessingField;
const String assistantHistoricalThinkingSnapshotField =
    internal.assistantHistoricalThinkingSnapshotField;
const String assistantProviderReasoningContinuationField =
    internal.assistantProviderReasoningContinuationField;
const String assistantSystemContextEnvelopeField =
    internal.assistantSystemContextEnvelopeField;
const String assistantUnderstandingResultField =
    internal.assistantUnderstandingResultField;
const String assistantTaskGraphField = internal.assistantTaskGraphField;
const String assistantOrchestratorStateField =
    internal.assistantOrchestratorStateField;
const String assistantTurnSynthesisStateField =
    internal.assistantTurnSynthesisStateField;
const String assistantFollowupPromptField =
    internal.assistantFollowupPromptField;
const String assistantActionHintsField = internal.assistantActionHintsField;
const String assistantBoundaryOutcomeField =
    internal.assistantBoundaryOutcomeField;

AssistantJourney resolvePersistedAssistantJourneyForDisplay(
  Map<String, dynamic> message,
) {
  return internal.resolvePersistedAssistantJourneyForDisplay(message);
}

List<ProcessTimelineFrame> resolvePersistedAssistantVisibleProcessTimeline(
  Map<String, dynamic> message,
) {
  return internal.resolvePersistedAssistantVisibleProcessTimeline(message);
}

AssistantDisplayState resolvePersistedAssistantDisplayState(
  Map<String, dynamic> message,
) {
  return internal.resolvePersistedAssistantDisplayState(message);
}

String resolvePersistedAssistantDisplayMarkdown(Map<String, dynamic> message) {
  return internal.resolvePersistedAssistantDisplayMarkdown(message);
}

String resolvePersistedAssistantDisplayPlainText(
  Map<String, dynamic> message,
) {
  return internal.resolvePersistedAssistantDisplayPlainText(message);
}

String resolveAssistantFollowupPromptFromMessage(Map<String, dynamic> message) {
  return internal.resolveAssistantFollowupPromptFromMessage(message);
}

List<String> resolveAssistantActionHintsFromMessage(
  Map<String, dynamic> message,
) {
  return internal.resolveAssistantActionHintsFromMessage(message);
}
