import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/prompt_template.dart';
import 'package:quwoquan_app/assistant/internal_legacy/template_runtime/template_validator.dart';

class TemplateRegistry {
  TemplateRegistry({
    this.manifestAssetPath =
        'assets/assistant/prompts/manifest.json',
  }) : _templates = <String, PromptTemplate>{};

  final String manifestAssetPath;
  final Map<String, PromptTemplate> _templates;
  final TemplateValidator _validator = const TemplateValidator();
  bool _loaded = false;
  Future<void>? _loadingFuture;
  TemplateRegistry._internal(this.manifestAssetPath, this._templates);

  factory TemplateRegistry.withSeeded({
    required Map<String, PromptTemplate> seededTemplates,
    String manifestAssetPath = 'assets/assistant/prompts/manifest.json',
  }) {
    final registry = TemplateRegistry._internal(manifestAssetPath, seededTemplates);
    registry._loaded = true;
    return registry;
  }

  Future<void> ensureLoaded() async {
    if (_loaded) return;
    _loadingFuture ??= _loadFromManifest(manifestAssetPath).then((_) {
      _loaded = true;
    });
    await _loadingFuture;
  }

  Future<void> _loadFromManifest(String manifestPath) async {
    try {
      final manifestRaw = await rootBundle.loadString(manifestPath);
      final decoded = jsonDecode(manifestRaw);
      if (decoded is! Map) return;
      final templatesRaw = decoded['templates'];
      if (templatesRaw is! List) return;
      for (final item in templatesRaw) {
        if (item is! Map) continue;
        final metaPath = (item['metaPath'] as String?)?.trim() ?? '';
        final contentPath = (item['contentPath'] as String?)?.trim() ?? '';
        if (metaPath.isEmpty || contentPath.isEmpty) continue;
        try {
          final metaRaw = await rootBundle.loadString(metaPath);
          final contentRaw = await rootBundle.loadString(contentPath);
          final metaDecoded = jsonDecode(metaRaw);
          if (metaDecoded is! Map) continue;
          final meta = metaDecoded.cast<String, dynamic>();
          final template = PromptTemplate(
            templateId: (meta['templateId'] as String?)?.trim() ?? '',
            templateVersion: (meta['version'] as String?)?.trim() ?? '',
            content: contentRaw,
            requiredVariables: (meta['requiredVariables'] as List?)
                    ?.whereType<String>()
                    .map((item) => item.trim())
                    .where((item) => item.isNotEmpty)
                    .toList(growable: false) ??
                const <String>[],
            metadata: meta,
          );
          if (template.templateId.isEmpty) continue;
          final validation = _validator.validate(
            templateId: template.templateId,
            content: template.content,
          );
          if (!validation.isValid) continue;
          _templates[template.key()] = template;
        } catch (_) {
          // Ignore broken template file and continue loading others.
          continue;
        }
      }
    } catch (_) {
      // Keep registry empty on manifest load failure.
      return;
    }
  }

  PromptTemplate? getTemplate(String templateId, String templateVersion) {
    return _templates['$templateId@$templateVersion'];
  }

  PromptTemplate? getLatestById(String templateId) {
    PromptTemplate? latest;
    for (final template in _templates.values) {
      if (template.templateId != templateId) continue;
      latest ??= template;
      if (_compareVersion(template.templateVersion, latest.templateVersion) >
          0) {
        latest = template;
      }
    }
    return latest;
  }

  static int _compareVersion(String left, String right) {
    final lp = _normalizeVersion(left);
    final rp = _normalizeVersion(right);
    if (lp == rp) return 0;
    return lp > rp ? 1 : -1;
  }

  static int _normalizeVersion(String raw) {
    final cleaned = raw.trim().toLowerCase().replaceAll(RegExp(r'[^0-9]'), '');
    return int.tryParse(cleaned) ?? 0;
  }
}

class TemplateSelector {
  const TemplateSelector();

  TemplateSelection select({
    required String templateId,
    required String defaultVersion,
    required Map<String, dynamic> context,
  }) {
    final fallback = TemplateSelection(
      templateId: templateId,
      templateVersion: defaultVersion,
      bucket: 'control',
      rollbackEnabled: false,
    );
    final experiments = context['templateExperiments'];
    if (experiments is! Map) return fallback;
    final perTemplate = experiments[templateId];
    if (perTemplate is! Map) return fallback;
    final enabled = perTemplate['enabled'] == true;
    if (!enabled) return fallback;
    final rollback = perTemplate['rollbackEnabled'] == true;
    if (rollback) return fallback.copyWith(rollbackEnabled: true);
    final targetVersion =
        (perTemplate['targetVersion'] as String?)?.trim() ?? '';
    final bucket = (perTemplate['bucket'] as String?)?.trim() ?? 'experiment';
    if (targetVersion.isEmpty) return fallback;
    return TemplateSelection(
      templateId: templateId,
      templateVersion: targetVersion,
      bucket: bucket,
      rollbackEnabled: false,
    );
  }
}

class TemplateSelection {
  const TemplateSelection({
    required this.templateId,
    required this.templateVersion,
    required this.bucket,
    required this.rollbackEnabled,
  });

  final String templateId;
  final String templateVersion;
  final String bucket;
  final bool rollbackEnabled;

  TemplateSelection copyWith({
    String? templateId,
    String? templateVersion,
    String? bucket,
    bool? rollbackEnabled,
  }) {
    return TemplateSelection(
      templateId: templateId ?? this.templateId,
      templateVersion: templateVersion ?? this.templateVersion,
      bucket: bucket ?? this.bucket,
      rollbackEnabled: rollbackEnabled ?? this.rollbackEnabled,
    );
  }
}
