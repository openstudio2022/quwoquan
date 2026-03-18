import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';

/// Permission config for a tool, sourced from [tool_permissions.json].
class ToolPermissionConfig {
  const ToolPermissionConfig({
    required this.requireConfirmation,
    this.allowedSchemes = const <String>[],
  });

  final bool requireConfirmation;
  final List<String> allowedSchemes;
}

class ToolMetadataRegistry {
  ToolMetadataRegistry({
    this.manifestAssetPath = 'assets/assistant/tools/manifest.json',
    this.permissionsAssetPath =
        'assets/assistant/tools/catalog/tool_permissions.json',
  });

  final String manifestAssetPath;
  final String permissionsAssetPath;
  Map<String, dynamic> _catalog = const <String, dynamic>{};
  Map<String, ToolPermissionConfig> _permissions =
      const <String, ToolPermissionConfig>{};
  Future<void>? _loadingFuture;
  bool _loaded = false;

  Future<void> ensureLoaded() async {
    if (_loaded) return;
    _loadingFuture ??= _load();
    await _loadingFuture;
  }

  Future<void> _load() async {
    try {
      await _loadCatalog();
      await _loadPermissions();
      _loaded = true;
    } catch (_) {
      _catalog = const <String, dynamic>{};
      _permissions = const <String, ToolPermissionConfig>{};
      _loaded = true;
    }
  }

  Future<void> _loadCatalog() async {
    final manifestRaw = await _loadText(manifestAssetPath);
    final manifestDecoded = jsonDecode(manifestRaw);
    if (manifestDecoded is! Map) {
      _catalog = const <String, dynamic>{};
      return;
    }
    final catalogPath =
        (manifestDecoded['catalogPath'] as String?)?.trim() ?? '';
    if (catalogPath.isEmpty) {
      _catalog = const <String, dynamic>{};
      return;
    }
    final catalogRaw = await _loadText(catalogPath);
    final catalogDecoded = jsonDecode(catalogRaw);
    if (catalogDecoded is! Map) {
      _catalog = const <String, dynamic>{};
      return;
    }
    _catalog = catalogDecoded.cast<String, dynamic>();
  }

  Future<void> _loadPermissions() async {
    try {
      final raw = await _loadText(permissionsAssetPath);
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      final perms = decoded['permissions'];
      if (perms is! Map) return;
      final out = <String, ToolPermissionConfig>{};
      for (final entry in perms.entries) {
        final name = (entry.key as String).trim();
        if (name.isEmpty) continue;
        final val = entry.value;
        if (val is! Map) continue;
        final requireConfirmation =
            val['requireConfirmation'] == true;
        final allowedRaw = val['allowedActions'] ?? val['allowedSchemes'];
        final allowed = allowedRaw is List
            ? allowedRaw
                .whereType<String>()
                .map((s) => s.trim())
                .where((s) => s.isNotEmpty)
                .toList(growable: false)
            : const <String>[];
        out[name] = ToolPermissionConfig(
          requireConfirmation: requireConfirmation,
          allowedSchemes: allowed,
        );
      }
      _permissions = out;
    } catch (_) {
      _permissions = const <String, ToolPermissionConfig>{};
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
    return _requiredStringList(matched['requiredOutputPaths']);
  }

  String toolKindByName(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return '';
    final routing =
        (matched['routing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return (routing['toolKind'] as String?)?.trim() ?? '';
  }

  bool supportsQueryTasks(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return false;
    final routing =
        (matched['routing'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    return routing['supportsQueryTasks'] == true;
  }

  bool isRetrievalLikeTool(String toolName) {
    return toolKindByName(toolName) == 'retrieval';
  }

  bool contributesUiReferences(
    String toolName, {
    required bool allowLocationContext,
  }) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return false;
    final uiContribution =
        (matched['uiContribution'] as Map?)?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (uiContribution['references'] == true) return true;
    return allowLocationContext && uiContribution['locationContext'] == true;
  }

  List<Map<String, dynamic>> slotOutputsByToolName(String toolName) {
    final matched = _toolByName(toolName);
    if (matched.isEmpty) return const <Map<String, dynamic>>[];
    return (matched['slotOutputs'] as List?)
            ?.whereType<Map>()
            .map((item) => item.cast<String, dynamic>())
            .toList(growable: false) ??
        const <Map<String, dynamic>>[];
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

  JourneyStageId journeyStageIdForTool(String toolName) {
    final ui = userInteractionForTool(toolName);
    if (ui == null) return JourneyStageId.unknown;
    return parseJourneyStageId((ui['journeyStageId'] as String?)?.trim() ?? '');
  }

  /// Returns permission config for [toolName] from tool_permissions.json.
  /// Call after [ensureLoaded]. Returns null if not configured.
  ToolPermissionConfig? permissionForTool(String toolName) =>
      _permissions[toolName];

  /// Resolves a template string containing `{{key}}` placeholders against
  /// the supplied [variables] map. Unknown placeholders fail closed.
  String resolveTemplate(String template, Map<String, dynamic> variables) {
    return template.replaceAllMapped(
      RegExp(r'\{\{(\w+(?:\.\w+)*)\}\}'),
      (match) {
        final key = match.group(1)!;
        final value = _resolveNestedKey(variables, key);
        return value?.toString() ?? '';
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

  List<String> _requiredStringList(Object? raw) {
    return (raw as List?)
            ?.whereType<String>()
            .map((item) => item.trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
  }

}

