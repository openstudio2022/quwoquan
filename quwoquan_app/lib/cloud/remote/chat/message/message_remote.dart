import 'package:quwoquan_app/cloud/runtime/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatMessageInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

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
