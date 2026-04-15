// ASSISTANT_WEAK_TYPE: VENDOR_JSON — 工具元数据 JSON 资产加载；读取后立即转为 typed catalog entity。

import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/contracts/runtime_enums.dart';
import 'package:quwoquan_app/assistant/tool/schema/tool_schema.dart';

/// Permission config for a tool, sourced from [tool_permissions.json].
class ToolPermissionConfig {
  const ToolPermissionConfig({
    required this.requireConfirmation,
    this.allowedSchemes = const <String>[],
  });

  final bool requireConfirmation;
  final List<String> allowedSchemes;
}

AssistantToolPayload? _nonEmptyPayload(Object? raw) {
  final payload = AssistantToolPayload.fromJson(raw);
  return payload.isEmptyPayload ? null : payload;
}

class _ToolCatalog {
  const _ToolCatalog({
    this.tools = const <_ToolCatalogEntry>[],
    this.domainToolMatrix = const <_ToolDomainToolMatrixEntry>[],
  });

  factory _ToolCatalog.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    final tools = payload
        .listField('tools')
        .map(_ToolCatalogEntry.fromJson)
        .where((item) => item.toolName.isNotEmpty)
        .toList(growable: false);
    final domainToolMatrix = payload
        .listField('domainToolMatrix')
        .map(_ToolDomainToolMatrixEntry.fromJson)
        .where((item) => item.domainId.isNotEmpty)
        .toList(growable: false);
    return _ToolCatalog(tools: tools, domainToolMatrix: domainToolMatrix);
  }

  final List<_ToolCatalogEntry> tools;
  final List<_ToolDomainToolMatrixEntry> domainToolMatrix;

  _ToolCatalogEntry? toolByName(String toolName) {
    final normalized = toolName.trim();
    if (normalized.isEmpty) return null;
    for (final tool in tools) {
      if (tool.toolName == normalized) return tool;
    }
    return null;
  }
}

class _ToolCatalogEntry {
  _ToolCatalogEntry({
    required this.toolName,
    required this.purpose,
    required this.whenToUse,
    required this.parameterSummary,
    required this.supportedSkills,
    required this.requiredOutputPaths,
    required this.routing,
    required this.uiContribution,
    required this.slotOutputs,
    required this.userInteraction,
    required this.openAiFunction,
  });

  factory _ToolCatalogEntry.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return _ToolCatalogEntry(
      toolName: payload.stringField('toolName') ?? '',
      purpose: payload.stringField('purpose') ?? '',
      whenToUse: payload.stringListField('whenToUse'),
      parameterSummary: payload
          .listField('parameterSummary')
          .map(AssistantToolPayload.fromJson)
          .where((item) => !item.isEmptyPayload)
          .toList(growable: false),
      supportedSkills: payload.stringListField('supportedSkills'),
      requiredOutputPaths: payload.stringListField('requiredOutputPaths'),
      routing: _ToolRouting.fromJson(payload['routing']),
      uiContribution: _ToolUiContribution.fromJson(payload['uiContribution']),
      slotOutputs: payload
          .listField('slotOutputs')
          .map(AssistantToolPayload.fromJson)
          .where((item) => !item.isEmptyPayload)
          .toList(growable: false),
      userInteraction: _nonEmptyPayload(payload['userInteraction']),
      openAiFunction: _ToolOpenAiFunction.fromJson(payload['openAiFunction']),
    );
  }

  final String toolName;
  final String purpose;
  final List<String> whenToUse;
  final List<AssistantToolPayload> parameterSummary;
  final List<String> supportedSkills;
  final List<String> requiredOutputPaths;
  final _ToolRouting routing;
  final _ToolUiContribution uiContribution;
  final List<AssistantToolPayload> slotOutputs;
  final AssistantToolPayload? userInteraction;
  final _ToolOpenAiFunction? openAiFunction;
}

class _ToolOpenAiFunction {
  const _ToolOpenAiFunction({
    required this.name,
    required this.description,
    required this.parameters,
  });

  factory _ToolOpenAiFunction.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    final name = payload.stringField('name') ?? '';
    final parameters = AssistantToolInputSchema.fromJson(payload['parameters']);
    if (name.isEmpty || parameters.isEmptyPayload) {
      return const _ToolOpenAiFunction(
        name: '',
        description: '',
        parameters: null,
      );
    }
    return _ToolOpenAiFunction(
      name: name,
      description: payload.stringField('description') ?? '',
      parameters: parameters,
    );
  }

  final String name;
  final String description;
  final AssistantToolInputSchema? parameters;
}

