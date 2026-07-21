import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
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
final class RemoteChatConversationQuery implements ChatConversationQuery {
  const RemoteChatConversationQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatConversationInvocationContextFactory invocationContext;

  @override
  Future<ChatConversationBatchSlice> batchGetConversations(
    ChatBatchGetConversationsQuery query,
  ) {
    return client.chatConversationBatchGetConversations(
      query,
      context: invocationContext(ChatRequestPageIds.batchGetConversations),
    );
  }

  @override
  Future<ChatConversationPageSlice> listConversations(
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
  Future<ChatConversationTimestampPageSlice> listConversationTimestamps(
    ChatListConversationTimestampsQuery query,
  ) {
    return client.chatConversationListConversationTimestamps(
      query,
      context: invocationContext(ChatRequestPageIds.listConversationTimestamps),
    );
  }

  @override
  Future<ChatGroupHome> getGroupHome(ChatGetGroupHomeQuery query) {
    return client.chatConversationGetGroupHome(
      query,
      context: invocationContext(ChatRequestPageIds.getGroupHome),
    );
  }

  @override
  Future<ChatMessageReceiptPageSlice> getMessageReceipts(
    ChatGetMessageReceiptsQuery query,
  ) {
    return client.chatConversationGetReceipts(
      query,
      context: invocationContext(ChatRequestPageIds.getReceipts),
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
    ChatCreateConversationCommand command,
  ) {
    return client.chatConversationCreateConversation(
      command,
      context: invocationContext(
        ChatRequestPageIds.createConversation,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatConversation> updateConversationTitle(
    ChatUpdateConversationTitleCommand command,
  ) {
    return client.chatConversationUpdateConversationTitle(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateConversationTitle,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatCommandAck> dissolveConversation(
    ChatDissolveConversationCommand command,
  ) {
    return client.chatConversationDissolveConversation(
      command,
      context: invocationContext(
        ChatRequestPageIds.dissolveConversation,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatConversation> updateAnnouncement(
    ChatUpdateAnnouncementCommand command,
  ) {
    return client.chatConversationUpdateAnnouncement(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateAnnouncement,
        command.idempotencyKey,
      ),
    );
  }

  @override
  Future<ChatConversation> updateGroupGovernanceSettings(
    ChatUpdateGroupGovernanceSettingsCommand command,
  ) {
    return client.chatConversationUpdateGroupGovernanceSettings(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateGroupGovernanceSettings,
        command.idempotencyKey,
      ),
    );
  }
}
