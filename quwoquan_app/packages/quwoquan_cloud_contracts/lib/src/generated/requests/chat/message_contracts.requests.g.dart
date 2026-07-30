// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

part of '../../../chat/message_contracts.dart';

String? _normalizeGeneratedOptionalText(String? value) {
  final normalized = value?.trim();
  return normalized == null || normalized.isEmpty ? null : normalized;
}

List<String> _normalizeGeneratedTextList(
  Iterable<String> values, {
  required bool deduplicate,
}) {
  final result = <String>[];
  final seen = <String>{};
  for (final value in values) {
    final normalized = value.trim();
    if (normalized.isEmpty) continue;
    if (deduplicate && !seen.add(normalized)) continue;
    result.add(normalized);
  }
  return List<String>.unmodifiable(result);
}

final class ChatListMessagesQuery {
  ChatListMessagesQuery({
    required String conversationId,
    int? afterSeq,
    int? beforeSeq,
    int limit = 20,
  }) : conversationId = conversationId.trim(),
       afterSeq = afterSeq,
       beforeSeq = beforeSeq,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final int? afterSeq;
  final int? beforeSeq;
  final int limit;
}

final class ChatRecallMessageCommand {
  ChatRecallMessageCommand({
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

final class ChatSendMessageCommand {
  ChatSendMessageCommand({
    required String conversationId,
    required String type,
    required String content,
    required String clientMsgId,
    String? mediaAssetId,
    ChatMessageCardCommand? card,
    String? replyToMessageId,
    Iterable<String> mentions = const <String>[],
    String? senderDisplayNameSnapshot,
    String? senderAvatarUrlSnapshot,
    int? personaContextVersion,
  }) : conversationId = conversationId.trim(),
       type = type.trim(),
       content = content,
       clientMsgId = clientMsgId.trim(),
       mediaAssetId = _normalizeGeneratedOptionalText(mediaAssetId),
       card = card,
       replyToMessageId = _normalizeGeneratedOptionalText(replyToMessageId),
       mentions = _normalizeGeneratedTextList(mentions, deduplicate: false),
       senderDisplayNameSnapshot = _normalizeGeneratedOptionalText(senderDisplayNameSnapshot),
       senderAvatarUrlSnapshot = _normalizeGeneratedOptionalText(senderAvatarUrlSnapshot),
       personaContextVersion = personaContextVersion {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.type.isEmpty) {
      throw ArgumentError.value(this.type, "type", 'must not be blank');
    }
    if (this.clientMsgId.isEmpty) {
      throw ArgumentError.value(this.clientMsgId, "clientMsgId", 'must not be blank');
    }
    if (this.type == "image" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is image");
    }
    if (this.type == "video" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is video");
    }
    if (this.type == "audio" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is audio");
    }
    if (this.type == "file" && this.mediaAssetId == null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is required when type is file");
    }
    if (this.type == "text" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is text");
    }
    if (this.type == "card" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is card");
    }
    if (this.type == "system_call_log" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is system_call_log");
    }
    if (this.type == "system_announcement" && this.mediaAssetId != null) {
      throw ArgumentError.value(this.mediaAssetId, "mediaAssetId", "is forbidden when type is system_announcement");
    }
    if (this.type == "card" && this.card == null) {
      throw ArgumentError.value(this.card, "card", "is required when type is card");
    }
    if (this.type != "card" && this.card != null) {
      throw ArgumentError.value(this.card, "card", "is forbidden unless type is card");
    }
  }

  final String conversationId;
  final String type;
  final String content;
  final String clientMsgId;
  final String? mediaAssetId;
  final ChatMessageCardCommand? card;
  final String? replyToMessageId;
  final List<String> mentions;
  final String? senderDisplayNameSnapshot;
  final String? senderAvatarUrlSnapshot;
  final int? personaContextVersion;
}

final class ChatSyncMessagesQuery {
  ChatSyncMessagesQuery({
    required String conversationId,
    required int lastSeq,
    int limit = 500,
  }) : conversationId = conversationId.trim(),
       lastSeq = lastSeq,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final int lastSeq;
  final int limit;
}

CloudOperationRequestPayload encodeChatMessageListMessagesGeneratedRequest(ChatListMessagesQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.afterSeq != null) "afterSeq": (request.afterSeq!).toString(),
      if (request.beforeSeq != null) "beforeSeq": (request.beforeSeq!).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatMessageRecallMessageGeneratedRequest(ChatRecallMessageCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeChatMessageSendMessageGeneratedRequest(ChatSendMessageCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "type": request.type,
      "content": request.content,
      "clientMsgId": request.clientMsgId,
      if (request.mediaAssetId != null) "mediaAssetId": request.mediaAssetId!,
      if (request.card != null) "card": <String, Object?>{'kind': request.card!.kind, 'title': request.card!.title, if (request.card!.subtitle != null) 'subtitle': request.card!.subtitle, if (request.card!.thumbnailUrl != null) 'thumbnailUrl': request.card!.thumbnailUrl, if (request.card!.deeplink != null) 'deeplink': request.card!.deeplink, if (request.card!.landingUrl != null) 'landingUrl': request.card!.landingUrl, if (request.card!.shareText != null) 'shareText': request.card!.shareText, if (request.card!.message != null) 'message': request.card!.message, 'attributes': <Map<String, String>>[for (final attribute in request.card!.attributes) <String, String>{'name': attribute.name, 'value': attribute.value}]},
      if (request.replyToMessageId != null) "replyToMessageId": request.replyToMessageId!,
      if (request.mentions.isNotEmpty) "mentions": request.mentions.map((value) => value).toList(growable: false),
      if (request.senderDisplayNameSnapshot != null) "senderDisplayNameSnapshot": request.senderDisplayNameSnapshot!,
      if (request.senderAvatarUrlSnapshot != null) "senderAvatarUrlSnapshot": request.senderAvatarUrlSnapshot!,
      if (request.personaContextVersion != null) "personaContextVersion": request.personaContextVersion!,
    },
  );
}

CloudOperationRequestPayload encodeChatMessageSyncMessagesGeneratedRequest(ChatSyncMessagesQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "lastSeq": request.lastSeq,
      "limit": request.limit,
    },
  );
}

