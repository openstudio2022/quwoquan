part of 'assistant_skill_center_page.dart';

class AssistantSkillCenterItem {
  const AssistantSkillCenterItem({required this.catalog, this.subscription});

  final AssistantSkillCatalogItemView catalog;
  final SkillSubscriptionWire? subscription;

  String get skillId => catalog.skillId;
  bool get enabled => subscription != null && subscription!.status == 'active';
  bool get paused => subscription != null && subscription!.status == 'paused';
  String get statusLabel {
    final status = subscription?.status ?? '';
    if (status == 'active') return '已订阅';
    if (status == 'paused') return '已暂停';
    return catalog.requiresConsent ? '需授权' : '可订阅';
  }
}

final assistantSkillCenterProvider =
    FutureProvider<List<AssistantSkillCenterItem>>((ref) async {
      final repo = ref.watch(assistantRepositoryProvider);
      final catalog = await repo.listSkillCatalog(limit: 64);
      final subscriptions = await repo.listSkillSubscriptions(limit: 64);
      final activeSubscriptions = <String, SkillSubscriptionWire>{
        for (final item in subscriptions)
          if (item.status != 'archived') item.skillId: item,
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
