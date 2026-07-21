import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatMessageInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );
typedef ChatMessageQueryInvocationContextFactory =
    CloudOperationInvocationContext Function(String clientPageId);

/// Production-only Message command Remote；不接收 path、operationId 或动态 body。
final class RemoteChatMessageCommandWriter implements ChatMessageCommandWriter {
  const RemoteChatMessageCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatMessageInvocationContextFactory invocationContext;

  @override
  Future<ChatSendMessageResult> sendMessage(ChatSendMessageCommand command) {
    return client.chatMessageSendMessage(
      command,
      context: invocationContext(
        ChatRequestPageIds.sendMessage,
        command.clientMsgId,
      ),
    );
  }
}

final class RemoteChatMessageQuery implements ChatMessageQuery {
  const RemoteChatMessageQuery({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatMessageQueryInvocationContextFactory invocationContext;

  @override
  Future<ChatMessagePageSlice> listMessages(ChatListMessagesQuery query) {
    return client.chatMessageListMessages(
      query,
      context: invocationContext(ChatRequestPageIds.listMessages),
    );
  }

  @override
  Future<ChatMessageSyncSlice> syncMessages(ChatSyncMessagesQuery query) {
    return client.chatMessageSyncMessages(
      query,
      context: invocationContext(ChatRequestPageIds.syncMessages),
    );
  }
}

final class RemoteChatMessageMutationWriter
    implements ChatMessageMutationWriter {
  const RemoteChatMessageMutationWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatMessageInvocationContextFactory invocationContext;

  @override
  Future<ChatCommandAck> recallMessage(ChatRecallMessageCommand command) {
    return client.chatMessageRecallMessage(
      command,
      context: invocationContext(
        ChatRequestPageIds.recallMessage,
        command.idempotencyKey,
      ),
    );
  }
}
