import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

AssistantJourney resolveAssistantJourneyFromMessage(Map<String, dynamic> message) {
  return resolvePersistedAssistantTimeline(message);
}

AssistantJourney resolveAssistantJourneyFromResponse(
  AssistantRunResponse response,
) {
  return resolveAssistantJourneyFromRunResponse(response);
}

String resolveAssistantFollowupPrompt(Map<String, dynamic> message) {
  return resolveAssistantFollowupPromptFromMessage(message);
}

List<String> resolveAssistantActionHints(Map<String, dynamic> message) {
  return resolveAssistantActionHintsFromMessage(message);
}
