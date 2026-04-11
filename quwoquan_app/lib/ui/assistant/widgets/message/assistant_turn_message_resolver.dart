// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 时间轴协议 Map 与 persisted turn 键空间（与 Codec 对齐）。

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/run_artifacts.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/run_response.dart';
import 'package:quwoquan_app/assistant/protocol/understanding_snapshot_codec.dart';
import 'package:quwoquan_app/assistant/transcript/persisted_timeline/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';

/// 将时间轴行编码为与 [resolvePersistedAssistantDisplayState] 等协议解析器兼容的扁平 Map。
///
/// UI 层应优先调用本文件中带 `FromTranscriptRow` 后缀的解析函数，避免在 Widget 中持有 Map。
Map<String, dynamic> assistantTranscriptRowToProtocolMap(
  AssistantTranscriptTimelineRow row,
) {
  return PersistedTimelineTurnCodec.encode(row);
}

AssistantJourney resolveAssistantJourneyFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolvePersistedAssistantJourneyForDisplay(
    assistantTranscriptRowToProtocolMap(row),
  );
}

List<ProcessTimelineFrame> resolveAssistantProcessTimelineFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolvePersistedAssistantVisibleProcessTimeline(
    assistantTranscriptRowToProtocolMap(row),
  );
}

RetrievalProcessingSnapshot
resolveAssistantRetrievalProcessingFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolveAssistantRetrievalProcessingFromMessage(
    assistantTranscriptRowToProtocolMap(row),
  );
}

RunArtifactsUnderstandingSnapshot
resolveAssistantUnderstandingSnapshotFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolveAssistantUnderstandingSnapshotFromMessage(
    assistantTranscriptRowToProtocolMap(row),
  );
}

RunArtifactsAnswerProcessing resolveAssistantAnswerProcessingFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolveAssistantAnswerProcessingFromMessage(
    assistantTranscriptRowToProtocolMap(row),
  );
}

AssistantDisplayState resolvePersistedAssistantDisplayStateFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolvePersistedAssistantDisplayState(
    assistantTranscriptRowToProtocolMap(row),
  );
}

String resolvePersistedAssistantDisplayMarkdownFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolvePersistedAssistantDisplayMarkdown(
    assistantTranscriptRowToProtocolMap(row),
  );
}

String resolvePersistedAssistantDisplayPlainTextFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolvePersistedAssistantDisplayPlainText(
    assistantTranscriptRowToProtocolMap(row),
  );
}

String resolveAssistantFollowupPromptFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolveAssistantFollowupPromptFromMessage(
    assistantTranscriptRowToProtocolMap(row),
  );
}

List<String> resolveAssistantActionHintsFromTranscriptRow(
  AssistantTranscriptTimelineRow row,
) {
  return resolveAssistantActionHintsFromMessage(
    assistantTranscriptRowToProtocolMap(row),
  );
}

AssistantJourney resolveAssistantJourneyFromMessage(
  Map<String, dynamic> message,
) {
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
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  final nested = (runArtifacts?[assistantRetrievalProcessingField] as Map?)
      ?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    return RetrievalProcessingSnapshot.fromJson(nested);
  }
  return const RetrievalProcessingSnapshot();
}

RunArtifactsUnderstandingSnapshot
resolveAssistantUnderstandingSnapshotFromMessage(Map<String, dynamic> message) {
  final direct = (message[assistantUnderstandingSnapshotField] as Map?)
      ?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    return parseRunArtifactsUnderstandingSnapshotFromMap(direct);
  }
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
  final nested = (runArtifacts?[assistantUnderstandingSnapshotField] as Map?)
      ?.cast<String, dynamic>();
  if (nested != null && nested.isNotEmpty) {
    return parseRunArtifactsUnderstandingSnapshotFromMap(nested);
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
  final runArtifacts = (message['runArtifacts'] as Map?)
      ?.cast<String, dynamic>();
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
