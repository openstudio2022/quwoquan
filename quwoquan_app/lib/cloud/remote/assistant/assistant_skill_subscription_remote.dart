import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_facets.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef AssistantSkillSubscriptionInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId, {
      String? idempotencyKey,
    });

/// SkillSubscription 的 production generated-client command/query adapter。
final class RemoteAssistantSkillSubscriptionAdapter
    implements AssistantSkillSubscriptionFacet {
  const RemoteAssistantSkillSubscriptionAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final AssistantSkillSubscriptionInvocationContextFactory invocationContext;

  @override
  Future<List<SkillSubscriptionWire>> listSkillSubscriptions({
    int limit = kAssistantSkillSubscriptionsDefaultLimit,
    String status = '',
  }) async {
    // dart format off
    final result = await client.assistantSkillSubscriptionListSkillSubscriptions(
          AssistantSkillSubscriptionListQuery(limit: limit, status: status),
          context: invocationContext(
            AssistantRequestPageIds.listSkillSubscriptions,
          ),
        );
    // dart format on
    return result.items.map(_toWire).toList(growable: false);
  }

  @override
  Future<SkillSubscriptionWire> getSkillSubscription({
    required String subscriptionId,
  }) async {
    final result = await client.assistantSkillSubscriptionGetSkillSubscription(
      AssistantSkillSubscriptionByIdQuery(subscriptionId: subscriptionId),
      context: invocationContext(AssistantRequestPageIds.getSkillSubscription),
    );
    return _toWire(result);
  }

  @override
  Future<SkillSubscriptionWire> createSkillSubscription({
    required String skillId,
    String domainId = 'assistant',
    List<String> tagRefs = const <String>[],
    required String rawText,
    List<String> queries = const <String>[],
    String cron = '0 8 * * *',
    required String clientRequestId,
  }) async {
    // dart format off
    final result = await client.assistantSkillSubscriptionCreateSkillSubscription(
          CreateAssistantSkillSubscriptionCommand(
            skillId: skillId,
            domainId: domainId,
            tagRefs: tagRefs,
            searchQueryPlan: AssistantSkillSubscriptionSearchPlan(
              rawText: rawText,
              queries: queries.isEmpty ? <String>[rawText] : queries,
            ),
            trigger: AssistantSkillSubscriptionTrigger(cron: cron),
            destination: AssistantSkillSubscriptionDestination(
              destinationType: 'user',
            ),
            clientRequestId: clientRequestId,
          ),
          context: invocationContext(
            AssistantRequestPageIds.createSkillSubscription,
            idempotencyKey: clientRequestId,
          ),
        );
    // dart format on
    return _toWire(result);
  }

  @override
  Future<SkillSubscriptionWire> updateSkillSubscriptionStatus({
    required String subscriptionId,
    required String status,
    required String clientRequestId,
  }) async {
    // dart format off
    final result = await client.assistantSkillSubscriptionUpdateSkillSubscriptionStatus(
          UpdateAssistantSkillSubscriptionStatusCommand(
            subscriptionId: subscriptionId,
            status: status,
          ),
          context: invocationContext(
            AssistantRequestPageIds.updateSkillSubscriptionStatus,
            idempotencyKey: clientRequestId,
          ),
        );
    // dart format on
    return _toWire(result);
  }

  SkillSubscriptionWire _toWire(
    AssistantSkillSubscriptionProjection projection,
  ) {
    return SkillSubscriptionWire(
      subscriptionId: projection.subscriptionId,
      owner: SkillSubscriptionOwnerWire(
        ownerType: projection.owner.ownerType,
        ownerId: projection.owner.ownerId,
      ),
      createdByUserId: projection.createdByUserId,
      createdByPersonaId: projection.createdByPersonaId ?? '',
      skillId: projection.skillId,
      domainId: projection.domainId,
      tagRefs: projection.tagRefs,
      status: parseSkillSubscriptionStatusStrict(projection.status),
      searchQueryPlan: SkillSubscriptionSearchQueryPlanWire(
        rawText: projection.searchQueryPlan.rawText,
        queries: projection.searchQueryPlan.queries,
      ),
      trigger: SkillSubscriptionTriggerWire(
        type: projection.trigger.type,
        cron: projection.trigger.cron,
      ),
      destination: SkillSubscriptionDestinationWire(
        destinationType: projection.destination.destinationType,
        destinationId: projection.destination.destinationId ?? '',
        maxPerDay: projection.destination.maxPerDay,
        cooldownMinutes: projection.destination.cooldownMinutes,
        quietHoursPolicy: projection.destination.quietHoursPolicy,
      ),
      deliveryState: SkillSubscriptionDeliveryStateWire(
        pendingDeliveryId: projection.deliveryState.pendingDeliveryId ?? '',
        lastAttemptAt:
            projection.deliveryState.lastAttemptAt?.toIso8601String() ?? '',
        lastDeliveredAt:
            projection.deliveryState.lastDeliveredAt?.toIso8601String() ?? '',
        nextAttemptAt:
            projection.deliveryState.nextAttemptAt?.toIso8601String() ?? '',
        consecutiveFailures: projection.deliveryState.consecutiveFailures,
        lastErrorCode: projection.deliveryState.lastErrorCode ?? '',
      ),
      createdAt: projection.createdAt.toIso8601String(),
      updatedAt: projection.updatedAt.toIso8601String(),
    );
  }
}
