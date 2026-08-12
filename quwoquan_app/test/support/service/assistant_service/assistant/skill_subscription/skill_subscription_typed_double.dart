import 'package:quwoquan_app/service/assistant_service/assistant/skill_subscription/application/skill_subscription_facet.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

class InMemoryAssistantSkillSubscriptionFacet
    implements AssistantSkillSubscriptionFacet {
  final List<SkillSubscriptionWire> _subscriptions = <SkillSubscriptionWire>[];

  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    final filtered = _subscriptions.where((item) {
      if (status.trim().isEmpty) {
        return item.status != SkillSubscriptionStatus.archived;
      }
      return item.status.wireName == status.trim();
    });
    return filtered.take(limit).toList(growable: false);
  }

  @override
  Future<SkillSubscriptionWire> getSkillSubscription({
    required String subscriptionId,
  }) async => _subscriptions.singleWhere(
    (item) => item.subscriptionId == subscriptionId.trim(),
    orElse: () => throw StateError('skill subscription not found'),
  );

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
    String timezone = 'Asia/Shanghai',
    required String clientRequestId,
  }) async {
    if (clientRequestId.trim().isEmpty) {
      throw ArgumentError.value(clientRequestId, 'clientRequestId', 'required');
    }
    final now = DateTime.now().toUtc().toIso8601String();
    final subscription = SkillSubscriptionWire(
      subscriptionId: 'sub_fixture_${_subscriptions.length + 1}',
      version: 1,
      createdByUserId: 'fixture-user',
      skillId: skillId,
      domainId: domainId,
      tagRefs: tagRefs,
      searchQueryPlan: SkillSubscriptionSearchQueryPlanWire(
        rawText: rawText,
        queries: queries.isEmpty ? <String>[rawText] : queries,
      ),
      trigger: SkillSubscriptionTriggerWire(cron: cron, timezone: timezone),
      destination: const SkillSubscriptionDestinationWire(
        destinationType: SkillSubscriptionDestinationType.user,
        destinationId: 'fixture-user',
      ),
      createdAt: now,
      updatedAt: now,
    );
    _subscriptions.insert(0, subscription);
    return subscription;
  }

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
    required String clientRequestId,
  }) async {
    if (clientRequestId.trim().isEmpty) {
      throw ArgumentError.value(clientRequestId, 'clientRequestId', 'required');
    }
    final index = _subscriptions.indexWhere(
      (item) => item.subscriptionId == subscriptionId,
    );
    if (index < 0) throw StateError('skill subscription not found');
    final current = _subscriptions[index];
    final updated = SkillSubscriptionWire(
      subscriptionId: current.subscriptionId,
      version: current.version + 1,
      owner: current.owner,
      createdByUserId: current.createdByUserId,
      skillId: current.skillId,
      domainId: current.domainId,
      tagRefs: current.tagRefs,
      status: parseSkillSubscriptionStatusStrict(status),
      searchQueryPlan: current.searchQueryPlan,
      trigger: current.trigger,
      destination: current.destination,
      createdAt: current.createdAt,
      updatedAt: DateTime.now().toUtc().toIso8601String(),
    );
    _subscriptions[index] = updated;
    return updated;
  }
}
