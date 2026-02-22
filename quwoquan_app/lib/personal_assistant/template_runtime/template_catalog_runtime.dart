import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;

class TemplateCatalogRuntime {
  TemplateCatalogRuntime({
    this.manifestAssetPath = 'assets/personal_assistant/prompts/manifest.json',
  });

  final String manifestAssetPath;
  final Map<String, String> _latestVersionByTemplateId = <String, String>{};
  final Set<String> _domainIds = <String>{};
  bool _loaded = false;
  Future<void>? _loadingFuture;

  Future<void> ensureLoaded({bool forceRefresh = false}) async {
    if (forceRefresh) {
      _loaded = false;
      _loadingFuture = null;
      _latestVersionByTemplateId.clear();
      _domainIds.clear();
    }
    if (_loaded) return;
    _loadingFuture ??= _load();
    await _loadingFuture;
    _loaded = true;
  }

  Future<void> _load() async {
    try {
      final manifestRaw = await rootBundle.loadString(manifestAssetPath);
      final decoded = jsonDecode(manifestRaw);
      if (decoded is! Map) return;
      final templatesRaw = decoded['templates'];
      if (templatesRaw is! List) return;
      for (final item in templatesRaw) {
        if (item is! Map) continue;
        final metaPath = (item['metaPath'] as String?)?.trim() ?? '';
        if (metaPath.isEmpty) continue;
        try {
          final metaRaw = await rootBundle.loadString(metaPath);
          final metaDecoded = jsonDecode(metaRaw);
          if (metaDecoded is! Map) continue;
          final meta = metaDecoded.cast<String, dynamic>();
          final templateId = (meta['templateId'] as String?)?.trim() ?? '';
          final version = (meta['version'] as String?)?.trim() ?? '';
          if (templateId.isEmpty || version.isEmpty) continue;
          final old = _latestVersionByTemplateId[templateId];
          if (old == null || _compareVersion(version, old) > 0) {
            _latestVersionByTemplateId[templateId] = version;
          }
          final domainId = (meta['domainId'] as String?)?.trim() ?? '';
          if (domainId.isNotEmpty && domainId != 'global') {
            _domainIds.add(domainId);
          }
        } catch (_) {
          continue;
        }
      }
    } catch (_) {
      return;
    }
  }

  String latestVersionFor(String templateId, {String fallback = ''}) {
    final value = _latestVersionByTemplateId[templateId];
    if (value != null && value.isNotEmpty) return value;
    return fallback;
  }

  List<String> availableDomains() {
    return _domainIds.toList(growable: false)..sort();
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
