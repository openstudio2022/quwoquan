// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../chat/conversation_membership_contracts.dart';

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

final class ChatAddConversationMembersCommand {
  ChatAddConversationMembersCommand({
    required String conversationId,
    required Iterable<String> userIds,
  }) : conversationId = conversationId.trim(),
       userIds = _normalizeGeneratedTextList(userIds, deduplicate: false) {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.userIds.isEmpty) {
      throw ArgumentError.value(this.userIds, "userIds", 'must not be blank');
    }
  }

  final String conversationId;
  final List<String> userIds;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "userIds": this.userIds.map((value) => value).toList(growable: false),
  };
}

final class ChatInviteConversationAssistantCommand {
  ChatInviteConversationAssistantCommand({
    required String conversationId,
    String? skillId,
  }) : conversationId = conversationId.trim(),
       skillId = _normalizeGeneratedOptionalText(skillId) {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final String? skillId;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.skillId != null) "skillId": this.skillId!,
  };
}

final class ChatLeaveConversationCommand {
  ChatLeaveConversationCommand({
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

final class ChatListConversationMembersQuery {
  ChatListConversationMembersQuery({
    required String conversationId,
    String? cursor,
    int limit = 20,
    String? role,
    String sort = 'joined_asc',
    String? query,
  }) : conversationId = conversationId.trim(),
       cursor = cursor,
       limit = limit,
       role = role,
       sort = sort,
       query = query {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (!const <String>{"joined_asc", "display_name_asc"}.contains(this.sort)) {
      throw ArgumentError.value(this.sort, "sort", 'unsupported canonical enum value');
    }
  }

  final String conversationId;
  final String? cursor;
  final int limit;
  final String? role;
  final String sort;
  final String? query;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.role != null) "role": this.role!,
    "sort": this.sort,
    if (this.query != null) "query": this.query!,
  };
}

final class ChatRemoveConversationAssistantCommand {
  ChatRemoveConversationAssistantCommand({
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

final class ChatRemoveConversationMemberCommand {
  ChatRemoveConversationMemberCommand({
    required String conversationId,
    required String userId,
  }) : conversationId = conversationId.trim(),
       userId = userId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.userId.isEmpty) {
      throw ArgumentError.value(this.userId, "userId", 'must not be blank');
    }
  }

  final String conversationId;
  final String userId;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "userId": this.userId,
  };
}

final class ChatTransferConversationOwnershipCommand {
  ChatTransferConversationOwnershipCommand({
    required String conversationId,
    required String newOwnerId,
  }) : conversationId = conversationId.trim(),
       newOwnerId = newOwnerId.trim() {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.newOwnerId.isEmpty) {
      throw ArgumentError.value(this.newOwnerId, "newOwnerId", 'must not be blank');
    }
  }

  final String conversationId;
  final String newOwnerId;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "newOwnerId": this.newOwnerId,
  };
}

final class ChatUpdateConversationAdminsCommand {
  ChatUpdateConversationAdminsCommand({
    required String conversationId,
    required Iterable<String> adminIds,
  }) : conversationId = conversationId.trim(),
       adminIds = _normalizeGeneratedTextList(adminIds, deduplicate: false) {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
    if (this.adminIds.isEmpty) {
      throw ArgumentError.value(this.adminIds, "adminIds", 'must not be blank');
    }
  }

  final String conversationId;
  final List<String> adminIds;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    "adminIds": this.adminIds.map((value) => value).toList(growable: false),
  };
}

CloudOperationRequestPayload encodeChatConversationMembershipAddMembersGeneratedRequest(ChatAddConversationMembersCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "userIds": request.userIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipInviteAssistantGeneratedRequest(ChatInviteConversationAssistantCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      if (request.skillId != null) "skillId": request.skillId!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipLeaveConversationGeneratedRequest(ChatLeaveConversationCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipListMembersGeneratedRequest(ChatListConversationMembersQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
      if (request.role != null) "role": request.role!,
      "sort": request.sort,
      if (request.query != null) "query": request.query!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipRemoveAssistantGeneratedRequest(ChatRemoveConversationAssistantCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipRemoveMemberGeneratedRequest(ChatRemoveConversationMemberCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
      "userId": request.userId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipTransferOwnershipGeneratedRequest(ChatTransferConversationOwnershipCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "newOwnerId": request.newOwnerId,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationMembershipUpdateGroupAdminsGeneratedRequest(ChatUpdateConversationAdminsCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    body: <String, Object?>{
      "adminIds": request.adminIds.map((value) => value).toList(growable: false),
    },
  );
}

