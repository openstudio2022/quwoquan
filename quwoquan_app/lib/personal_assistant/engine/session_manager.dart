import 'dart:convert';
import 'dart:io';

import 'package:quwoquan_app/personal_assistant/storage/personal_assistant_storage_path.dart';

class AssistantSessionManager {
  AssistantSessionManager({
    String? storagePath,
  }) : _pathFuture = storagePath != null
            ? Future<String>.value(storagePath)
            : getPersonalAssistantStoragePath('sessions.json');

  final Future<String> _pathFuture;
  final Map<String, List<Map<String, String>>> _sessions = <String, List<Map<String, String>>>{};
  Map<String, List<Map<String, String>>> get sessions => _sessions;

  List<Map<String, String>> getOrCreateSession(String sessionId) {
    return _sessions.putIfAbsent(sessionId, () => <Map<String, String>>[]);
  }

  Future<void> load() async {
    final path = await _pathFuture;
    final file = File(path);
    if (!await file.exists()) return;
    final raw = jsonDecode(await file.readAsString());
    if (raw is! Map) return;
    for (final entry in raw.entries) {
      final key = entry.key.toString();
      final value = entry.value;
      if (value is! List) continue;
      _sessions[key] = value
          .whereType<Map>()
          .map((m) => m.map((k, v) => MapEntry(k.toString(), v.toString())))
          .toList(growable: true);
    }
  }

  Future<void> save() async {
    final path = await _pathFuture;
    final file = File(path);
    await file.parent.create(recursive: true);
    await file.writeAsString(jsonEncode(_sessions));
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
        .map((m) => '${m['role'] ?? 'unknown'}: ${m['content'] ?? ''}')
        .join('\n');
  }
}
