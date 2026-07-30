// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../chat/conversation_user_state_contracts.dart';

final class ChatMarkConversationMessageReadCommand {
  ChatMarkConversationMessageReadCommand({
    required String conversationId,
    required String messageId,
  }) : conversationId = conversationId.trim(),
       messageId = messageId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.messageId.isEmpty) {
      throw ArgumentError.value(this.messageId, "messageId", 'must not be blank');
    }
  }

  final String conversationId;
  final String messageId;
}

final class ChatUpdateConversationSettingsCommand {
  ChatUpdateConversationSettingsCommand({
    required String conversationId,
    bool? muted,
    bool? pinned,
  }) : conversationId = conversationId.trim(),
       muted = muted,
       pinned = pinned {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final bool? muted;
  final bool? pinned;
}

CloudOperationRequestPayload encodeChatConversationUserStateMarkAsReadGeneratedRequest(ChatMarkConversationMessageReadCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUserStateUpdateConversationSettingsGeneratedRequest(ChatUpdateConversationSettingsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      if (request.muted != null) "muted": request.muted!,
      if (request.pinned != null) "pinned": request.pinned!,
    },
  );
}

