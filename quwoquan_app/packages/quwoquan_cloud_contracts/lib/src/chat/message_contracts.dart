import 'chat_operation_contracts.g.dart';

export 'chat_operation_contracts.g.dart';

abstract interface class ChatMessageCommandWriter {
  Future<ChatSendMessageResult> sendMessage(ChatSendMessageCommand command);
}

abstract interface class ChatMessageQuery {
  Future<MessagePageSlice> listMessages(ChatListMessagesQuery query);

  Future<ChatMessageSyncSlice> syncMessages(ChatSyncMessagesQuery query);

  Future<ConversationAssetPage> listConversationAssets(
    ChatListConversationAssetsQuery query,
  );
}

abstract interface class ChatMessageMutationWriter {
  Future<MessageCommandAck> recallMessage(
    ChatRecallMessageCommand command, {
    required String idempotencyKey,
  });
}
