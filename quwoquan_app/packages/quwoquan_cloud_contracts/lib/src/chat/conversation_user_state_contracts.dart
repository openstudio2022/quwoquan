import 'chat_operation_contracts.g.dart';

export 'chat_operation_contracts.g.dart';

abstract interface class ChatConversationUserStateCommandWriter {
  Future<ConversationUserStateCommandAck> markMessageRead(
    ChatMarkConversationMessageReadCommand command, {
    required String idempotencyKey,
  });

  Future<ConversationUserStateCommandAck> updateConversationSettings(
    ChatUpdateConversationSettingsCommand command, {
    required String idempotencyKey,
  });
}
