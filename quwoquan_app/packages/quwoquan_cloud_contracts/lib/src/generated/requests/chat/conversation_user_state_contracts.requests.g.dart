// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

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

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "messageId": this.messageId,
  };
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

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.muted != null) "muted": this.muted!,
    if (this.pinned != null) "pinned": this.pinned!,
  };
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

