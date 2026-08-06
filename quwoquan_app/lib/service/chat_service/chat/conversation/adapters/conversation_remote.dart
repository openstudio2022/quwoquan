import 'package:quwoquan_app/service/chat_service/chat/conversation/application/conversation_query.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatConversationInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);
typedef ChatConversationCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

/// Production Conversation query adapter. Generated descriptors own the path,
/// authorization, retry policy and response decoding; this adapter exposes
/// only the object-scoped typed query.
final class RemoteChatConversationQuery implements ConversationQuery {
  const RemoteChatConversationQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatConversationInvocationContextFactory invocationContext;

  @override
  Future<ConversationBatchSlice> batchGetConversations(
    ChatBatchGetConversationsQuery query,
  ) {
    return client.chatConversationBatchGetConversations(
      query,
      context: invocationContext(ChatRequestPageIds.batchGetConversations),
    );
  }

  @override
  Future<ConversationPageSlice> listConversations(
    ChatListConversationsQuery query,
  ) {
    return client.chatConversationListConversations(
      query,
      context: invocationContext(ChatRequestPageIds.listConversations),
    );
  }

  @override
  Future<ChatConversation> getConversation(ChatGetConversationQuery query) {
    return client.chatConversationGetConversation(
      query,
      context: invocationContext(ChatRequestPageIds.getConversation),
    );
  }

  @override
  Future<ConversationTimestampIndexSlice> listConversationTimestamps(
    ChatListConversationTimestampsQuery query,
  ) {
    return client.chatConversationListConversationTimestamps(
      query,
      context: invocationContext(ChatRequestPageIds.listConversationTimestamps),
    );
  }

  @override
  Future<GroupHome> getGroupHome(ChatGetGroupHomeQuery query) {
    return client.chatConversationGetGroupHome(
      query,
      context: invocationContext(ChatRequestPageIds.getGroupHome),
    );
  }
}

/// Production Conversation command adapter. Generated operations own HTTP
/// routes, idempotency transport and strict response decoding.
final class RemoteChatConversationCommandWriter
    implements ChatConversationCommandWriter {
  const RemoteChatConversationCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatConversationCommandInvocationContextFactory invocationContext;

  @override
  Future<ChatConversation> createConversation(
    ChatCreateConversationCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationCreateConversation(
      command,
      context: invocationContext(
        ChatRequestPageIds.createConversation,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatConversation> updateConversationTitle(
    ChatUpdateConversationTitleCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationUpdateConversationTitle(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateConversationTitle,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ConversationCommandAck> dissolveConversation(
    ChatDissolveConversationCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationDissolveConversation(
      command,
      context: invocationContext(
        ChatRequestPageIds.dissolveConversation,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatConversation> updateAnnouncement(
    ChatUpdateAnnouncementCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationUpdateAnnouncement(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateAnnouncement,
        idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatConversation> updateGroupGovernanceSettings(
    ChatUpdateGroupGovernanceSettingsCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationUpdateGroupGovernanceSettings(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateGroupGovernanceSettings,
        idempotencyKey,
      ),
    );
  }
}
