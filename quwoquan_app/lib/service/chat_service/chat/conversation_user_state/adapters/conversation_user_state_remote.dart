import 'package:quwoquan_app/service/chat_service/chat/conversation_user_state/application/public/conversation_user_state_command_writer.dart';
import 'package:quwoquan_app/runtime/transport/generated/chat/chat_request_page_ids.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

typedef ChatConversationUserStateCommandInvocationContextFactory =
    CloudOperationInvocationContext Function(
      String clientPageId,
      String idempotencyKey,
    );

final class RemoteChatConversationUserStateCommandWriter
    implements ConversationUserStateCommandWriter {
  const RemoteChatConversationUserStateCommandWriter({
    required this.client,
    required this.invocationContext,
  });

  final GeneratedCloudOperationClient client;
  final ChatConversationUserStateCommandInvocationContextFactory
  invocationContext;

  @override
  Future<ConversationUserStateCommandAck> markMessageRead(
    ChatMarkConversationMessageReadCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationUserStateMarkAsRead(
      command,
      context: invocationContext(ChatRequestPageIds.markAsRead, idempotencyKey),
    );
  }

  @override
  Future<ConversationUserStateCommandAck> updateConversationSettings(
    ChatUpdateConversationSettingsCommand command, {
    required String idempotencyKey,
  }) {
    return client.chatConversationUserStateUpdateConversationSettings(
      command,
      context: invocationContext(
        ChatRequestPageIds.updateConversationSettings,
        idempotencyKey,
      ),
    );
  }
}
