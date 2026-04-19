// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 会话存储加载/合并历史 Map；入口 assistantJsonAsStringKeyedMap。

import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_session_history_state.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'assistant_session_store.dart';
import 'assistant_session_projection_service.dart';

class AssistantSessionManager {
  static const AssistantSessionProjectionService _projectionService =
      AssistantSessionProjectionService();

  AssistantSessionManager({String? storagePath})
    : _store = AssistantSessionStore(storagePath: storagePath);

  final AssistantSessionStore _store;
  // ignore: unused_field
  static const String _assistantEntrySessionId = 'assistant';
  final Map<String, List<Map<String, dynamic>>> _sessions =
      <String, List<Map<String, dynamic>>>{};
  final Map<String, Map<String, dynamic>> _sessionMeta =
      <String, Map<String, dynamic>>{};
  String _activeSessionId = '';
  Map<String, List<Map<String, dynamic>>> get sessions => _sessions;
  String get activeSessionId => _activeSessionId;

  List<Map<String, dynamic>> getOrCreateSession(String sessionId) {
    return _sessions.putIfAbsent(sessionId, () => <Map<String, dynamic>>[]);
  }

  Future<void> load() async {
    await AssistantContentFilters.ensureLoaded();
    final snapshot = await _store.load();
    _sessions
      ..clear()
      ..addAll(snapshot.sessions);
    _sessionMeta
      ..clear()
      ..addAll(snapshot.metadata);
    _activeSessionId = snapshot.activeSessionId;
  }

  Future<void> save() async {
    await _store.save(
      AssistantSessionStoreSnapshot(
        sessions: Map<String, List<Map<String, dynamic>>>.from(_sessions),
        metadata: Map<String, Map<String, dynamic>>.from(_sessionMeta),
        activeSessionId: _activeSessionId,
      ),
    );
  }

  void appendMessage({
    required String sessionId,
    required String role,
    required String content,
    Map<String, dynamic> metadata = const <String, dynamic>{},
  }) {
    final messages = getOrCreateSession(sessionId);
    messages.add(<String, dynamic>{
      'role': role,
      'content': content,
      ...metadata,
    });
  }

  List<Map<String, dynamic>> recentDialogueRounds(
    String sessionId, {
    int limit = defaultRecentDialogueRoundsLimit,
  }) {
    return _projectionService.recentDialogueRounds(
      getOrCreateSession(sessionId),
      limit: limit,
    );
  }

  String summarizeRecent(
    String sessionId, {
    int limit = 8,
    int? roundsLimit,
  }) {
    return _projectionService.summarizeRecent(
      getOrCreateSession(sessionId),
      limit: limit,
      roundsLimit: roundsLimit,
    );
  }

  Future<String> summarizeRecentAsync(
    String sessionId, {
    int limit = 8,
    int? roundsLimit,
    Future<String> Function(String transcript)? summarizer,
  }) {
    return _projectionService.summarizeRecentAsync(
      getOrCreateSession(sessionId),
      limit: limit,
      roundsLimit: roundsLimit,
      summarizer: summarizer,
    );
  }

  String resolveAssistantSessionForQuery(String latestUserQuery) {
    latestUserQuery.trim();
    final current = ensureAssistantActiveSession();
    _activeSessionId = current;
    return current;
  }

  String ensureAssistantActiveSession() {
    if (_activeSessionId.isNotEmpty &&
        _sessions.containsKey(_activeSessionId)) {
      return _activeSessionId;
    }
    String candidate = '';
    DateTime? latestTime;
    for (final entry in _sessionMeta.entries) {
      final updatedAt = DateTime.tryParse(
        (entry.value['updatedAt'] ?? '').toString(),
      );
      if (updatedAt == null) continue;
      if (latestTime == null || updatedAt.isAfter(latestTime)) {
        latestTime = updatedAt;
        candidate = entry.key;
      }
    }
    if (candidate.isEmpty && _sessions.isNotEmpty) {
      candidate = _sessions.keys.first;
    }
    if (candidate.isEmpty) {
      candidate = _createAssistantSessionId();
      _sessions[candidate] = <Map<String, dynamic>>[];
    }
    _activeSessionId = candidate;
    return _activeSessionId;
  }

  void switchAssistantSession(String sessionId) {
    if (!_sessions.containsKey(sessionId)) return;
    _activeSessionId = sessionId;
  }

  String _createAssistantSessionId() {
    return 'assistant_${DateTime.now().millisecondsSinceEpoch}';
  }

  String topicTitleOf(String sessionId) {
    return _projectionService.topicTitleOf(_sessionMeta, sessionId);
  }

  void updateSessionTopicSummary({
    required String sessionId,
    required String latestUserQuery,
    required String latestAssistantReply,
  }) {
    _projectionService.updateSessionTopicSummary(
      sessionMeta: _sessionMeta,
      sessionId: sessionId,
      latestUserQuery: latestUserQuery,
      latestAssistantReply: latestAssistantReply,
    );
  }

  List<AssistantSessionDescriptor> listSessionDescriptors() {
    return _projectionService.listSessionDescriptors(
      sessions: _sessions,
      sessionMeta: _sessionMeta,
      activeSessionId: _activeSessionId,
    );
  }

  List<PreferenceFact> sessionPreferenceFactsOf(String sessionId) {
    return _projectionService.sessionPreferenceFactsOf(
      _sessions[sessionId] ?? const <Map<String, dynamic>>[],
    );
  }

  List<PreferenceFact> longTermPreferenceFactsOf(String sessionId) {
    return _projectionService.longTermPreferenceFactsOf(
      _sessions[sessionId] ?? const <Map<String, dynamic>>[],
    );
  }

  AssistantSessionHistoryState historyStateOf(String sessionId) {
    final raw = _sessionMeta[sessionId]?['historyState'];
    if (raw is Map) {
      final parsed = AssistantSessionHistoryState.fromJson(
        raw.cast<String, dynamic>(),
      );
      if (!parsed.isEmpty) {
        return parsed;
      }
    }
    final messages = _sessions[sessionId] ?? const <Map<String, dynamic>>[];
    if (messages.isEmpty) {
      return const AssistantSessionHistoryState();
    }
    final preferenceFacts = <PreferenceFact>[
      ...sessionPreferenceFactsOf(sessionId),
      ...longTermPreferenceFactsOf(sessionId),
    ];
    final dedupedPreferences = <String, PreferenceFact>{};
    for (final fact in preferenceFacts) {
      final key = fact.factId.trim().isNotEmpty
          ? fact.factId.trim()
          : '${fact.scope.trim()}:${fact.key.trim()}:${fact.value.trim()}';
      if (key.trim().isEmpty || dedupedPreferences.containsKey(key)) {
        continue;
      }
      dedupedPreferences[key] = fact;
    }
    return AssistantSessionHistoryState(
      sessionSummary: (_sessionMeta[sessionId]?['topicSummary'] ?? '')
          .toString()
          .trim(),
      userPreferences: dedupedPreferences.values.toList(growable: false),
    );
  }

  void updateSessionHistoryState({
    required String sessionId,
    required AssistantSessionHistoryState historyState,
  }) {
    final existing = _sessionMeta[sessionId] ?? <String, dynamic>{};
    _sessionMeta[sessionId] = <String, dynamic>{
      ...existing,
      'historyState': historyState.toJson(),
      'updatedAt': DateTime.now().toIso8601String(),
    };
  }
}
