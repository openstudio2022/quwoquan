// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../chat/contact_contracts.dart';

final class ChatListContactHomeQuery {
  const ChatListContactHomeQuery({
    String filter = 'all',
    int limit = 50,
  }) : filter = filter,
       limit = limit;

  final String filter;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "filter": this.filter,
    "limit": this.limit,
  };
}

final class ChatListContactsQuery {
  const ChatListContactsQuery({
    String? cursor,
    int limit = 20,
  }) : cursor = cursor,
       limit = limit;

  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListGroupCandidatesQuery {
  const ChatListGroupCandidatesQuery({
    String? conversationId,
    int limit = 100,
  }) : conversationId = conversationId,
       limit = limit;

  final String? conversationId;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.conversationId != null) "conversationId": this.conversationId!,
    "limit": this.limit,
  };
}

final class ChatListInboxQuery {
  const ChatListInboxQuery({
    String? cursor,
    int limit = 50,
  }) : cursor = cursor,
       limit = limit;

  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListSelectableGroupContactMembersQuery {
  ChatListSelectableGroupContactMembersQuery({
    required String conversationId,
    String? query,
    String? cursor,
    int limit = 100,
  }) : conversationId = conversationId.trim(),
       query = query,
       cursor = cursor,
       limit = limit {
    if (this.conversationId.isEmpty) {
      throw ArgumentError.value(this.conversationId, "conversationId", 'must not be blank');
    }
  }

  final String conversationId;
  final String? query;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "conversationId": this.conversationId,
    if (this.query != null) "query": this.query!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ChatListSelectableGroupConversationsQuery {
  const ChatListSelectableGroupConversationsQuery({
    String? query,
    String? source,
    String? cursor,
    int limit = 50,
  }) : query = query,
       source = source,
       cursor = cursor,
       limit = limit;

  final String? query;
  final String? source;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.query != null) "query": this.query!,
    if (this.source != null) "source": this.source!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

CloudOperationRequestPayload encodeChatConversationListContactHomeGeneratedRequest(ChatListContactHomeQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "filter": request.filter,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListContactsGeneratedRequest(ChatListContactsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListGroupCandidatesGeneratedRequest(ChatListGroupCandidatesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.conversationId != null) "conversationId": request.conversationId!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListInboxGeneratedRequest(ChatListInboxQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListSelectableGroupContactMembersGeneratedRequest(ChatListSelectableGroupContactMembersQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "conversationId": request.conversationId,
    },
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.query != null) "query": request.query!,
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

CloudOperationRequestPayload encodeChatConversationListSelectableGroupConversationsGeneratedRequest(ChatListSelectableGroupConversationsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.query != null) "query": request.query!,
      if (request.source != null) "source": request.source!,
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

