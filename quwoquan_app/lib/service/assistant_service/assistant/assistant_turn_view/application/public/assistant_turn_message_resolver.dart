// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 时间轴协议 Map 与 persisted turn 键空间（与 Codec 对齐）。

import 'package:quwoquan_app/service/assistant_service/assistant/assistant_run/application/public/assistant_run_persisted_value_types.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_assistant_turn_contract.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/persisted_timeline_turn_codec.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/assistant_turn_view/application/public/assistant_transcript_timeline_row.dart';

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

List<ProcessTimelineFrame> resolveAssistantProcessTimelineFromMessage(
  Map<String, dynamic> message,
) {
  return resolvePersistedAssistantVisibleProcessTimeline(message);
}

RetrievalProcessingSnapshot resolveAssistantRetrievalProcessingFromMessage(
  Map<String, dynamic> message,
) {
  final direct = (message[assistantRetrievalProcessingField] as Map?)
      ?.cast<String, dynamic>();
  if (direct != null && direct.isNotEmpty) {
    return RetrievalProcessingSnapshot.fromJson(direct);
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
  return const RunArtifactsAnswerProcessing();
}
