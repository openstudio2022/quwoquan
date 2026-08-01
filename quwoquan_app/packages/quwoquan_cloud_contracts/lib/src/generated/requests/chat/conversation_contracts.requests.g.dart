// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../chat/conversation_contracts.dart';

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

final class ChatBatchGetConversationsQuery {
  ChatBatchGetConversationsQuery({
    required Iterable<String> conversationIds,
  }) : conversationIds = _normalizeGeneratedTextList(conversationIds, deduplicate: false) {
    if (this.conversationIds.isEmpty) {
      throw ArgumentError.value(this.conversationIds, "conversationIds", 'must not be blank');
    }
  }

  final List<String> conversationIds;

  Map<String, Object?> toJson() => <String, Object?>{
    "ids": this.conversationIds.map((value) => value).toList(growable: false),
  };
}

final class ChatCreateConversationCommand {
  ChatCreateConversationCommand({
    required String type,
    String? title,
    int? maxGroupSize,
    Iterable<String> initialMemberIds = const <String>[],
  }) : type = type.trim(),
       title = _normalizeGeneratedOptionalText(title),
       maxGroupSize = maxGroupSize,
       initialMemberIds = _normalizeGeneratedTextList(initialMemberIds, deduplicate: false) {
    if (this.type.isEmpty) {
      throw ArgumentError.value(this.type, "type", 'must not be blank');
    }
  }

  final String type;
  final String? title;
  final int? maxGroupSize;
  final List<String> initialMemberIds;

  Map<String, Object?> toJson() => <String, Object?>{
    "type": this.type,
    if (this.title != null) "title": this.title!,
    if (this.maxGroupSize != null) "maxGroupSize": this.maxGroupSize!,
    if (this.initialMemberIds.isNotEmpty) "initialMemberIds": this.initialMemberIds.map((value) => value).toList(growable: false),
  };
}

final class ChatDissolveConversationCommand {
  ChatDissolveConversationCommand({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatGetConversationQuery {
  ChatGetConversationQuery({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatGetGroupHomeQuery {
  ChatGetGroupHomeQuery({
    required String conversationId,
  }) : conversationId = conversationId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
  };
}

final class ChatGetMessageReceiptsQuery {
  ChatGetMessageReceiptsQuery({
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

final class ChatListConversationTimestampsQuery {
  const ChatListConversationTimestampsQuery();
}

final class ChatListConversationsQuery {
  const ChatListConversationsQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit;

  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.cursor?.isNotEmpty == true) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatUpdateAnnouncementCommand {
  ChatUpdateAnnouncementCommand({
    required String conversationId,
    required String announcement,
  }) : conversationId = conversationId.trim(),
       announcement = announcement {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final String announcement;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "announcement": this.announcement,
  };
}

final class ChatUpdateConversationTitleCommand {
  ChatUpdateConversationTitleCommand({
    required String conversationId,
    required String title,
  }) : conversationId = conversationId.trim(),
       title = title.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.title.isEmpty) {
      throw ArgumentError.value(this.title, "title", 'must not be blank');
    }
  }

  final String conversationId;
  final String title;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "title": this.title,
  };
}

final class ChatUpdateGroupGovernanceSettingsCommand {
  ChatUpdateGroupGovernanceSettingsCommand({
    required String conversationId,
    required bool nameEditableByAdminOnly,
  }) : conversationId = conversationId.trim(),
       nameEditableByAdminOnly = nameEditableByAdminOnly {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final bool nameEditableByAdminOnly;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "nameEditableByAdminOnly": this.nameEditableByAdminOnly,
  };
}

CloudOperationRequestPayload encodeChatConversationBatchGetConversationsGeneratedRequest(ChatBatchGetConversationsQuery request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "ids": request.conversationIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationCreateConversationGeneratedRequest(ChatCreateConversationCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "type": request.type,
      if (request.title != null) "title": request.title!,
      if (request.maxGroupSize != null) "maxGroupSize": request.maxGroupSize!,
      if (request.initialMemberIds.isNotEmpty) "initialMemberIds": request.initialMemberIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationDissolveConversationGeneratedRequest(ChatDissolveConversationCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationGetConversationGeneratedRequest(ChatGetConversationQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationGetGroupHomeGeneratedRequest(ChatGetGroupHomeQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationGetReceiptsGeneratedRequest(ChatGetMessageReceiptsQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListConversationTimestampsGeneratedRequest(ChatListConversationTimestampsQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeChatConversationListConversationsGeneratedRequest(ChatListConversationsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.cursor?.isNotEmpty == true) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUpdateAnnouncementGeneratedRequest(ChatUpdateAnnouncementCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "announcement": request.announcement,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUpdateConversationTitleGeneratedRequest(ChatUpdateConversationTitleCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "title": request.title,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationUpdateGroupGovernanceSettingsGeneratedRequest(ChatUpdateGroupGovernanceSettingsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "nameEditableByAdminOnly": request.nameEditableByAdminOnly,
    },
  );
}

