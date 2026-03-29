import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';

AssistantJourney resolveAssistantJourneyFromMessage(Map<String, dynamic> message) {
  return resolvePersistedAssistantJourneyForDisplay(message);
}

AssistantJourney resolveAssistantJourneyFromResponse(
  AssistantRunResponse response,
) {
  return resolveAssistantJourneyFromRunResponse(response);
}

List<ProcessTimelineFrame> resolveAssistantProcessTimelineFromMessage(
  Map<String, dynamic> message,
) {
  return resolvePersistedAssistantVisibleProcessTimeline(message);
}

List<ProcessTimelineFrame> resolveAssistantProcessTimelineFromResponse(
  AssistantRunResponse response,
) {
  return resolveAssistantVisibleProcessTimelineFromRunResponse(response);
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

RunArtifactsUnderstandingSnapshot resolveAssistantUnderstandingSnapshotFromMessage(
  Map<String, dynamic> message,
) {
  final direct = (message[assistantUnderstandingSnapshotField] as Map?)
      ?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    return RunArtifactsUnderstandingSnapshot.fromJson(direct);
  }
  final runArtifacts = (message['runArtifacts'] as Map?)?.cast<String, dynamic>();
  final nested = (runArtifacts?[assistantUnderstandingSnapshotField] as Map?)
      ?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    return RunArtifactsUnderstandingSnapshot.fromJson(nested);
  }
  return const RunArtifactsUnderstandingSnapshot();
}

RunArtifactsAnswerProcessing resolveAssistantAnswerProcessingFromMessage(
  Map<String, dynamic> message,
) {
  final direct = (message[assistantAnswerProcessingField] as Map?)
      ?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    return RunArtifactsAnswerProcessing.fromJson(direct);
  }
  final runArtifacts = (message['runArtifacts'] as Map?)?.cast<String, dynamic>();
  final nested = (runArtifacts?[assistantAnswerProcessingField] as Map?)
      ?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    return RunArtifactsAnswerProcessing.fromJson(nested);
  }
  return const RunArtifactsAnswerProcessing();
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
