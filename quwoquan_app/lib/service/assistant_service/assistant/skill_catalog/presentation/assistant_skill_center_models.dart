part of 'assistant_skill_center_page.dart';

class AssistantSkillCenterItem {
  const AssistantSkillCenterItem({
    required this.catalog,
    this.setting,
    this.subscriptions = const <SkillSubscriptionWire>[],
    this.consent,
  });

  final AssistantSkillCatalogItemView catalog;
  final SkillUserSetting? setting;
  final List<SkillSubscriptionWire> subscriptions;
  final SkillConsent? consent;

  String get skillId => catalog.skillId;
  bool get hasSubscription => subscriptions.isNotEmpty;
  bool get enabled => setting?.status != SkillUserSettingStatus.disabled;
  bool get proactiveCapable {
    final mode = catalog.activationMode?.trim().toLowerCase() ?? '';
    return mode == 'proactive' || mode == 'hybrid';
  }

  bool get consentGranted {
    final required = catalog.requiredConsentScopes.toSet();
    if (required.isEmpty) {
      return true;
    }
    final current = consent;
    if (current == null ||
        current.granted != true ||
        current.revokedAt != null) {
      return false;
    }
    final granted = current.grantedScopes.toSet();
    return required.every(granted.contains);
  }

  bool isConsentScopeGranted(String scopeId) {
    final current = consent;
    return current != null &&
        current.granted == true &&
        current.revokedAt == null &&
        current.grantedScopes.contains(scopeId);
  }

  List<SkillCatalogSemanticLabel> get requiredConsentScopeLabels {
    final required = catalog.requiredConsentScopes.toSet();
    return catalog.consentScopeLabels
        .where((label) => required.contains(label.id))
        .toList(growable: false);
  }

  List<SkillCatalogSemanticLabel> get optionalConsentScopeLabels {
    final required = catalog.requiredConsentScopes.toSet();
    return catalog.consentScopeLabels
        .where((label) => !required.contains(label.id))
        .toList(growable: false);
  }
}

final assistantSkillCenterProvider =
    FutureProvider<List<AssistantSkillCenterItem>>((ref) async {
      final catalogFacet = ref.watch(assistantSkillCatalogFacetProvider);
      final settingFacet = ref.watch(assistantSkillUserSettingFacetProvider);
      final subscriptionFacet = ref.watch(
        assistantSkillSubscriptionFacetProvider,
      );
      final consentFacet = ref.watch(assistantSkillConsentFacetProvider);
      final results = await Future.wait<Object>(<Future<Object>>[
        catalogFacet.listSkillCatalog(limit: 64),
        settingFacet.listSkillUserSettings(limit: 64),
        subscriptionFacet.listSkillSubscriptions(limit: 64),
        consentFacet.listConsents(),
      ]);
      final catalog = results[0] as List<AssistantSkillCatalogItemView>;
      final settings = results[1] as List<SkillUserSetting>;
      final subscriptions = results[2] as List<SkillSubscriptionWire>;
      final consents = results[3] as List<SkillConsent>;
      final settingsBySkill = <String, SkillUserSetting>{
        for (final item in settings) item.skillId: item,
      };
      final activeSubscriptions = <String, List<SkillSubscriptionWire>>{};
      for (final item in subscriptions) {
        if (item.status == SkillSubscriptionStatus.archived) {
          continue;
        }
        activeSubscriptions
            .putIfAbsent(item.skillId, () => <SkillSubscriptionWire>[])
            .add(item);
      }
      for (final items in activeSubscriptions.values) {
        items.sort(
          (left, right) => left.subscriptionId.compareTo(right.subscriptionId),
        );
      }
      final consentsBySkill = <String, SkillConsent>{
        for (final item in consents) item.skillId: item,
      };
      return catalog
          .map(
            (item) => AssistantSkillCenterItem(
              catalog: item,
              setting: settingsBySkill[item.skillId],
              subscriptions: List<SkillSubscriptionWire>.unmodifiable(
                activeSubscriptions[item.skillId] ??
                    const <SkillSubscriptionWire>[],
              ),
              consent: consentsBySkill[item.skillId],
            ),
          )
          .toList(growable: false);
    });

class AssistantConnectorCenterState {
  const AssistantConnectorCenterState({
    required this.definitions,
    required this.connections,
    required this.invocations,
  });

  final List<ConnectorDefinition> definitions;
  final List<ConnectorConnectionView> connections;
  final List<ConnectorInvocationView> invocations;

  ConnectorConnectionView? connectionFor(String connectorId) {
    for (final connection in connections) {
      if (connection.connectorId == connectorId) {
        return connection;
      }
    }
    return null;
  }

  ConnectorInvocationView? latestInvocationFor(String connectionId) {
    for (final invocation in invocations) {
      if (invocation.connectionId == connectionId) {
        return invocation;
      }
    }
    return null;
  }
}

final assistantConnectorCenterProvider =
    FutureProvider<AssistantConnectorCenterState>((ref) async {
      final facet = ref.watch(assistantConnectorManagementFacetProvider);
      final results = await Future.wait<Object>(<Future<Object>>[
        facet.listConnectorDefinitions(),
        facet.listConnectorConnections(),
        facet.listConnectorInvocations(),
      ]);
      return AssistantConnectorCenterState(
        definitions: results[0] as List<ConnectorDefinition>,
        connections: results[1] as List<ConnectorConnectionView>,
        invocations: results[2] as List<ConnectorInvocationView>,
      );
    });

/// 最近云端会话（R-ASSIST-001 收口）：唯一数据源是
/// ListAssistantSessions 查询面，本地不再维护会话副本。
final assistantRecentSessionsProvider =
    FutureProvider.autoDispose<List<AssistantSessionWire>>((ref) async {
      final facet = ref.watch(assistantSessionRunFacetProvider);
      final page = await facet.listAssistantSessions();
      return page.items;
    });
