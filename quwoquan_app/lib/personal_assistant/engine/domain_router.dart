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
    final fromTemplate = _catalogRuntime.availableDomains().toSet();
    final selectedCatalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    final fromRouting = selectedCatalog.rules
        .where((rule) => rule.enabled)
        .map((rule) => rule.domainId)
        .toSet();
    final domains = fromRouting
        .where((domainId) => fromTemplate.contains(domainId))
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
}
