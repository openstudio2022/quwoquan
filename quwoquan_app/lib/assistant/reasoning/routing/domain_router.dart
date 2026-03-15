import 'package:quwoquan_app/assistant/reasoning/routing/domain_routing_catalog_runtime.dart';
import 'package:quwoquan_app/assistant/skill/domain/skill_manifest.dart';
import 'package:quwoquan_app/assistant/template_runtime/assistant_template_runtime.dart';

/// Provides domain catalog data for the assistant.
///
/// In the new LLM-first architecture, this class no longer performs
/// keyword-based classification. The LLM autonomously selects the
/// appropriate skill via the injected skill catalog prompt. This class
/// only loads configuration and supplies catalog metadata.
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
    final domains =
        selectedCatalog.rules
            .where((rule) => rule.enabled)
            .map((rule) => rule.domainId)
            .toSet()
            .toList(growable: false)
          ..sort();
    if (domains.isNotEmpty) return domains;
    return const <String>['fallback_general_search'];
  }

  /// Returns [fallbackDomainId]. Keyword-based classification has been
  /// removed; the LLM selects the domain via the planner prompt.
  Future<String> classify({
    required String query,
    required Map<String, dynamic> contextScopeHint,
    bool forceRefresh = false,
  }) async {
    await ensureLoaded(forceRefresh: forceRefresh);
    final catalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    return catalog.fallbackDomainId;
  }

  /// Builds a compact skill catalog prompt for LLM-based skill selection.
  /// Each enabled domain is listed with its description and mode.
  Future<String> buildSkillCatalogPrompt({
    Map<String, dynamic> contextScopeHint = const <String, dynamic>{},
  }) async {
    await ensureLoaded();
    final catalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    final buffer = StringBuffer();
    for (final rule in catalog.rules) {
      if (!rule.enabled || rule.description.isEmpty) continue;
      buffer.writeln(
        '- ${rule.domainId}: ${rule.description} [mode=${rule.mode}]',
      );
    }
    return buffer.toString().trimRight();
  }

  /// Returns the domain configuration for a given [domainId], or null.
  Future<DomainRoutingRule?> getDomainConfig(String domainId) async {
    await ensureLoaded();
    final catalog = _routingCatalogRuntime.resolveCatalogForRequest(
      const <String, dynamic>{},
    );
    for (final rule in catalog.rules) {
      if (rule.domainId == domainId) return rule;
    }
    return null;
  }

  /// Returns lightweight [PersonalAssistantSkillManifest] objects built from
  /// the routing catalog rules, suitable for the recall layer.
  Future<List<PersonalAssistantSkillManifest>> availableSkillManifests({
    Map<String, dynamic> contextScopeHint = const <String, dynamic>{},
  }) async {
    await ensureLoaded();
    final catalog = _routingCatalogRuntime.resolveCatalogForRequest(
      contextScopeHint,
    );
    return catalog.rules
        .where((rule) => rule.enabled)
        .map(
          (rule) => PersonalAssistantSkillManifest.fromMap(<String, dynamic>{
            'id': rule.domainId,
            'name': rule.domainId,
            'description': rule.description,
            'version': '1.0.0',
            'executionTarget': 'tool_chain',
            'parametersSchema': const <String, dynamic>{},
            'domainId': rule.domainId,
            'frontmatter': <String, dynamic>{'mode': rule.mode},
          }),
        )
        .toList(growable: false);
  }

  String get fallbackDomainId {
    final catalog = _routingCatalogRuntime.resolveCatalogForRequest(
      const <String, dynamic>{},
    );
    return catalog.fallbackDomainId;
  }
}
