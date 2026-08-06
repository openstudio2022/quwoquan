import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Conversation 对象自有查询端口；不包含其他对象的投影查询。
abstract interface class ConversationQuery {
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
}
