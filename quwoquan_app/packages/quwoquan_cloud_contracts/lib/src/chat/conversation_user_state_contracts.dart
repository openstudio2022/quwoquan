import '../operation_request_payload.dart';
import 'conversation_contracts.dart' show ChatCommandAck;

export 'conversation_contracts.dart' show ChatCommandAck;
part '../generated/requests/chat/conversation_user_state_contracts.requests.g.dart';

abstract interface class ChatConversationUserStateCommandWriter {
  Future<ChatCommandAck> markMessageRead(
    ChatMarkConversationMessageReadCommand command, {
    required String idempotencyKey,
  });

  Future<ChatCommandAck> updateConversationSettings(
    ChatUpdateConversationSettingsCommand command, {
    required String idempotencyKey,
  });
}
