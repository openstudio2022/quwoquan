import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;

class ToolMetadataRegistry {
  ToolMetadataRegistry({
    this.manifestAssetPath = 'assets/personal_assistant/tools/manifest.json',
  });

  final String manifestAssetPath;
  Map<String, dynamic> _catalog = const <String, dynamic>{};
  Future<void>? _loadingFuture;
  bool _loaded = false;

  Future<void> ensureLoaded() async {
    if (_loaded) return;
    _loadingFuture ??= _load();
    await _loadingFuture;
  }

  Future<void> _load() async {
    try {
      final manifestRaw = await _loadText(manifestAssetPath);
      final manifestDecoded = jsonDecode(manifestRaw);
      if (manifestDecoded is! Map) {
        _catalog = const <String, dynamic>{};
        _loaded = true;
        return;
      }
      final catalogPath =
          (manifestDecoded['catalogPath'] as String?)?.trim() ?? '';
      if (catalogPath.isEmpty) {
        _catalog = const <String, dynamic>{};
        _loaded = true;
        return;
      }
      final catalogRaw = await _loadText(catalogPath);
      final catalogDecoded = jsonDecode(catalogRaw);
      if (catalogDecoded is! Map) {
        _catalog = const <String, dynamic>{};
        _loaded = true;
        return;
      }
      _catalog = catalogDecoded.cast<String, dynamic>();
      _loaded = true;
    } catch (_) {
      _catalog = const <String, dynamic>{};
      _loaded = true;
      return;
    }
  }

  Future<String> _loadText(String path) async {
    try {
      return await rootBundle.loadString(path);
    } catch (_) {
      final file = File(path);
      if (!await file.exists()) rethrow;
      return file.readAsString();
    }
  }

  List<String> allToolNames() {
    final tools = (_catalog['tools'] as List?)?.whereType<Map>() ?? const <Map>[];
    return tools
        .map((item) => (item['toolName'] as String?)?.trim() ?? '')
        .where((item) => item.isNotEmpty)
        .toList(growable: false);
  }

  List<String> availableToolsForDomain({
    required String domainId,
    required List<String> fallbackNames,
  }) {
    final matrix = (_catalog['domainToolMatrix'] as List?)?.whereType<Map>() ??
        const <Map>[];
    for (final item in matrix) {
      final id = (item['domainId'] as String?)?.trim() ?? '';
      if (id != domainId) continue;
      final allowed = (item['allowedTools'] as List?)
              ?.whereType<String>()
              .map((name) => name.trim())
              .where((name) => name.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      if (allowed.isNotEmpty) return allowed;
    }
    return fallbackNames;
  }

  List<Map<String, dynamic>> invocationGuidelinesForTools(List<String> toolNames) {
    final tools = (_catalog['tools'] as List?)?.whereType<Map>() ?? const <Map>[];
    final out = <Map<String, dynamic>>[];
    for (final name in toolNames) {
      final matched = tools.firstWhere(
        (item) => ((item['toolName'] as String?)?.trim() ?? '') == name,
        orElse: () => const <String, dynamic>{},
      );
      if (matched.isEmpty) continue;
      out.add(<String, dynamic>{
        'toolName': name,
        'purpose': (matched['purpose'] as String?)?.trim() ?? '',
        'whenToUse':
            (matched['whenToUse'] as List?)?.whereType<String>().toList(growable: false) ??
                const <String>[],
        'parameterSummary':
            (matched['parameterSummary'] as List?)
                    ?.whereType<Map>()
                    .map((item) => item.cast<String, dynamic>())
                    .toList(growable: false) ??
                const <Map<String, dynamic>>[],
        'supportedSkills':
            (matched['supportedSkills'] as List?)?.whereType<String>().toList(growable: false) ??
                const <String>[],
      });
    }
    return out;
  }

  Map<String, dynamic>? openAiFunctionSchemaByName(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return null;
    final schema = matched['openAiFunction'];
    if (schema is! Map) return null;
    return <String, dynamic>{
      'type': 'function',
      'function': schema.cast<String, dynamic>(),
    };
  }

  Map<String, dynamic>? functionParametersByToolName(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return null;
    final schema = matched['openAiFunction'];
    if (schema is! Map) return null;
    final parameters = schema['parameters'];
    if (parameters is! Map) return null;
    return parameters.cast<String, dynamic>();
  }

  List<String> requiredOutputPathsByToolName(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return const <String>[];
    return (matched['requiredOutputPaths'] as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
  }

  /// Returns the full [userInteraction] block for [toolName], or null.
  Map<String, dynamic>? userInteractionForTool(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return null;
    final ui = matched['userInteraction'];
    if (ui is! Map) return null;
    return ui.cast<String, dynamic>();
  }

  /// Returns the [reasoning.promptHint] string for [toolName], or null.
  String? promptHintForTool(String toolName) {
    final ui = userInteractionForTool(toolName);
    if (ui == null) return null;
    final reasoning = ui['reasoning'];
    if (reasoning is! Map) return null;
    return (reasoning['promptHint'] as String?)?.trim();
  }

  /// Resolves a template string containing `{{key}}` placeholders against
  /// the supplied [variables] map.  Unknown placeholders are left as-is.
  String resolveTemplate(String template, Map<String, dynamic> variables) {
    return template.replaceAllMapped(
      RegExp(r'\{\{(\w+(?:\.\w+)*)\}\}'),
      (match) {
        final key = match.group(1)!;
        final value = _resolveNestedKey(variables, key);
        return value?.toString() ?? match.group(0)!;
      },
    );
  }

  // ── private helpers ──────────────────────────────────────────────────

  dynamic _resolveNestedKey(Map<String, dynamic> map, String dotPath) {
    final segments = dotPath.split('.');
    dynamic current = map;
    for (final seg in segments) {
      if (current is Map) {
        current = current[seg];
      } else if (current is List && seg == 'length') {
        return current.length;
      } else {
        return null;
      }
    }
    return current;
  }

  Map<String, dynamic> _toolByName(String toolName) {
    final tools = (_catalog['tools'] as List?)?.whereType<Map>() ?? const <Map>[];
    final matched = tools.firstWhere(
      (item) => ((item['toolName'] as String?)?.trim() ?? '') == toolName,
      orElse: () => const <String, dynamic>{},
    );
    if (matched is Map<String, dynamic>) return matched;
    return matched.cast<String, dynamic>();
  }
}

