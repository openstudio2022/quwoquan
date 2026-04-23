import 'dart:convert';
import 'dart:math' as math;

import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';

class AssistantSessionSummaryBuilder {
  const AssistantSessionSummaryBuilder();

  String summarizeRecentMessages(
    List<Map<String, dynamic>> history, {
    int limit = defaultRecentDialogueRoundsLimit,
    int? roundsLimit,
    int roundsOlderLimit = defaultOlderRecentDialogueRoundsLimit,
  }) {
    return _summarizeRecentMessages(
      history,
      limit: limit,
      roundsLimit: roundsLimit,
      roundsOlderLimit: roundsOlderLimit,
    );
  }

  Future<String> summarizeRecentMessagesAsync(
    List<Map<String, dynamic>> history, {
    int limit = defaultRecentDialogueRoundsLimit,
    int? roundsLimit,
    int roundsOlderLimit = defaultOlderRecentDialogueRoundsLimit,
    Future<String> Function(String transcript)? summarizer,
  }) async {
    final raw = _summarizeRecentMessages(
      history,
      limit: limit,
      roundsLimit: roundsLimit,
      roundsOlderLimit: roundsOlderLimit,
    );
    if (raw.isEmpty) return '';
    if (summarizer == null) return raw;
    try {
      final compressed = await summarizer(raw);
      final result = compressed.trim();
      if (result.isEmpty) return raw;
      if (AssistantContentFilters.isDegradedText(result)) return raw;
      final sanitized = _sanitizeForSummary(result);
      return sanitized.isNotEmpty ? sanitized : raw;
    } catch (_) {
      return raw;
    }
  }

  String buildTopicTitle(String userQuery) {
    final text = userQuery.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (text.isEmpty) return _defaultTopicTitle;
    final maxLen = math.min(18, text.length);
    return text.substring(0, maxLen);
  }

  String buildTopicSummary({
    required String userQuery,
    required String assistantReply,
  }) {
    final query = userQuery.trim();
    final answer = assistantReply.trim();
    if (query.isEmpty && answer.isEmpty) return '';
    final shortAnswer = answer.length > 80 ? '${answer.substring(0, 80)}...' : answer;
    return '$query\n$shortAnswer'.trim();
  }

  String _summarizeRecentMessages(
    List<Map<String, dynamic>> history, {
    int limit = defaultRecentDialogueRoundsLimit,
    int? roundsLimit,
    int roundsOlderLimit = defaultOlderRecentDialogueRoundsLimit,
  }) {
    if (history.isEmpty) {
      return '';
    }
    if ((roundsLimit ?? 0) > 0) {
      final transcript = buildRecentDialogueRoundsTranscript(
        buildRecentDialogueRounds(
          history,
          limit: roundsLimit!,
          olderLimit: roundsOlderLimit,
        ),
      );
      if (transcript.isNotEmpty) {
        return transcript;
      }
    }
    final segment = history.length <= limit
        ? history
        : history.sublist(history.length - limit);
    return segment
        .map((m) {
          final role = m['role'] ?? 'unknown';
          final content = _sanitizeForSummary(
            _bestAssistantDisplayCandidate(m),
          );
          if (content.isEmpty) return null;
          return '$role: $content';
        })
        .where((line) => line != null)
        .join('\n');
  }

  String _sanitizeForSummary(String raw) {
    if (raw.isEmpty) return '';
    final stripped = _stripXmlToolCalls(raw).trim();
    if (stripped.isEmpty) return '';
    if (stripped.trimLeft().startsWith('{')) {
      try {
        final start = stripped.indexOf('{');
        final decoded = _jsonDecodeFirst(stripped.substring(start));
        if (decoded is Map) {
          final um = (decoded['userMarkdown'] as String?)?.trim() ?? '';
          if (um.isNotEmpty &&
              !um.startsWith('{') &&
              !AssistantContentFilters.isProgressPlaceholder(um) &&
              !_containsInternalHistoryText(um)) {
            return um;
          }
          final summary = (decoded['summary'] as String?)?.trim() ?? '';
          if (summary.isNotEmpty &&
              !summary.startsWith('{') &&
              !AssistantContentFilters.isProgressPlaceholder(summary) &&
              !_containsInternalHistoryText(summary)) {
            return summary;
          }
          final result = decoded['result'];
          if (result is Map) {
            final text =
                (result['text'] as String?)?.trim() ??
                (result['summary'] as String?)?.trim() ??
                '';
            if (text.isNotEmpty &&
                !AssistantContentFilters.isProgressPlaceholder(text) &&
                !_containsInternalHistoryText(text)) {
              return text;
            }
          }
          return '';
        }
      } catch (_) {}
    }
    if (_containsInternalHistoryText(stripped)) return '';
    if (AssistantContentFilters.isDegradedText(stripped)) return '';
    if (AssistantContentFilters.isProgressPlaceholder(stripped)) return '';
    return stripped;
  }

  Object? _jsonDecodeFirst(String text) {
    try {
      return jsonDecode(text);
    } catch (_) {
      return null;
    }
  }

  String _bestAssistantDisplayCandidate(Map<String, dynamic> message) {
    final candidates = <String>[
      resolvePersistedAssistantDisplayPlainText(message),
      resolvePersistedAssistantDisplayMarkdown(message),
      (message['content'] ?? '').toString(),
    ];
    for (final candidate in candidates) {
      final sanitized = _sanitizeForSummary(candidate);
      if (sanitized.isNotEmpty) return sanitized;
    }
    return '';
  }

  static final RegExp _xmlToolCallTagRe = RegExp(
    r'<tool_call>[\s\S]*?</tool_call>|'
    r'<function=[^>]+>[\s\S]*?</function>|'
    r'<tool_call>|</tool_call>|'
    r'<function=[^>]*>|</function>|'
    r'<parameter=[^>]*>[\s\S]*?</parameter>|'
    r'</?parameter[^>]*>',
  );

  String _stripXmlToolCalls(String text) =>
      text.replaceAll(_xmlToolCallTagRe, '').trim();

  bool _containsInternalHistoryText(String text) {
    if (text.trim().isEmpty) return false;
    const fragments = <String>[
      'contractId',
      'assistant_turn',
      'turnPhase',
      'queryTasks',
      'tool_call',
      '<tool_call>',
      'provider',
      'machineEnvelope',
      '正在调用工具',
    ];
    for (final fragment in fragments) {
      if (text.contains(fragment)) return true;
    }
    return false;
  }

  static const String _defaultTopicTitle = '全部历史';
}
