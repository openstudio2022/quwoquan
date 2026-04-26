import 'package:quwoquan_app/assistant/infrastructure/streaming/assistant_stream_chunk_visibility.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_text_resolver.dart';
import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';

/// 从 persisted / Map 形态的多候选字段中，取出首段可送入多轮拼历史的助手正文（与流式/协议过滤一致）。
String firstSanitizedAssistantHistoryTextForModel(
  Iterable<String> rawCandidates,
) {
  for (final raw in rawCandidates) {
    final sanitized =
        AssistantDisplayTextResolver.normalizeCompletedDisplayCandidate(raw);
    if (sanitized.isEmpty) continue;
    if (isAssistantStreamInternalChunk(sanitized)) continue;
    if (AssistantContentFilters.isProgressPlaceholder(sanitized)) continue;
    if (AssistantDisplayTextResolver.containsUnsafeDisplayProtocolLeak(
      sanitized,
    )) {
      continue;
    }
    return sanitized;
  }
  return '';
}

String assistantHistoryTextForModelFromMessageMap(
  Map<String, dynamic> message,
) {
  return firstSanitizedAssistantHistoryTextForModel(<String>[
    (message['displayPlainText'] ?? '').toString(),
    (message['displayMarkdown'] ?? '').toString(),
    (message['content'] ?? '').toString(),
  ]);
}

String assistantHistoryTextForModelFromAnswerRow(
  AssistantAnswerTranscriptRow row,
) {
  return firstSanitizedAssistantHistoryTextForModel(<String>[
    row.persisted.displayPlainText,
    row.persisted.displayMarkdown,
    row.content,
  ]);
}
