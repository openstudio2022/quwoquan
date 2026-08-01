// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../notification/app_message_contracts.dart';

final class AckAppMessageCommand {
  const AckAppMessageCommand({
    required String messageId,
  }) : messageId = messageId;

  final String messageId;

  Map<String, Object?> toJson() => <String, Object?>{
    "messageId": this.messageId,
  };
}

final class GetAppMessageQuery {
  const GetAppMessageQuery({
    required String messageId,
  }) : messageId = messageId;

  final String messageId;

  Map<String, Object?> toJson() => <String, Object?>{
    "messageId": this.messageId,
  };
}

final class GetAppMessageUnreadCountQuery {
  const GetAppMessageUnreadCountQuery();
}

final class ListAppMessagesQuery {
  const ListAppMessagesQuery({
    String? messageType,
    bool? read,
    String? cursor,
    int limit = 20,
  }) : messageType = messageType,
       read = read,
       cursor = cursor,
       limit = limit;

  final String? messageType;
  final bool? read;
  final String? cursor;
  final int limit;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.messageType != null) "type": this.messageType!,
    if (this.read != null) "read": this.read!,
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
  };
}

final class ReadAppMessageCommand {
  const ReadAppMessageCommand({
    required String messageId,
  }) : messageId = messageId;

  final String messageId;

  Map<String, Object?> toJson() => <String, Object?>{
    "messageId": this.messageId,
  };
}

CloudOperationRequestPayload encodeNotificationNotificationAckAppMessageGeneratedRequest(AckAppMessageCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeNotificationNotificationGetAppMessageGeneratedRequest(GetAppMessageQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "messageId": request.messageId,
    },
  );
}

CloudOperationRequestPayload encodeNotificationNotificationGetAppMessageUnreadCountGeneratedRequest(GetAppMessageUnreadCountQuery request) {
  return CloudOperationRequestPayload(
  );
}

CloudOperationRequestPayload encodeNotificationNotificationListAppMessagesGeneratedRequest(ListAppMessagesQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      if (request.messageType != null) "type": request.messageType!,
      if (request.read != null) "read": (request.read!).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      "limit": (request.limit).toString(),
    },
  );
}

CloudOperationRequestPayload encodeNotificationNotificationReadAppMessageGeneratedRequest(ReadAppMessageCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "messageId": request.messageId,
    },
  );
}

