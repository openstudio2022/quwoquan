import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;

import 'package:quwoquan_app/personal_assistant/contracts/assistant_turn_contract.dart';
import 'package:quwoquan_app/personal_assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/personal_assistant/storage/personal_assistant_storage_path.dart';

class AssistantSessionManager {
  AssistantSessionManager({
    String? storagePath,
  }) : _pathFuture = storagePath != null
            ? Future<String>.value(storagePath)
            : getPersonalAssistantStoragePath('sessions.json');

  final Future<String> _pathFuture;
  // ignore: unused_field
  static const String _assistantEntrySessionId = 'assistant';
  static const String _defaultTopicTitle = '全部历史';
  final Map<String, List<Map<String, dynamic>>> _sessions = <String, List<Map<String, dynamic>>>{};
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
    final path = await _pathFuture;
    final file = File(path);
    if (!await file.exists()) return;
    final raw = jsonDecode(await file.readAsString());
    if (raw is! Map) return;
    if (raw['sessions'] is Map) {
      final rawSessions = (raw['sessions'] as Map).entries;
      for (final entry in rawSessions) {
        final key = entry.key.toString();
        final value = entry.value;
        if (value is! List) continue;
        _sessions[key] = value
            .whereType<Map>()
            .map((m) => m.map((k, v) => MapEntry(k.toString(), v)))
            .where((m) => !_isDegradedAssistantMessage(m))
            .toList(growable: true);
      }
      final metadata = raw['metadata'];
      if (metadata is Map) {
        for (final entry in metadata.entries) {
          final key = entry.key.toString();
          final value = entry.value;
          if (value is! Map) continue;
          _sessionMeta[key] = value.cast<String, dynamic>();
        }
      }
      _activeSessionId = (raw['activeSessionId'] ?? '').toString();
      return;
    }
    // 向后兼容 v1: 根对象直接是 sessionId -> message[].
    for (final entry in raw.entries) {
      final key = entry.key.toString();
      final value = entry.value;
      if (value is! List) continue;
      _sessions[key] = value
          .whereType<Map>()
          .map((m) => m.map((k, v) => MapEntry(k.toString(), v)))
          .where((m) => !_isDegradedAssistantMessage(m))
          .toList(growable: true);
    }
    // 迁移历史消息到当前契约版本（见 02-dart-coding §5.3）
    _migrateSessionsToCurrentContractVersion();
  }

  /// 将 session 中 assistant 消息的 contractVersion 从遗留版本升级到当前版本。
  ///
  /// 规则：读取 content 字符串，若 JSON 中 contractVersion 为遗留值（v2/v3），
  /// 更新为 [kAssistantTurnCurrentVersion] 后写回。加载完成后立即执行，保证内存中
  /// 的数据始终是当前版本，下次 save() 时自动持久化升级后的数据。
  void _migrateSessionsToCurrentContractVersion() {
    for (final messages in _sessions.values) {
      for (int i = 0; i < messages.length; i++) {
        final content = (messages[i]['content'] as String?) ?? '';
        if (content.trimLeft().isEmpty || content.trimLeft()[0] != '{') continue;
        try {
          final decoded = jsonDecode(content);
          if (decoded is! Map) continue;
          final version = (decoded['contractVersion'] as String?)?.trim() ?? '';
          // v2/v3 均需升级；v2 包裹格式不会存入 session（session 只存纯文本），无需处理
          if (version == kAssistantTurnLegacyVersion ||
              version == kAssistantTurnV2WrapKey) {
            final upgraded = Map<String, dynamic>.from(
              decoded.cast<String, dynamic>(),
            );
            upgraded['contractVersion'] = kAssistantTurnCurrentVersion;
            final updated = Map<String, dynamic>.from(messages[i]);
            updated['content'] = jsonEncode(upgraded);
            messages[i] = updated;
          }
        } catch (_) {
          // JSON 解析失败：跳过，保留原始内容
        }
      }
    }
  }

  Future<void> save() async {
    final path = await _pathFuture;
    final file = File(path);
    await file.parent.create(recursive: true);
    final payload = <String, dynamic>{
      'version': 'v2',
      'activeSessionId': _activeSessionId,
      'sessions': _sessions,
      'metadata': _sessionMeta,
    };
    await file.writeAsString(jsonEncode(payload));
  }

  void appendMessage({
    required String sessionId,
    required String role,
    required String content,
  }) {
    final messages = getOrCreateSession(sessionId);
    messages.add(<String, String>{
      'role': role,
      'content': content,
    });
  }

  String summarizeRecent(String sessionId, {int limit = 8}) {
    final history = getOrCreateSession(sessionId);
    if (history.isEmpty) return '';
    final segment = history.length <= limit ? history : history.sublist(history.length - limit);
    return segment
        .map((m) {
          final role = m['role'] ?? 'unknown';
          final raw = (m['content'] ?? '').toString().trim();
          // 过滤 JSON 格式回复和降级文本，只保留纯文本内容
          final content = _sanitizeForSummary(raw);
          if (content.isEmpty) return null;
          return '$role: $content';
        })
        .where((line) => line != null)
        .join('\n');
  }

  /// 将 assistant 回复内容净化为可读摘要文本：
  /// - 若是 JSON（assistant_turn_v2），提取 userMarkdown 或 result.text
  /// - 若是降级文本，跳过
  String _sanitizeForSummary(String raw) {
    if (raw.isEmpty) return '';
    // 跳过降级/错误文本（统一使用 AssistantContentFilters，不在此处维护独立词表）
    if (AssistantContentFilters.isDegradedText(raw)) return '';
    // 尝试提取 JSON 里的 userMarkdown
    if (raw.trimLeft().startsWith('{')) {
      try {
        final start = raw.indexOf('{');
        final decoded = _jsonDecodeFirst(raw.substring(start));
        if (decoded is Map) {
          final um = (decoded['userMarkdown'] as String?)?.trim() ?? '';
          if (um.isNotEmpty &&
              !um.startsWith('{') &&
              !AssistantContentFilters.isProgressPlaceholder(um)) {
            return um;
          }
          final result = decoded['result'];
          if (result is Map) {
            final text = (result['text'] as String?)?.trim() ??
                (result['summary'] as String?)?.trim() ?? '';
            if (text.isNotEmpty &&
                !AssistantContentFilters.isProgressPlaceholder(text)) {
              return text;
            }
          }
          return '';
        }
      } catch (_) {}
    }
    return raw;
  }

  dynamic _jsonDecodeFirst(String text) {
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
    Future<String> Function(String transcript)? summarizer,
  }) async {
    final raw = summarizeRecent(sessionId, limit: limit);
    if (raw.isEmpty) return '';
    if (summarizer == null) return raw;
    try {
      final compressed = await summarizer(raw);
      // 若 summarizer 失败（返回降级文本），降级到原始 transcript
      final result = compressed.trim();
      if (result.isEmpty) return raw;
      if (AssistantContentFilters.isDegradedText(result)) return raw;
      return result;
    } catch (_) {
      return raw;
    }
  }

  String resolveAssistantSessionForQuery(String latestUserQuery) {
    final current = ensureAssistantActiveSession();
    final query = latestUserQuery.trim();
    if (query.length < 6) return current;
    final currentMeta = _sessionMeta[current] ?? const <String, dynamic>{};
    final profile = [
      (currentMeta['topicTitle'] ?? '').toString(),
      (currentMeta['topicSummary'] ?? '').toString(),
      (currentMeta['lastUserQuery'] ?? '').toString(),
    ].join(' ');
    final similarity = _textSimilarity(query, profile);
    if (similarity >= 0.26 || !_isSessionMature(current)) {
      _activeSessionId = current;
      return current;
    }
    final nextId = _createAssistantSessionId();
    _activeSessionId = nextId;
    getOrCreateSession(nextId);
    return nextId;
  }

  String ensureAssistantActiveSession() {
    if (_activeSessionId.isNotEmpty && _sessions.containsKey(_activeSessionId)) {
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
    final raw = (_sessionMeta[sessionId]?['topicTitle'] ?? '').toString().trim();
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

  List<Map<String, dynamic>> listSessionDescriptors() {
    final items = _sessions.entries.map((entry) {
      final sessionId = entry.key;
      final messages = entry.value;
      final meta = _sessionMeta[sessionId] ?? const <String, dynamic>{};
      final updatedAt = (meta['updatedAt'] ?? '').toString();
      final topicTitle = (meta['topicTitle'] ?? '').toString().trim();
      final topicSummary = (meta['topicSummary'] ?? '').toString().trim();
      return <String, dynamic>{
        'sessionId': sessionId,
        'messageCount': messages.length,
        'lastMessage': messages.isEmpty ? '' : (messages.last['content'] ?? ''),
        'topicTitle': topicTitle.isEmpty ? _defaultTopicTitle : topicTitle,
        'topicSummary': topicSummary,
        'updatedAt': updatedAt,
        'isActive': sessionId == _activeSessionId,
      };
    }).toList(growable: false);
    items.sort((a, b) {
      final ta = DateTime.tryParse((a['updatedAt'] ?? '').toString());
      final tb = DateTime.tryParse((b['updatedAt'] ?? '').toString());
      if (ta == null && tb == null) return 0;
      if (ta == null) return 1;
      if (tb == null) return -1;
      return tb.compareTo(ta);
    });
    return items;
  }

  String _createAssistantSessionId() {
    return 'assistant_${DateTime.now().millisecondsSinceEpoch}';
  }

  bool _isSessionMature(String sessionId) {
    final size = _sessions[sessionId]?.length ?? 0;
    return size >= 4;
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
    final shortAnswer = answer.length > 80 ? '${answer.substring(0, 80)}...' : answer;
    return '$query\n$shortAnswer'.trim();
  }

  double _textSimilarity(String a, String b) {
    final setA = _tokenize(a);
    final setB = _tokenize(b);
    if (setA.isEmpty || setB.isEmpty) return 0;
    final intersection = setA.intersection(setB).length;
    final union = setA.union(setB).length;
    if (union == 0) return 0;
    return intersection / union;
  }

  Set<String> _tokenize(String text) {
    final lower = text.toLowerCase().trim();
    if (lower.isEmpty) return <String>{};
    final asciiTokens = lower
        .split(RegExp(r'[^a-z0-9\u4e00-\u9fff]+'))
        .where((item) => item.trim().isNotEmpty)
        .toSet();
    final chars = lower.runes
        .map((r) => String.fromCharCode(r))
        .where((ch) => RegExp(r'[a-z0-9\u4e00-\u9fff]').hasMatch(ch))
        .toList(growable: false);
    for (var i = 0; i < chars.length - 1; i++) {
      asciiTokens.add('${chars[i]}${chars[i + 1]}');
    }
    return asciiTokens;
  }

  /// 判断一条消息是否是降级/错误/JSON原文内容，加载时需过滤，避免污染后续 LLM 历史。
  bool _isDegradedAssistantMessage(Map<String, dynamic> m) {
    final role = m['role']?.toString() ?? '';
    if (role != 'assistant') return false;
    final content = m['content']?.toString().trim() ?? '';
    if (content.isEmpty) return false;
    // 统一使用 AssistantContentFilters，消除此处独立维护词表的漂移风险。
    // JSON 信封、进度占位、降级/错误文本均不应写回 session 历史。
    return AssistantContentFilters.isNotDisplayable(content);
  }
}
