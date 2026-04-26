import 'dart:convert';
import 'dart:io' show File;

import 'package:flutter/services.dart' show rootBundle;

class PromptSnippetRenderer {
  PromptSnippetRenderer({
    this.assetPath = 'assets/assistant/prompts/global/prompt_snippets.md',
    Map<String, String>? seededSnippets,
  }) : _snippetCache = seededSnippets;

  final String assetPath;

  Map<String, String>? _snippetCache;
  Future<void>? _loading;

  Future<String> renderSnippet(
    String snippetId, {
    Map<String, dynamic> variables = const <String, dynamic>{},
  }) async {
    await _ensureLoaded();
    final raw = _snippetCache?[snippetId] ?? '';
    if (raw.isEmpty) return '';
    return _renderContent(raw, variables);
  }

  Future<void> _ensureLoaded() async {
    if (_snippetCache != null) return;
    _loading ??= () async {
      try {
        final raw = await rootBundle.loadString(assetPath);
        final loadedSnippets = _extractSnippets(raw);
        if (loadedSnippets.isNotEmpty) {
          _snippetCache = loadedSnippets;
          return;
        }
      } catch (_) {}
      final fallbackPaths = <String>[
        assetPath,
        'quwoquan_app/$assetPath',
        '../quwoquan_app/$assetPath',
        '../../quwoquan_app/$assetPath',
        '../$assetPath',
        '../../$assetPath',
        '../../../$assetPath',
      ];
      for (final candidate in fallbackPaths) {
        try {
          final file = File(candidate);
          if (!await file.exists()) continue;
          final raw = await file.readAsString();
          final loadedSnippets = _extractSnippets(raw);
          if (loadedSnippets.isEmpty) continue;
          _snippetCache = loadedSnippets;
          return;
        } catch (_) {
          // Try the next candidate path.
        }
      }
      _snippetCache = const <String, String>{};
    }();
    await _loading;
  }

  Map<String, String> _extractSnippets(String raw) {
    final snippets = <String, String>{};
    var buffer = StringBuffer();
    String? currentId;
    for (final line in const LineSplitter().convert(raw)) {
      final trimmed = line.trim();
      // 必须先于 “snippet:ID” 判断：`<!-- snippet:end -->` 也会被
      // `snippet:([A-Za-z0-9_.-]+)` 误匹配为 id=end 的开始标记。
      if (trimmed == '<!-- snippet:end -->') {
        final snippetId = currentId?.trim() ?? '';
        if (snippetId.isNotEmpty) {
          snippets[snippetId] = buffer.toString().trimRight();
        }
        currentId = null;
        buffer = StringBuffer();
        continue;
      }
      final startMatch = RegExp(
        r'^<!-- snippet:([A-Za-z0-9_.-]+) -->$',
      ).firstMatch(trimmed);
      if (startMatch != null) {
        currentId = startMatch.group(1);
        buffer = StringBuffer();
        continue;
      }
      if (currentId != null) {
        buffer.writeln(line);
      }
    }
    return snippets;
  }

  String _renderContent(String content, Map<String, dynamic> variables) {
    var rendered = content;
    for (final entry in variables.entries) {
      rendered = rendered.replaceAll(
        '{{${entry.key}}}',
        _stringify(entry.value),
      );
    }
    return rendered;
  }

  String _stringify(dynamic value) {
    if (value == null) return '';
    if (value is String) return value;
    if (value is num || value is bool) return '$value';
    if (value is Map || value is Iterable) {
      return jsonEncode(value);
    }
    return value.toString();
  }
}
