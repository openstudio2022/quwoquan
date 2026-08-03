part of 'assistant_skill_center_page.dart';

class AssistantSkillCenterItem {
  const AssistantSkillCenterItem({
    required this.catalog,
    this.setting,
    this.subscription,
    this.consent,
  });

  final AssistantSkillCatalogItemView catalog;
  final SkillUserSetting? setting;
  final SkillSubscriptionWire? subscription;
  final SkillConsent? consent;

  String get skillId => catalog.skillId;
  bool get hasSubscription => subscription != null;
  bool get enabled => setting?.status != SkillUserSettingStatus.disabled;
  bool get proactiveCapable {
    final mode = catalog.activationMode?.trim().toLowerCase() ?? '';
    return mode == 'proactive' || mode == 'hybrid';
  }

  bool get proactiveEnabled =>
      subscription?.status == SkillSubscriptionStatus.active;

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
    return current.grantedScopes.toSet().length == required.length &&
        current.grantedScopes.every(required.contains);
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
      final activeSubscriptions = <String, SkillSubscriptionWire>{
        for (final item in subscriptions)
          if (item.status != SkillSubscriptionStatus.archived)
            item.skillId: item,
      };
      final activeConsents = <String, SkillConsent>{
        for (final item in consents)
          if (item.granted == true && item.revokedAt == null)
            item.skillId: item,
      };
      return catalog
          .map(
            (item) => AssistantSkillCenterItem(
              catalog: item,
              setting: settingsBySkill[item.skillId],
              subscription: activeSubscriptions[item.skillId],
              consent: activeConsents[item.skillId],
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
