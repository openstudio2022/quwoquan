part of 'assistant_skill_center_page.dart';

class AssistantSkillCenterItem {
  const AssistantSkillCenterItem({required this.catalog, this.subscription});

  final AssistantSkillCatalogItemProjection catalog;
  final SkillSubscriptionWire? subscription;

  String get skillId => catalog.skillId;
  bool get hasSubscription => subscription != null;
  bool get enabled => subscription?.status == SkillSubscriptionStatus.active;
}

final assistantSkillCenterProvider =
    FutureProvider<List<AssistantSkillCenterItem>>((ref) async {
      final personalData = ref.watch(assistantPersonalDataFacetProvider);
      final subscriptionFacet = ref.watch(
        assistantSkillSubscriptionFacetProvider,
      );
      final catalog = await personalData.listSkillCatalog(limit: 64);
      final subscriptions = await subscriptionFacet.listSkillSubscriptions(
        limit: 64,
      );
      final activeSubscriptions = <String, SkillSubscriptionWire>{
        for (final item in subscriptions)
          if (item.status != SkillSubscriptionStatus.archived)
            item.skillId: item,
      };
      return catalog
          .map(
            (item) => AssistantSkillCenterItem(
              catalog: item,
              subscription: activeSubscriptions[item.skillId],
            ),
          )
          .toList(growable: false);
    });

/// 最近云端会话（R-ASSIST-001 收口）：唯一数据源是
/// ListAssistantConversations 查询面，本地不再维护会话副本。
final assistantRecentSessionsProvider =
    FutureProvider.autoDispose<List<AssistantConversationWire>>((ref) async {
      final facet = ref.watch(assistantConversationRunFacetProvider);
      final page = await facet.listAssistantConversations();
      return page.items;
    });
