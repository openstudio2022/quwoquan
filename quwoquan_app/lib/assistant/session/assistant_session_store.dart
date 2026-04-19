import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/assistant/persistence/assistant_storage_path.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_content_filters.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_display_state_projection.dart';
import 'package:quwoquan_app/assistant/protocol/assistant_session_wire.dart';
import 'package:quwoquan_app/assistant/protocol/persisted_assistant_turn.dart';

class AssistantSessionStore {
  AssistantSessionStore({String? storagePath})
    : _pathFuture = storagePath != null
          ? Future<String>.value(storagePath)
          : getPersonalAssistantStoragePath('sessions.json');

  final Future<String> _pathFuture;

  Future<AssistantSessionStoreSnapshot> load() async {
    final file = File(await _pathFuture);
    if (!await file.exists()) {
      return const AssistantSessionStoreSnapshot();
    }
    String rawText;
    try {
      rawText = await file.readAsString();
    } on FileSystemException {
      return const AssistantSessionStoreSnapshot();
    } on FormatException {
      return const AssistantSessionStoreSnapshot();
    }
    if (rawText.trim().isEmpty) {
      return const AssistantSessionStoreSnapshot();
    }
    Object? decoded;
    try {
      decoded = jsonDecode(rawText);
    } on FormatException {
      return await _wipePersistedHistoryFile(file);
    }
    final root = assistantJsonAsStringKeyedMap(decoded);
    if (root == null) {
      return await _wipePersistedHistoryFile(file);
    }
    if ((root['version'] ?? '').toString().trim() != assistantHistoryStorageVersion) {
      return await _wipePersistedHistoryFile(file);
    }
    final rawSessions = root['sessions'];
    if (rawSessions is! Map) {
      return await _wipePersistedHistoryFile(file);
    }
    final sessions = <String, List<Map<String, dynamic>>>{};
    var mutated = false;
    final metadata = <String, Map<String, dynamic>>{};
    final rawMetadata = root['metadata'];
    if (rawMetadata is Map) {
      for (final entry in rawMetadata.entries) {
        final key = entry.key.toString();
        final value = entry.value;
        if (value is Map) {
          metadata[key] = value
              .map((k, v) => MapEntry(k.toString(), v))
              .cast<String, dynamic>();
        } else if (value != null) {
          mutated = true;
        }
      }
    } else if (rawMetadata != null) {
      mutated = true;
    }
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
      sessions[key] = normalized.toList(growable: true);
    }
    final activeSessionId = (root['activeSessionId'] ?? '').toString().trim();
    if (!sessions.containsKey(activeSessionId) && activeSessionId.isNotEmpty) {
      mutated = true;
    }
    final snapshot = AssistantSessionStoreSnapshot(
      sessions: sessions,
      metadata: metadata
          .map((key, value) => MapEntry(key, Map<String, dynamic>.from(value))),
      activeSessionId: sessions.containsKey(activeSessionId) ? activeSessionId : '',
    );
    if (mutated) {
      await save(snapshot);
    }
    return snapshot;
  }

  Future<void> save(AssistantSessionStoreSnapshot snapshot) async {
    final file = File(await _pathFuture);
    await file.parent.create(recursive: true);
    await file.writeAsString(
      jsonEncode(<String, dynamic>{
        'version': assistantHistoryStorageVersion,
        'activeSessionId': snapshot.activeSessionId,
        'sessions': snapshot.sessions,
        'metadata': snapshot.metadata,
      }),
    );
  }

  Future<AssistantSessionStoreSnapshot> wipe() async {
    final file = File(await _pathFuture);
    return _wipePersistedHistoryFile(file);
  }

  Future<AssistantSessionStoreSnapshot> _wipePersistedHistoryFile(File file) async {
    final snapshot = const AssistantSessionStoreSnapshot();
    await file.parent.create(recursive: true);
    await file.writeAsString(
      jsonEncode(<String, dynamic>{
        'version': assistantHistoryStorageVersion,
        'activeSessionId': '',
        'sessions': const <String, dynamic>{},
        'metadata': const <String, dynamic>{},
      }),
    );
    return snapshot;
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
        resolvePersistedAssistantJourney(canonical).stages.isNotEmpty ||
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

class AssistantSessionStoreSnapshot {
  const AssistantSessionStoreSnapshot({
    this.sessions = const <String, List<Map<String, dynamic>>>{},
    this.metadata = const <String, Map<String, dynamic>>{},
    this.activeSessionId = '',
  });

  final Map<String, List<Map<String, dynamic>>> sessions;
  final Map<String, Map<String, dynamic>> metadata;
  final String activeSessionId;
}
