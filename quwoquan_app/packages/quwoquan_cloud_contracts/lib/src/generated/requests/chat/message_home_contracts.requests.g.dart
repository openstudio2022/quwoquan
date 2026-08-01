// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../chat/message_home_contracts.dart';

final class ChatListMessageHomeQuery {
  const ChatListMessageHomeQuery({
    String filter = 'all',
    String? cursor,
    int limit = 20,
  }) : filter = filter,
       cursor = cursor,
       limit = limit;

  final String filter;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    "filter": this.filter,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

CloudOperationRequestPayload encodeChatConversationListMessageHomeGeneratedRequest(ChatListMessageHomeQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "filter": request.filter,
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
    },
  );
}

