import 'chat_operation_contracts.g.dart';

export 'chat_operation_contracts.g.dart';

/// Object-scoped application port. Request/response values are generated from
/// the canonical Chat contracts; this facade owns no wire model or decoder.
abstract interface class ChatConversationQuery {
  Future<ConversationBatchSlice> batchGetConversations(
    ChatBatchGetConversationsQuery query,
  );

  Future<ConversationPageSlice> listConversations(
    ChatListConversationsQuery query,
  );

  Future<ChatConversation> getConversation(ChatGetConversationQuery query);

  Future<ConversationTimestampIndexSlice> listConversationTimestamps(
    ChatListConversationTimestampsQuery query,
  );

  Future<GroupHome> getGroupHome(ChatGetGroupHomeQuery query);

  Future<MessageReceiptPageSlice> getMessageReceipts(
    ChatGetMessageReceiptsQuery query,
  );
}

/// Object-scoped command port over the single generated Chat ABI.
abstract interface class ChatConversationCommandWriter {
  Future<ChatConversation> createConversation(
    ChatCreateConversationCommand command, {
    required String idempotencyKey,
  });

  Future<ChatConversation> updateConversationTitle(
    ChatUpdateConversationTitleCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationCommandAck> dissolveConversation(
    ChatDissolveConversationCommand command, {
    required String idempotencyKey,
  });

  Future<ChatConversation> updateAnnouncement(
    ChatUpdateAnnouncementCommand command, {
    required String idempotencyKey,
  });

  Future<ChatConversation> updateGroupGovernanceSettings(
    ChatUpdateGroupGovernanceSettingsCommand command, {
    required String idempotencyKey,
  });
}
