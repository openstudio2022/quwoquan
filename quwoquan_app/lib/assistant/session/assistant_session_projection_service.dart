import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/memory/preference/preference_fact_service.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/session/session_summary_builder.dart';

class AssistantSessionProjectionService {
  const AssistantSessionProjectionService({
    PreferenceFactService preferenceFactService = const PreferenceFactService(),
    AssistantSessionSummaryBuilder summaryBuilder =
        const AssistantSessionSummaryBuilder(),
  })  : _preferenceFactService = preferenceFactService,
        _summaryBuilder = summaryBuilder;

  final PreferenceFactService _preferenceFactService;
  final AssistantSessionSummaryBuilder _summaryBuilder;

  List<Map<String, dynamic>> recentDialogueRounds(
    List<Map<String, dynamic>> history, {
    int limit = defaultRecentDialogueRoundsLimit,
    int olderLimit = defaultOlderRecentDialogueRoundsLimit,
  }) {
    if (history.isEmpty) {
      return const <Map<String, dynamic>>[];
    }
    return buildRecentDialogueRounds(
      history,
      limit: limit,
      olderLimit: olderLimit,
    );
  }

  String summarizeRecent(
    List<Map<String, dynamic>> history, {
    int limit = 8,
    int? roundsLimit,
    int roundsOlderLimit = defaultOlderRecentDialogueRoundsLimit,
  }) {
    return _summaryBuilder.summarizeRecentMessages(
      history,
      limit: limit,
      roundsLimit: roundsLimit,
      roundsOlderLimit: roundsOlderLimit,
    );
  }

  Future<String> summarizeRecentAsync(
    List<Map<String, dynamic>> history, {
    int limit = 8,
    int? roundsLimit,
    int roundsOlderLimit = defaultOlderRecentDialogueRoundsLimit,
    Future<String> Function(String transcript)? summarizer,
  }) {
    return _summaryBuilder.summarizeRecentMessagesAsync(
      history,
      limit: limit,
      roundsLimit: roundsLimit,
      roundsOlderLimit: roundsOlderLimit,
      summarizer: summarizer,
    );
  }

  String topicTitleOf(
    Map<String, Map<String, dynamic>> sessionMeta,
    String sessionId,
  ) {
    final raw = (sessionMeta[sessionId]?['topicTitle'] ?? '')
        .toString()
        .trim();
    if (raw.isNotEmpty) return raw;
    return _defaultTopicTitle;
  }

  void updateSessionTopicSummary({
    required Map<String, Map<String, dynamic>> sessionMeta,
    required String sessionId,
    required String latestUserQuery,
    required String latestAssistantReply,
  }) {
    final now = DateTime.now().toIso8601String();
    final title = _summaryBuilder.buildTopicTitle(latestUserQuery);
    final summary = _summaryBuilder.buildTopicSummary(
      userQuery: latestUserQuery,
      assistantReply: latestAssistantReply,
    );
    final existing = sessionMeta[sessionId] ?? <String, dynamic>{};
    sessionMeta[sessionId] = <String, dynamic>{
      ...existing,
      'topicTitle': title,
      'topicSummary': summary,
      'updatedAt': now,
    };
  }

  List<AssistantSessionDescriptor> listSessionDescriptors({
    required Map<String, List<Map<String, dynamic>>> sessions,
    required Map<String, Map<String, dynamic>> sessionMeta,
    required String activeSessionId,
  }) {
    final items = sessions.entries
        .map((entry) {
          final sessionId = entry.key;
          final messages = entry.value;
          final meta = sessionMeta[sessionId] ?? const <String, dynamic>{};
          final sessionFacts = sessionPreferenceFactsOf(messages);
          final longTermFacts = longTermPreferenceFactsOf(messages);
          final updatedAt = (meta['updatedAt'] ?? '').toString();
          final topicTitle = (meta['topicTitle'] ?? '').toString().trim();
          final topicSummary = (meta['topicSummary'] ?? '').toString().trim();
          return AssistantSessionDescriptor(
            sessionId: sessionId,
            messageCount: messages.length,
            lastMessage: messages.isEmpty
                ? ''
                : (messages.last['content'] ?? '').toString(),
            topicTitle: topicTitle.isEmpty ? _defaultTopicTitle : topicTitle,
            topicSummary: topicSummary,
            sessionPreferenceFactCount: sessionFacts.length,
            longTermPreferenceFactCount: longTermFacts.length,
            updatedAt: updatedAt,
            isActive: sessionId == activeSessionId,
          );
        })
        .toList(growable: false);
    items.sort((a, b) {
      final ta = DateTime.tryParse(a.updatedAt);
      final tb = DateTime.tryParse(b.updatedAt);
      if (ta == null && tb == null) return 0;
      if (ta == null) return 1;
      if (tb == null) return -1;
      return tb.compareTo(ta);
    });
    return items;
  }

  List<PreferenceFact> sessionPreferenceFactsOf(
    List<Map<String, dynamic>> messages,
  ) {
    return _preferenceFactService.collectPreferenceFactsFromMessages(
      messages,
      selector: (turn) => turn.sessionPreferenceFacts,
    );
  }

  List<PreferenceFact> longTermPreferenceFactsOf(
    List<Map<String, dynamic>> messages,
  ) {
    return _preferenceFactService.collectPreferenceFactsFromMessages(
      messages,
      selector: (turn) => turn.longTermPreferenceFacts,
    );
  }

  static const String _defaultTopicTitle = '全部历史';
}
