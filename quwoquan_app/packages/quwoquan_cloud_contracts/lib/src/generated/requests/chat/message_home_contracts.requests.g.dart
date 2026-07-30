// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 80b68db6b546ae955959cb31a73c5fdfb60da766b906dc9529a837191ea4a01e

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

