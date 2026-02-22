import 'dart:convert';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/personal_assistant/engine/domain_config_governance.dart';

class DomainRoutingRule {
  const DomainRoutingRule({
    required this.domainId,
    required this.enabled,
    required this.priority,
    required this.intentKeywords,
    required this.dialoguePath,
  });

  final String domainId;
  final bool enabled;
  final int priority;
  final List<String> intentKeywords;
  final String dialoguePath;
}

class DomainRoutingCatalog {
  const DomainRoutingCatalog({
    required this.catalogId,
    required this.version,
    required this.fallbackDomainId,
    required this.pageTypeFallbacks,
    required this.rules,
  });

  final String catalogId;
  final String version;
  final String fallbackDomainId;
  final Map<String, String> pageTypeFallbacks;
  final List<DomainRoutingRule> rules;

  static DomainRoutingCatalog empty() {
    return const DomainRoutingCatalog(
      catalogId: '',
      version: '',
      fallbackDomainId: 'fallback_general_search',
      pageTypeFallbacks: <String, String>{},
      rules: <DomainRoutingRule>[],
    );
  }
}

class DomainRoutingCatalogRuntime {
  DomainRoutingCatalogRuntime({
    this.assetPath =
        'assets/personal_assistant/prompts/domain_routing/domain_routing_catalog.json',
    DomainConfigGovernance? governance,
  }) : _governance = governance ?? const DomainConfigGovernance();

  final DomainConfigGovernance _governance;

  final String assetPath;
  DomainRoutingCatalog _catalog = DomainRoutingCatalog.empty();
  final Map<String, DomainRoutingCatalog> _catalogsByVersion =
      <String, DomainRoutingCatalog>{};
  bool _loaded = false;
  Future<void>? _loadingFuture;

  Future<void> ensureLoaded({bool forceRefresh = false}) async {
    if (forceRefresh) {
      _loaded = false;
      _loadingFuture = null;
      _catalog = DomainRoutingCatalog.empty();
      _catalogsByVersion.clear();
    }
    if (_loaded) return;
    _loadingFuture ??= _load();
    await _loadingFuture;
    _loaded = true;
  }

  DomainRoutingCatalog get catalog => _catalog;

  String catalogVersion() => _catalog.version;

  List<String> domainIds() {
    return _catalog.rules
        .where((rule) => rule.enabled && rule.domainId.isNotEmpty)
        .map((rule) => rule.domainId)
        .toSet()
        .toList(growable: false);
  }

  String dialoguePathFor(String domainId) {
    for (final rule in _catalog.rules) {
      if (rule.domainId != domainId) continue;
      if (rule.dialoguePath.trim().isNotEmpty) return rule.dialoguePath.trim();
    }
    return 'assets/personal_assistant/prompts/domains/$domainId/dialogue';
  }

  Future<void> _load() async {
    try {
      final raw = await rootBundle.loadString(assetPath);
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      final parsedCatalog = _parseCatalogMap(decoded.cast<String, dynamic>());
      if (parsedCatalog == null) return;
      _catalog = parsedCatalog;
      if (parsedCatalog.version.trim().isNotEmpty) {
        _catalogsByVersion[parsedCatalog.version.trim()] = parsedCatalog;
      }
    } catch (_) {
      return;
    }
  }

  DomainRoutingCatalog resolveCatalogForRequest(
    Map<String, dynamic> contextScopeHint,
  ) {
    final envelope =
        (contextScopeHint['domainRoutingRemoteEnvelope'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    final parsedRemote = _parseRemoteCatalog(
      envelope: envelope,
      contextScopeHint: contextScopeHint,
    );
    if (parsedRemote != null) {
      _catalogsByVersion[parsedRemote.version] = parsedRemote;
    }
    final rollback =
        (contextScopeHint['domainRoutingRollback'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (rollback['enabled'] == true) {
      final targetVersion = (rollback['targetVersion'] as String?)?.trim() ?? '';
      final rollbackCatalog = _catalogsByVersion[targetVersion];
      if (rollbackCatalog != null) return rollbackCatalog;
    }
    if (parsedRemote != null) return parsedRemote;
    return _catalog;
  }

  DomainRoutingCatalog? _parseRemoteCatalog({
    required Map<String, dynamic> envelope,
    required Map<String, dynamic> contextScopeHint,
  }) {
    if (envelope.isEmpty) return null;
    final verified = _governance.verifyEnvelopeSignature(envelope);
    final allowUnsigned = envelope['allowUnsignedDebug'] == true &&
        contextScopeHint['allowUnsignedDomainConfig'] == true;
    if (!verified && !allowUnsigned) return null;
    final catalogRaw = envelope['catalog'];
    if (catalogRaw is! Map) return null;
    final parsed =
        _parseCatalogMap(catalogRaw.cast<String, dynamic>(), allowEmptyId: false);
    if (parsed == null) return null;
    if (!_governance.allowByGrayRelease(
      envelope: envelope,
      contextScopeHint: contextScopeHint,
    )) {
      return null;
    }
    return parsed;
  }

  DomainRoutingCatalog? _parseCatalogMap(
    Map<String, dynamic> map, {
    bool allowEmptyId = true,
  }) {
    final rulesRaw = (map['domains'] as List?)?.whereType<Map>().toList() ??
        const <Map>[];
    final rules = <DomainRoutingRule>[];
    for (final item in rulesRaw) {
      final domainId = (item['domainId'] as String?)?.trim() ?? '';
      if (domainId.isEmpty) continue;
      final keywords = (item['intentKeywords'] as List?)
              ?.whereType<String>()
              .map((token) => token.trim())
              .where((token) => token.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      rules.add(
        DomainRoutingRule(
          domainId: domainId,
          enabled: item['enabled'] != false,
          priority: (item['priority'] as num?)?.toInt() ?? 0,
          intentKeywords: keywords,
          dialoguePath: (item['dialoguePath'] as String?)?.trim() ?? '',
        ),
      );
    }
    rules.sort((a, b) => b.priority.compareTo(a.priority));

    final fallbacks = <String, String>{};
    final fallbackRaw = map['pageTypeFallbacks'];
    if (fallbackRaw is Map) {
      for (final entry in fallbackRaw.entries) {
        final key = entry.key.toString().trim();
        final value = entry.value.toString().trim();
        if (key.isEmpty || value.isEmpty) continue;
        fallbacks[key] = value;
      }
    }
    final catalogId = (map['catalogId'] as String?)?.trim() ?? '';
    if (!allowEmptyId && catalogId.isEmpty) return null;
    final version = (map['version'] as String?)?.trim() ?? '';
    if (version.isEmpty) return null;
    return DomainRoutingCatalog(
      catalogId: catalogId,
      version: version,
      fallbackDomainId: (map['fallbackDomainId'] as String?)?.trim().isNotEmpty ==
              true
          ? (map['fallbackDomainId'] as String).trim()
          : 'fallback_general_search',
      pageTypeFallbacks: fallbacks,
      rules: rules,
    );
  }
}