class _ToolRouting {
  const _ToolRouting({
    this.toolKind = '',
    this.supportsQueryTasks = false,
    this.internalOnlyParameters = const <String>[],
  });

  factory _ToolRouting.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return _ToolRouting(
      toolKind: payload.stringField('toolKind') ?? '',
      supportsQueryTasks: payload.boolField('supportsQueryTasks') ?? false,
      internalOnlyParameters: payload.stringListField('internalOnlyParameters'),
    );
  }

  final String toolKind;
  final bool supportsQueryTasks;
  final List<String> internalOnlyParameters;
}

class _ToolUiContribution {
  const _ToolUiContribution({
    this.references = false,
    this.locationContext = false,
  });

  factory _ToolUiContribution.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return _ToolUiContribution(
      references: payload.boolField('references') ?? false,
      locationContext: payload.boolField('locationContext') ?? false,
    );
  }

  final bool references;
  final bool locationContext;
}

class _ToolDomainToolMatrixEntry {
  const _ToolDomainToolMatrixEntry({
    required this.domainId,
    required this.allowedTools,
  });

  factory _ToolDomainToolMatrixEntry.fromJson(Object? raw) {
    final payload = AssistantToolPayload.fromJson(raw);
    return _ToolDomainToolMatrixEntry(
      domainId: payload.stringField('domainId') ?? '',
      allowedTools: payload.stringListField('allowedTools'),
    );
  }

  final String domainId;
  final List<String> allowedTools;
}

class ToolMetadataRegistry {
  ToolMetadataRegistry({
    this.manifestAssetPath = 'assets/assistant/tools/manifest.json',
    this.permissionsAssetPath =
        'assets/assistant/tools/catalog/tool_permissions.json',
  });

