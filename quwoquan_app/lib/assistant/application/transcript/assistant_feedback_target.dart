import 'package:quwoquan_app/assistant/transcript/row/assistant_transcript_timeline_row.dart';

/// 显式/隐式反馈锚点（application）；禁止再传整行 [Map]。
class AssistantFeedbackTarget {
  const AssistantFeedbackTarget({
    required this.messageId,
    this.runId = '',
    this.traceId = '',
    this.sourceQuery = '',
    this.answerText = '',
    this.displayPlainText = '',
  });

  final String messageId;
  final String runId;
  final String traceId;
  final String sourceQuery;
  final String answerText;
  final String displayPlainText;

  factory AssistantFeedbackTarget.fromAssistantRow(
    AssistantAnswerTranscriptRow row, {
    String? replayQuery,
    String? replayRunId,
    String? replayTraceId,
  }) {
    final plain = row.persisted.displayPlainText.trim().isNotEmpty
        ? row.persisted.displayPlainText
        : row.content;
    return AssistantFeedbackTarget(
      messageId: row.id,
      runId: row.anchor.runId.isNotEmpty ? row.anchor.runId : (replayRunId ?? ''),
      traceId:
          row.anchor.traceId.isNotEmpty ? row.anchor.traceId : (replayTraceId ?? ''),
      sourceQuery: row.anchor.sourceQuery.isNotEmpty
          ? row.anchor.sourceQuery
          : (replayQuery ?? ''),
      answerText: row.content,
      displayPlainText: plain,
    );
  }
}
