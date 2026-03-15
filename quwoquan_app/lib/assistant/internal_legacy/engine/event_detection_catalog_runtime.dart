import 'dart:convert';
import 'dart:io';

import 'package:flutter/services.dart' show rootBundle;
import 'package:quwoquan_app/assistant/internal_legacy/engine/domain_config_governance.dart';

class EventDetectionRule {
  const EventDetectionRule({
    required this.event,
    required this.priority,
    required this.keywords,
    required this.stateBeforeIn,
  });

  final String event;
  final int priority;
  final List<String> keywords;
  final List<String> stateBeforeIn;
}

class EventDetectionCatalog {
  const EventDetectionCatalog({
    required this.catalogId,
    required this.version,
    required this.defaultEvent,
    required this.emptyTextEvent,
    required this.globalRules,
    required this.domainRules,
  });

  final String catalogId;
  final String version;
  final String defaultEvent;
  final String emptyTextEvent;
  final List<EventDetectionRule> globalRules;
  final Map<String, List<EventDetectionRule>> domainRules;

  static EventDetectionCatalog empty() {
    return const EventDetectionCatalog(
      catalogId: '',
      version: '',
      defaultEvent: 'E_USER_QUERY_RECEIVED',
      emptyTextEvent: 'E_USER_REQUEST_EXPLAIN',
      globalRules: <EventDetectionRule>[],
      domainRules: <String, List<EventDetectionRule>>{},
    );
  }
}

class EventDetectionCatalogRuntime {
  EventDetectionCatalogRuntime({
    this.assetPath =
        'assets/assistant/prompts/domain_routing/event_detection_catalog.json',
    DomainConfigGovernance? governance,
  }) : _governance = governance ?? const DomainConfigGovernance();

  final String assetPath;
  final DomainConfigGovernance _governance;
  EventDetectionCatalog _catalog = EventDetectionCatalog.empty();
  final Map<String, EventDetectionCatalog> _catalogsByVersion =
      <String, EventDetectionCatalog>{};
  bool _loaded = false;
  Future<void>? _loadingFuture;

  Future<void> ensureLoaded({bool forceRefresh = false}) async {
    if (forceRefresh) {
      _loaded = false;
      _loadingFuture = null;
      _catalog = EventDetectionCatalog.empty();
      _catalogsByVersion.clear();
    }
    if (_loaded) return;
    _loadingFuture ??= _load();
    await _loadingFuture;
    _loaded = true;
  }

  EventDetectionCatalog resolveCatalogForRequest(
    Map<String, dynamic> contextScopeHint,
  ) {
    final envelope =
        (contextScopeHint['eventDetectionRemoteEnvelope'] as Map?)
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
        (contextScopeHint['eventDetectionRollback'] as Map?)
            ?.cast<String, dynamic>() ??
        const <String, dynamic>{};
    if (rollback['enabled'] == true) {
      final targetVersion =
          (rollback['targetVersion'] as String?)?.trim() ?? '';
      final rollbackCatalog = _catalogsByVersion[targetVersion];
      if (rollbackCatalog != null) return rollbackCatalog;
    }
    if (parsedRemote != null) return parsedRemote;
    return _catalog;
  }

  Future<void> _load() async {
    try {
      final raw = await _loadText(assetPath);
      final decoded = jsonDecode(raw);
      if (decoded is! Map) return;
      final parsed = _parseCatalogMap(decoded.cast<String, dynamic>());
      if (parsed == null) return;
      _catalog = parsed;
      if (parsed.version.trim().isNotEmpty) {
        _catalogsByVersion[parsed.version.trim()] = parsed;
      }
    } catch (_) {
      return;
    }
  }

  Future<String> _loadText(String path) async {
    try {
      return await rootBundle.loadString(path);
    } catch (_) {
      final file = File(path);
      if (await file.exists()) {
        return await file.readAsString();
      }
      rethrow;
    }
  }

  EventDetectionCatalog? _parseRemoteCatalog({
    required Map<String, dynamic> envelope,
    required Map<String, dynamic> contextScopeHint,
  }) {
    if (envelope.isEmpty) return null;
    final verified = _governance.verifyEnvelopeSignature(envelope);
    final allowUnsigned =
        envelope['allowUnsignedDebug'] == true &&
        contextScopeHint['allowUnsignedDomainConfig'] == true;
    if (!verified && !allowUnsigned) return null;
    if (!_governance.allowByGrayRelease(
      envelope: envelope,
      contextScopeHint: contextScopeHint,
    )) {
      return null;
    }
    final catalogRaw = envelope['catalog'];
    if (catalogRaw is! Map) return null;
    return _parseCatalogMap(catalogRaw.cast<String, dynamic>());
  }

  EventDetectionCatalog? _parseCatalogMap(Map<String, dynamic> map) {
    final globalRules = _parseRules(
      (map['globalRules'] as List?)?.whereType<Map>().toList() ?? const <Map>[],
    );
    final domainRules = <String, List<EventDetectionRule>>{};
    final domainRaw = map['domainRules'];
    if (domainRaw is Map) {
      for (final entry in domainRaw.entries) {
        final domainId = entry.key.toString().trim();
        if (domainId.isEmpty || entry.value is! List) continue;
        final rules = _parseRules(
          (entry.value as List).whereType<Map>().toList(growable: false),
        );
        domainRules[domainId] = rules;
      }
    }
    final version = (map['version'] as String?)?.trim() ?? '';
    if (version.isEmpty) return null;
    return EventDetectionCatalog(
      catalogId: (map['catalogId'] as String?)?.trim() ?? '',
      version: version,
      defaultEvent: (map['defaultEvent'] as String?)?.trim().isNotEmpty == true
          ? (map['defaultEvent'] as String).trim()
          : 'E_USER_QUERY_RECEIVED',
      emptyTextEvent:
          (map['emptyTextEvent'] as String?)?.trim().isNotEmpty == true
          ? (map['emptyTextEvent'] as String).trim()
          : 'E_USER_REQUEST_EXPLAIN',
      globalRules: globalRules,
      domainRules: domainRules,
    );
  }

  List<EventDetectionRule> _parseRules(List<Map> rulesRaw) {
    final rules = <EventDetectionRule>[];
    for (final item in rulesRaw) {
      final event = (item['event'] as String?)?.trim() ?? '';
      if (event.isEmpty) continue;
      final keywords =
          (item['keywords'] as List?)
              ?.whereType<String>()
              .map((token) => token.trim())
              .where((token) => token.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      final stateBeforeIn =
          (item['stateBeforeIn'] as List?)
              ?.whereType<String>()
              .map((state) => state.trim())
              .where((state) => state.isNotEmpty)
              .toList(growable: false) ??
          const <String>[];
      rules.add(
        EventDetectionRule(
          event: event,
          priority: (item['priority'] as num?)?.toInt() ?? 0,
          keywords: keywords,
          stateBeforeIn: stateBeforeIn,
        ),
      );
    }
    rules.sort((a, b) => b.priority.compareTo(a.priority));
    return rules;
  }
}