  final String manifestAssetPath;
  final String permissionsAssetPath;
  _ToolCatalog _catalog = const _ToolCatalog();
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
      _catalog = const _ToolCatalog();
      _permissions = const <String, ToolPermissionConfig>{};
      _loaded = true;
    }
  }

  Future<void> _loadCatalog() async {
    final manifestRaw = await _loadText(manifestAssetPath);
    final manifestDecoded = jsonDecode(manifestRaw);
    if (manifestDecoded is! Map) {
      _catalog = const _ToolCatalog();
      return;
    }
    final catalogPath =
        (manifestDecoded['catalogPath'] as String?)?.trim() ?? '';
    if (catalogPath.isEmpty) {
      _catalog = const _ToolCatalog();
      return;
    }
    final catalogRaw = await _loadText(catalogPath);
    final catalogDecoded = jsonDecode(catalogRaw);
    _catalog = _ToolCatalog.fromJson(catalogDecoded);
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
        final requireConfirmation = val['requireConfirmation'] == true;
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
    return _catalog.tools
        .map((item) => item.toolName)
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
  }

  List<String> availableToolsForDomain({
    required String domainId,
    required List<String> fallbackNames,
  }) {
    for (final item in _catalog.domainToolMatrix) {
      if (item.domainId != domainId) continue;
      if (item.allowedTools.isNotEmpty) return item.allowedTools;
    }
    return fallbackNames;
  }

  List<Map<String, dynamic>> invocationGuidelinesForTools(
    List<String> toolNames,
  ) {
    final out = <Map<String, dynamic>>[];
    for (final name in toolNames) {
      final matched = _catalog.toolByName(name);
      if (matched == null) continue;
      out.add(<String, dynamic>{
        'toolName': name,
        'purpose': matched.purpose,
        'whenToUse': matched.whenToUse,
        'parameterSummary': matched.parameterSummary
            .map((item) => item.toDynamicJson())
            .toList(growable: false),
        'supportedSkills': matched.supportedSkills,
      });
    }
    return out;
  }

  AssistantToolSpec? canonicalToolSpecByName(String toolName) {
    final matched = _catalog.toolByName(toolName);
    final openAiFunction = matched?.openAiFunction;
    final schemaName =
        openAiFunction?.name.trim().isNotEmpty == true
        ? openAiFunction!.name.trim()
        : toolName.trim();
    final description =
        (openAiFunction?.description.trim().isNotEmpty == true
            ? openAiFunction!.description.trim()
            : matched?.purpose ?? '');
    final parameters = openAiFunction?.parameters;
    if (schemaName.isEmpty || parameters == null || parameters.isEmptyPayload) {
      return null;
    }
    return AssistantToolSpec(
      name: schemaName,
      description: description,
      inputSchema: parameters,
    );
  }

  Map<String, dynamic>? openAiFunctionSchemaByName(String toolName) {
    return openAiToolSchemaByName(toolName);
  }

  Map<String, dynamic>? openAiToolSchemaByName(String toolName) {
    final spec = canonicalToolSpecByName(toolName);
    return spec?.toOpenAiToolWire();
  }

  Map<String, dynamic>? anthropicToolSchemaByName(String toolName) {
    final spec = canonicalToolSpecByName(toolName);
    return spec?.toAnthropicToolWire();
  }

  AssistantToolInputSchema? functionParametersByToolName(String toolName) {
    return canonicalToolSpecByName(toolName)?.inputSchema;
  }

  List<String> requiredOutputPathsByToolName(String toolName) {
    return _catalog.toolByName(toolName)?.requiredOutputPaths ??
        const <String>[];
  }

  String toolKindByName(String toolName) {
    return _catalog.toolByName(toolName)?.routing.toolKind ?? '';
  }

  bool supportsQueryTasks(String toolName) {
    return _catalog.toolByName(toolName)?.routing.supportsQueryTasks ?? false;
  }

  List<String> internalOnlyParameters(String toolName) {
    return _catalog.toolByName(toolName)?.routing.internalOnlyParameters ??
        const <String>[];
  }

  bool isRetrievalLikeTool(String toolName) {
    return toolKindByName(toolName) == 'retrieval';
  }

  bool contributesUiReferences(
    String toolName, {
    required bool allowLocationContext,
  }) {
    final contribution = _catalog.toolByName(toolName)?.uiContribution;
    if (contribution == null) return false;
    if (contribution.references) return true;
    return allowLocationContext && contribution.locationContext;
  }

  List<Map<String, dynamic>> slotOutputsByToolName(String toolName) {
    final matched = _catalog.toolByName(toolName);
    if (matched == null) return const <Map<String, dynamic>>[];
    return matched.slotOutputs
        .map((item) => item.toDynamicJson())
        .toList(growable: false);
  }

  /// Returns the full [userInteraction] block for [toolName], or null.
  Map<String, dynamic>? userInteractionForTool(String toolName) {
    return _catalog.toolByName(toolName)?.userInteraction?.toDynamicJson();
  }

  /// Returns the [reasoning.promptHint] string for [toolName], or null.
  String? promptHintForTool(String toolName) {
    final interaction = _catalog.toolByName(toolName)?.userInteraction;
    if (interaction == null) return null;
    final reasoning = interaction.payloadField('reasoning');
    return reasoning.stringField('promptHint');
  }

  JourneyStageId journeyStageIdForTool(String toolName) {
    final interaction = _catalog.toolByName(toolName)?.userInteraction;
    if (interaction == null) return JourneyStageId.unknown;
    return parseJourneyStageId(interaction.stringField('journeyStageId') ?? '');
  }

  /// Returns permission config for [toolName] from tool_permissions.json.
  /// Call after [ensureLoaded]. Returns null if not configured.
  ToolPermissionConfig? permissionForTool(String toolName) =>
      _permissions[toolName];

  /// Resolves a template string containing `{{key}}` placeholders against
  /// the supplied [variables] map. Unknown placeholders fail closed.
  String resolveTemplate(String template, Map<String, dynamic> variables) {
    return template.replaceAllMapped(RegExp(r'\{\{(\w+(?:\.\w+)*)\}\}'), (
      match,
    ) {
      final key = match.group(1)!;
      final value = _resolveNestedKey(variables, key);
      return value?.toString() ?? '';
    });
  }

  /// Returns true only when all placeholders in [template] can be resolved to
  /// non-empty values from [variables]. Numeric zero is considered resolvable.
  bool canResolveTemplate(String template, Map<String, dynamic> variables) {
    final matches = RegExp(r'\{\{(\w+(?:\.\w+)*)\}\}').allMatches(template);
    for (final match in matches) {
      final key = match.group(1);
      if (key == null || key.isEmpty) continue;
      final value = _resolveNestedKey(variables, key);
      if (value == null) return false;
      if (value is num || value is bool) continue;
      if (value is String && value.trim().isEmpty) return false;
      if (value is Iterable && value.isEmpty) return false;
    }
    return true;
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
}
