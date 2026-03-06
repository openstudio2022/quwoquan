import 'package:quwoquan_app/personal_assistant/engine/domain_routing_catalog_runtime.dart';
import 'package:quwoquan_app/personal_assistant/template_runtime/template_catalog_runtime.dart';

class AssistantDomainRouter {
  AssistantDomainRouter({
    TemplateCatalogRuntime? catalogRuntime,
    DomainRoutingCatalogRuntime? routingCatalogRuntime,
  }) : _catalogRuntime = catalogRuntime ?? TemplateCatalogRuntime(),
       _routingCatalogRuntime =
           routingCatalogRuntime ?? DomainRoutingCatalogRuntime();

  final TemplateCatalogRuntime _catalogRuntime;
  final DomainRoutingCatalogRuntime _routingCatalogRuntime;

  Future<void> ensureLoaded({bool forceRefresh = false}) async {
    await _catalogRuntime.ensureLoaded(forceRefresh: forceRefresh);
    await _routingCatalogRuntime.ensureLoaded(forceRefresh: forceRefresh);
  }

  Future<String> catalogVersion({
    bool forceRefresh = false,
    Map<String, dynamic> contextScopeHint = const <String, dynamic>{},
  }) async {
    await ensureLoaded(forceRefresh: forceRefresh);
    return _routingCatalogRuntime
        .resolveCatalogForRequest(contextScopeHint)
        .version;
  }

  Future<List<String>> availableDomains({
    bool forceRefresh = false,
    Map<String, dynamic> contextScopeHint = const <String, dynamic>{},
  }) async {
    await ensureLoaded(forceRefresh: forceRefresh);
    final selectedCatalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    final domains = selectedCatalog.rules
        .where((rule) => rule.enabled)
        .map((rule) => rule.domainId)
        .toSet()
        .toList(growable: false)
      ..sort();
    if (domains.isNotEmpty) return domains;
    return const <String>['fallback_general_search'];
  }

  Future<String> classify({
    required String query,
    required Map<String, dynamic> contextScopeHint,
    bool forceRefresh = false,
  }) async {
    final domains = await availableDomains(
      forceRefresh: forceRefresh,
      contextScopeHint: contextScopeHint,
    );
    final routingCatalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    String matchOrFallback(String domainId) {
      if (domains.contains(domainId)) return domainId;
      final fallbackId = routingCatalog.fallbackDomainId.trim();
      return domains.contains(fallbackId)
          ? fallbackId
          : domains.contains('fallback_general_search')
          ? 'fallback_general_search'
          : domains.first;
    }

    final lowered = query.toLowerCase();
    for (final rule in routingCatalog.rules) {
      if (!rule.enabled || !domains.contains(rule.domainId)) continue;
      if (_containsAny(lowered, rule.intentKeywords)) {
        return matchOrFallback(rule.domainId);
      }
    }

    final pageType = (contextScopeHint['pageType'] as String?)?.trim() ?? '';
    if (pageType.isNotEmpty) {
      final mapped = routingCatalog.pageTypeFallbacks[pageType];
      if (mapped != null && mapped.trim().isNotEmpty) {
        return matchOrFallback(mapped.trim());
      }
    }
    return matchOrFallback(routingCatalog.fallbackDomainId);
  }

  bool _containsAny(String source, List<String> keywords) {
    for (final keyword in keywords) {
      if (source.contains(keyword)) return true;
    }
    return false;
  }

  /// Classifies a query and returns a ranked list of matching domain IDs.
  /// The first entry is the primary domain; subsequent entries are secondary
  /// domains that partially match. At most [maxSecondary]+1 total domains.
  Future<List<String>> classifyMulti({
    required String query,
    required Map<String, dynamic> contextScopeHint,
    bool forceRefresh = false,
    int maxSecondary = 2,
  }) async {
    final domains = await availableDomains(
      forceRefresh: forceRefresh,
      contextScopeHint: contextScopeHint,
    );
    final routingCatalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    String matchOrFallback(String domainId) {
      if (domains.contains(domainId)) return domainId;
      final fallbackId = routingCatalog.fallbackDomainId.trim();
      return domains.contains(fallbackId)
          ? fallbackId
          : domains.contains('fallback_general_search')
          ? 'fallback_general_search'
          : domains.first;
    }

    final lowered = query.toLowerCase();
    final matched = <String>[];
    for (final rule in routingCatalog.rules) {
      if (!rule.enabled || !domains.contains(rule.domainId)) continue;
      if (_containsAny(lowered, rule.intentKeywords)) {
        final id = matchOrFallback(rule.domainId);
        if (!matched.contains(id)) {
          matched.add(id);
        }
        if (matched.length >= maxSecondary + 1) break;
      }
    }
    if (matched.isNotEmpty) return matched;
    // Fallback to single-domain classification
    final pageType = (contextScopeHint['pageType'] as String?)?.trim() ?? '';
    if (pageType.isNotEmpty) {
      final mapped = routingCatalog.pageTypeFallbacks[pageType];
      if (mapped != null && mapped.trim().isNotEmpty) {
        return <String>[matchOrFallback(mapped.trim())];
      }
    }
    return <String>[matchOrFallback(routingCatalog.fallbackDomainId)];
  }
}
