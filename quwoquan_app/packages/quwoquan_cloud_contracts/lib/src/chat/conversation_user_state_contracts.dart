import '../operation_request_payload.dart';
import 'conversation_contracts.dart' show ChatCommandAck;

export 'conversation_contracts.dart' show ChatCommandAck;

abstract interface class ChatConversationUserStateCommandWriter {
  Future<ChatCommandAck> markMessageRead(
    ChatMarkConversationMessageReadCommand command,
  );

  Future<ChatCommandAck> updateConversationSettings(
    ChatUpdateConversationSettingsCommand command,
  );
}

final class ChatMarkConversationMessageReadCommand {
  ChatMarkConversationMessageReadCommand({
    required String conversationId,
    required String idempotencyKey,
    required String messageId,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(idempotencyKey, 'idempotencyKey'),
       messageId = _requiredNonBlankText(messageId, 'messageId');

  final String conversationId;
  final String idempotencyKey;
  final String messageId;
}

CloudOperationRequestPayload encodeChatMarkConversationMessageReadCommand(
  ChatMarkConversationMessageReadCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      'conversationId': command.conversationId,
      'messageId': command.messageId,
    },
  );
}

final class ChatUpdateConversationSettingsCommand {
  ChatUpdateConversationSettingsCommand({
    required String conversationId,
    required String idempotencyKey,
    this.muted,
    this.pinned,
  }) : conversationId = _requiredNonBlankText(conversationId, 'conversationId'),
       idempotencyKey = _requiredNonBlankText(
         idempotencyKey,
         'idempotencyKey',
       ) {
    if (muted == null && pinned == null) {
      throw ArgumentError('at least one of muted or pinned is required');
    }
  }

  final String conversationId;
  final String idempotencyKey;
  final bool? muted;
  final bool? pinned;
}

CloudOperationRequestPayload encodeChatUpdateConversationSettingsCommand(
  ChatUpdateConversationSettingsCommand command,
) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{'conversationId': command.conversationId},
    body: <String, Object?>{
      if (command.muted case final value?) 'muted': value,
      if (command.pinned case final value?) 'pinned': value,
    },
  );
}

String _requiredNonBlankText(String value, String field) {
  final normalized = value.trim();
  if (normalized.isEmpty) {
    throw ArgumentError.value(value, field, 'must not be blank');
  }
  return normalized;
}
