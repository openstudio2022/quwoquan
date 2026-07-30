import 'package:quwoquan_app/cloud/runtime/generated/assistant/assistant_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// AssistantConversation 已进入 generated-client 单轨的查询适配器。
///
/// 未进入 generated-client 的 run/stream command 仍由其各自 transport owner
/// 承担；这里不混入手写 HTTP，也不提供兼容旁路。
final class RemoteAssistantConversationQueryAdapter {
  const RemoteAssistantConversationQueryAdapter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final CloudOperationInvocationContext Function(String clientPageId)
  invocationContext;

  Future<AssistantConversationProjection> getConversation({
    required String conversationId,
  }) {
    return client.assistantAssistantConversationGetAssistantConversation(
      AssistantConversationByIdQuery(conversationId: conversationId),
      context: invocationContext(
        AssistantRequestPageIds.getAssistantConversation,
      ),
    );
  }

  Future<AssistantConversationListProjection> listConversations({
    required int limit,
    required String cursor,
  }) {
    return client.assistantAssistantConversationListAssistantConversations(
      AssistantConversationListQuery(limit: limit, cursor: cursor),
      context: invocationContext(
        AssistantRequestPageIds.listAssistantConversations,
      ),
    );
  }
}
