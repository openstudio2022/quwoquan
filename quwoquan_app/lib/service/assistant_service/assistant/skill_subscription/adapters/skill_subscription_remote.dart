import 'package:quwoquan_app/runtime/transport/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_app/service/assistant_service/assistant/skill_subscription/application/skill_subscription_facet.dart';
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
    return result.items;
  }

  @override
  Future<SkillSubscriptionWire> getSkillSubscription({
    required String subscriptionId,
  }) async {
    final result = await client.assistantSkillSubscriptionGetSkillSubscription(
      AssistantSkillSubscriptionByIdQuery(subscriptionId: subscriptionId),
      context: invocationContext(AssistantRequestPageIds.getSkillSubscription),
    );
    return result;
  }

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
    // dart format off
    final result = await client.assistantSkillSubscriptionCreateSkillSubscription(
          CreateAssistantSkillSubscriptionCommand(
            skillId: skillId,
            domainId: domainId,
            tagRefs: tagRefs,
            searchQueryPlan: SkillSubscriptionSearchQueryPlanWire(
              rawText: rawText,
              queries: queries.isEmpty ? <String>[rawText] : queries,
            ),
            trigger: SkillSubscriptionTriggerWire(
              cron: cron,
              timezone: timezone,
            ),
            destination: const SkillSubscriptionDestinationWire(
              destinationType: SkillSubscriptionDestinationType.user,
            ),
            clientRequestId: clientRequestId,
          ),
          context: invocationContext(
            AssistantRequestPageIds.createSkillSubscription,
            idempotencyKey: clientRequestId,
          ),
        );
    // dart format on
    return result;
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
            clientRequestId: clientRequestId,
          ),
          context: invocationContext(
            AssistantRequestPageIds.updateSkillSubscriptionStatus,
            idempotencyKey: clientRequestId,
          ),
        );
    // dart format on
    return result;
  }
}
