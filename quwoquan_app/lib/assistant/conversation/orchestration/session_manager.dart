// ASSISTANT_WEAK_TYPE: EXTENSION_MAP — 会话存储加载/合并历史 Map；入口 assistantJsonAsStringKeyedMap。

import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:quwoquan_app/assistant/contracts/assistant_journey.dart';
import 'package:quwoquan_app/assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/assistant/contracts/preference_fact.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/recent_dialogue_rounds.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';
import 'package:quwoquan_app/assistant/memory/storage/assistant_storage_path.dart';

class AssistantSessionManager {
  AssistantSessionManager({String? storagePath})
    : _pathFuture = storagePath != null
          ? Future<String>.value(storagePath)
          : getPersonalAssistantStoragePath('sessions.json');

  final Future<String> _pathFuture;
  // ignore: unused_field
  static const String _assistantEntrySessionId = 'assistant';
  static const String _defaultTopicTitle = '全部历史';
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
    _sessions.clear();
    _sessionMeta.clear();
    _activeSessionId = '';
    await AssistantContentFilters.ensureLoaded();
    final path = await _pathFuture;
    final file = File(path);
    if (!await file.exists()) return;
    String rawText;
    try {
      rawText = await file.readAsString();
    } on FileSystemException {
      // 历史 session 文件损坏或存在非法编码时，直接跳过加载，
      // 避免污染本轮运行或让 E2E 因历史垃圾文件崩溃。
      return;
    } on FormatException {
      return;
    }
    if (rawText.trim().isEmpty) return;
    Object? decoded;
    try {
      decoded = jsonDecode(rawText);
    } on FormatException {
      await _wipePersistedHistoryFile(file);
      return;
    }
    final root = assistantJsonAsStringKeyedMap(decoded);
    if (root == null) {
      await _wipePersistedHistoryFile(file);
      return;
    }
    if ((root['version'] ?? '').toString().trim() !=
        assistantHistoryStorageVersion) {
      await _wipePersistedHistoryFile(file);
      return;
    }
    final rawSessions = root['sessions'];
    if (rawSessions is! Map) {
      await _wipePersistedHistoryFile(file);
      return;
    }
    final rawMetadata =
        (root['metadata'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    var mutated = false;
    for (final entry in rawSessions.entries) {
      final key = entry.key.toString();
      final value = entry.value;
      if (value is! List) {
        mutated = true;
        continue;
      }
      final normalized = _normalizeLoadedSessionMessages(
        value
            .whereType<Map>()
            .map((item) => item.map((k, v) => MapEntry(k.toString(), v)))
            .toList(growable: false),
      );
      if (normalized == null || normalized.isEmpty) {
        mutated = true;
        continue;
      }
      _sessions[key] = normalized.toList(growable: true);
      final meta = rawMetadata[key];
      if (meta is Map) {
        _sessionMeta[key] = meta.cast<String, dynamic>();
      }
    }
    final activeSessionId = (root['activeSessionId'] ?? '').toString().trim();
    if (_sessions.containsKey(activeSessionId)) {
      _activeSessionId = activeSessionId;
    } else if (activeSessionId.isNotEmpty) {
      mutated = true;
    }
    if (mutated) {
      await save();
    }
  }

  Future<void> save() async {
    final path = await _pathFuture;
    final file = File(path);
    await file.parent.create(recursive: true);
    final payload = <String, dynamic>{
      'version': assistantHistoryStorageVersion,
      'activeSessionId': _activeSessionId,
      'sessions': _sessions,
      'metadata': _sessionMeta,
    };
    await file.writeAsString(jsonEncode(payload));
  }

  Future<void> _wipePersistedHistoryFile(File file) async {
    _sessions.clear();
    _sessionMeta.clear();
    _activeSessionId = '';
    await file.parent.create(recursive: true);
    await file.writeAsString(
      jsonEncode(<String, dynamic>{
        'version': assistantHistoryStorageVersion,
        'activeSessionId': '',
        'sessions': const <String, dynamic>{},
        'metadata': const <String, dynamic>{},
      }),
    );
  }

  List<Map<String, dynamic>>? _normalizeLoadedSessionMessages(
    List<Map<String, dynamic>> rawMessages,
  ) {
    final normalized = <Map<String, dynamic>>[];
    for (final raw in rawMessages) {
      final message = _normalizeLoadedMessage(raw);
      if (message == null) {
        return null;
      }
      if (_isDegradedAssistantMessage(message)) {
        return null;
      }
      normalized.add(message);
    }
    return normalized;
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
    final history = getOrCreateSession(sessionId);
    if (history.isEmpty) {
      return const <Map<String, dynamic>>[];
    }
    return buildRecentDialogueRounds(history, limit: limit);
  }

  String summarizeRecent(
    String sessionId, {
    int limit = 8,
    int? roundsLimit,
  }) {
    final normalizedRoundsLimit = roundsLimit ?? 0;
    if (normalizedRoundsLimit > 0) {
      final transcript = buildRecentDialogueRoundsTranscript(
        recentDialogueRounds(sessionId, limit: normalizedRoundsLimit),
      );
      if (transcript.isNotEmpty) {
        return transcript;
      }
    }
    final history = getOrCreateSession(sessionId);
    if (history.isEmpty) return '';
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

  /// 将 assistant 回复内容净化为可读摘要文本：
  /// - 若是 canonical assistant_turn JSON，提取 userMarkdown 或 result.text
  /// - 若是降级文本，跳过
  String _sanitizeForSummary(String raw) {
    if (raw.isEmpty) return '';
    final stripped = _stripXmlToolCalls(raw).trim();
    if (stripped.isEmpty) return '';
    // 尝试提取 JSON 里的 userMarkdown
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
    // 跳过降级/错误文本（统一使用 AssistantContentFilters，不在此处维护独立词表）
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

  /// LLM-based async summarization. Falls back to sanitized concatenation if [summarizer] is null
  /// or returns empty. This replaces the naive string concatenation with semantic compression.
  Future<String> summarizeRecentAsync(
    String sessionId, {
    int limit = 8,
    int? roundsLimit,
    Future<String> Function(String transcript)? summarizer,
  }) async {
    final raw = summarizeRecent(
      sessionId,
      limit: limit,
      roundsLimit: roundsLimit,
    );
    if (raw.isEmpty) return '';
    if (summarizer == null) return raw;
    try {
      final compressed = await summarizer(raw);
      // 若 summarizer 失败（返回降级文本），降级到原始 transcript
      final result = compressed.trim();
      if (result.isEmpty) return raw;
      if (AssistantContentFilters.isDegradedText(result)) return raw;
      final sanitized = _sanitizeForSummary(result);
      return sanitized.isNotEmpty ? sanitized : raw;
    } catch (_) {
      return raw;
    }
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

  String topicTitleOf(String sessionId) {
    final raw = (_sessionMeta[sessionId]?['topicTitle'] ?? '')
        .toString()
        .trim();
    if (raw.isNotEmpty) return raw;
    return _defaultTopicTitle;
  }

  void updateSessionTopicSummary({
    required String sessionId,
    required String latestUserQuery,
    required String latestAssistantReply,
  }) {
    final now = DateTime.now().toIso8601String();
    final title = _buildTopicTitle(latestUserQuery);
    final summary = _buildTopicSummary(
      userQuery: latestUserQuery,
      assistantReply: latestAssistantReply,
    );
    final existing = _sessionMeta[sessionId] ?? <String, dynamic>{};
    _sessionMeta[sessionId] = <String, dynamic>{
      ...existing,
      'topicTitle': title,
      'topicSummary': summary,
      'lastUserQuery': latestUserQuery,
      'lastAssistantReply': latestAssistantReply,
      'updatedAt': now,
    };
  }

  List<AssistantSessionDescriptor> listSessionDescriptors() {
    final items = _sessions.entries
        .map((entry) {
          final sessionId = entry.key;
          final messages = entry.value;
          final meta = _sessionMeta[sessionId] ?? const <String, dynamic>{};
          final sessionFacts = sessionPreferenceFactsOf(sessionId);
          final longTermFacts = longTermPreferenceFactsOf(sessionId);
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
            isActive: sessionId == _activeSessionId,
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

  List<PreferenceFact> sessionPreferenceFactsOf(String sessionId) {
    return _collectPreferenceFacts(
      sessionId,
      selector: (turn) => turn.sessionPreferenceFacts,
    );
  }

  List<PreferenceFact> longTermPreferenceFactsOf(String sessionId) {
    return _collectPreferenceFacts(
      sessionId,
      selector: (turn) => turn.longTermPreferenceFacts,
    );
  }

  List<PreferenceFact> _collectPreferenceFacts(
    String sessionId, {
    required List<PreferenceFact> Function(AssistantTurnOutput turn) selector,
  }) {
    final messages = _sessions[sessionId] ?? const <Map<String, dynamic>>[];
    final collected = <PreferenceFact>[];
    final seen = <String>{};
    for (final message in messages) {
      if ((message['role'] ?? '').toString() != 'assistant') continue;
      final turn = _tryParseAssistantTurn(
        (message['content'] as String?) ?? '',
      );
      if (turn == null) continue;
      for (final fact in selector(turn)) {
        final key = fact.factId.isNotEmpty
            ? fact.factId
            : '${fact.scope}:${fact.key}:${fact.value}';
        if (!seen.add(key)) continue;
        collected.add(fact);
      }
    }
    return collected;
  }

  AssistantTurnOutput? _tryParseAssistantTurn(String raw) {
    if (raw.trimLeft().isEmpty || !raw.trimLeft().startsWith('{')) return null;
    final decoded = _jsonDecodeFirst(raw);
    if (decoded is! Map) return null;
    return tryParseAssistantTurnOutput(decoded.cast<String, dynamic>());
  }

  String _createAssistantSessionId() {
    return 'assistant_${DateTime.now().millisecondsSinceEpoch}';
  }

  String _buildTopicTitle(String userQuery) {
    final text = userQuery.trim().replaceAll(RegExp(r'\s+'), ' ');
    if (text.isEmpty) return _defaultTopicTitle;
    final maxLen = math.min(18, text.length);
    return text.substring(0, maxLen);
  }

  String _buildTopicSummary({
    required String userQuery,
    required String assistantReply,
  }) {
    final query = userQuery.trim();
    final answer = assistantReply.trim();
    if (query.isEmpty && answer.isEmpty) return '';
    final shortAnswer = answer.length > 80
        ? '${answer.substring(0, 80)}...'
        : answer;
    return '$query\n$shortAnswer'.trim();
  }

  /// 判断一条消息是否是降级/错误/JSON原文内容，加载时需过滤，避免污染后续 LLM 历史。
  bool _isDegradedAssistantMessage(Map<String, dynamic> m) {
    final role = m['role']?.toString() ?? '';
    if (role != 'assistant') return false;
    final candidates = <String>[
      resolvePersistedAssistantDisplayPlainText(m),
      resolvePersistedAssistantDisplayMarkdown(m),
      (m['content'] ?? '').toString(),
    ];
    for (final candidate in candidates) {
      final raw = _stripXmlToolCalls(candidate).trim();
      if (raw.isEmpty) continue;
      if (_sanitizeForSummary(raw).isNotEmpty) {
        continue;
      }
      // 若原始 JSON / envelope 能提取出稳定的用户可见文本，则视为可保留；
      // 否则再按内部协议片段或降级文本过滤，避免历史污染。
      if (AssistantContentFilters.isNotDisplayable(raw) ||
          _containsInternalHistoryText(raw)) {
        return true;
      }
    }
    return false;
  }

  Map<String, dynamic>? _normalizeLoadedMessage(Map<String, dynamic> raw) {
    final normalized = Map<String, dynamic>.from(raw);
    final role = (normalized['role'] ?? '').toString();
    if (role != 'assistant') return normalized;
    final canonical = normalizeCanonicalPersistedAssistantTurnMessage(
      normalized,
    );
    if (canonical == null) {
      return null;
    }
    final displayPlain = _sanitizeForSummary(
      resolvePersistedAssistantDisplayPlainText(canonical),
    );
    final displayMarkdown = _sanitizeForSummary(
      resolvePersistedAssistantDisplayMarkdown(canonical),
    );
    final content = _sanitizeForSummary(
      (canonical['content'] ?? '').toString(),
    );
    final best = [
      displayPlain,
      displayMarkdown,
      content,
    ].firstWhere((item) => item.trim().isNotEmpty, orElse: () => '');
    final hasReplayableProcessState =
        !resolvePersistedAssistantJourney(canonical).isEmpty ||
        resolvePersistedAssistantProcessTimeline(canonical).isNotEmpty ||
        hasAssistantDisplayState(
          resolvePersistedAssistantDisplayState(canonical),
        );
    if (best.isEmpty && !hasReplayableProcessState) {
      return null;
    }
    canonical['content'] = best;
    final runArtifacts = (canonical['runArtifacts'] as Map?)
        ?.cast<String, dynamic>();
    if (runArtifacts != null && runArtifacts.isNotEmpty) {
      final sanitizedArtifacts = Map<String, dynamic>.from(runArtifacts)
        ..remove('machineEnvelope');
      canonical['runArtifacts'] = sanitizedArtifacts;
    }
    return canonical;
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
}
