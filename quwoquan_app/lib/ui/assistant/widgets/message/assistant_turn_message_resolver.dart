import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
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

RetrievalProcessingSnapshot resolveAssistantRetrievalProcessingFromMessage(
  Map<String, dynamic> message,
) {
  final direct = (message[assistantRetrievalProcessingField] as Map?)
      ?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    return RetrievalProcessingSnapshot.fromJson(direct);
  }
  final runArtifacts = (message['runArtifacts'] as Map?)?.cast<String, dynamic>();
  final nested = (runArtifacts?[assistantRetrievalProcessingField] as Map?)
      ?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    return RetrievalProcessingSnapshot.fromJson(nested);
  }
  return const RetrievalProcessingSnapshot();
}

RetrievalProcessingSnapshot resolveAssistantRetrievalProcessingFromResponse(
  AssistantRunResponse response,
) {
  final direct =
      (response.structuredResponse[assistantRetrievalProcessingField] as Map?)
          ?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    return RetrievalProcessingSnapshot.fromJson(direct);
  }
  return response.runArtifacts?.retrievalProcessing ??
      const RetrievalProcessingSnapshot();
}

String resolveAssistantFollowupPrompt(Map<String, dynamic> message) {
  return resolveAssistantFollowupPromptFromMessage(message);
}

List<String> resolveAssistantActionHints(Map<String, dynamic> message) {
  return resolveAssistantActionHintsFromMessage(message);
}
