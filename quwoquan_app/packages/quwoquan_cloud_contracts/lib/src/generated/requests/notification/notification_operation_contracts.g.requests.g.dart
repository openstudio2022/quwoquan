// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 8eb58b30af5b0a68a46189c1cdf634d15ae49e2fe4b048af1dc35656eb8a48b9

part of '../../../notification/notification_operation_contracts.g.dart';


void _generatedRequestRejectUnknownFields(
  Map<String, Object?> map,
  Set<String> allowed,
  String path,
) {
  for (final key in map.keys) {
    if (!allowed.contains(key)) {
      throw FormatException('$path contains unknown field $key');
    }
  }
}


String _generatedRequestString(Object? value, String path) {
  if (value is String) return value;
  throw FormatException('$path must be a string');
}


int _generatedRequestInt(Object? value, String path) {
  if (value is int) return value;
  throw FormatException('$path must be an integer');
}


bool _generatedRequestBool(Object? value, String path) {
  if (value is bool) return value;
  throw FormatException('$path must be a boolean');
}

final class AckAppMessageCommand {
  const AckAppMessageCommand({
    required String messageId,
  }) : messageId = messageId;

  final String messageId;

  factory AckAppMessageCommand.fromWire(Map<String, Object?> map, [String path = "AckAppMessageCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"messageId"}, path);
    return AckAppMessageCommand(
      messageId: _generatedRequestString(map["messageId"], '$path.messageId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messageId": this.messageId,
  };
}

final class AckIncomingCallPresentationCommand {
  AckIncomingCallPresentationCommand({
    required String deliveryKey,
  }) : deliveryKey = deliveryKey.trim() {
    if (this.deliveryKey.isEmpty) {
      throw ArgumentError.value(this.deliveryKey, "deliveryKey", 'must not be blank');
    }
  }

  final String deliveryKey;

  factory AckIncomingCallPresentationCommand.fromWire(Map<String, Object?> map, [String path = "AckIncomingCallPresentationCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"deliveryKey"}, path);
    return AckIncomingCallPresentationCommand(
      deliveryKey: _generatedRequestString(map["deliveryKey"], '$path.deliveryKey'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "deliveryKey": this.deliveryKey,
  };
}

final class GetAppMessageQuery {
  const GetAppMessageQuery({
    required String messageId,
  }) : messageId = messageId;

  final String messageId;

  factory GetAppMessageQuery.fromWire(Map<String, Object?> map, [String path = "GetAppMessageQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"messageId"}, path);
    return GetAppMessageQuery(
      messageId: _generatedRequestString(map["messageId"], '$path.messageId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messageId": this.messageId,
  };
}

final class GetAppMessageUnreadCountQuery {
  const GetAppMessageUnreadCountQuery();
}

final class ListAppMessagesQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  ListAppMessagesQuery({
    String? messageType,
    bool? read,
    String? cursor,
    int limit = 20,
  }) : messageType = messageType,
       read = read,
       cursor = cursor,
       limit = limit {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? messageType;
  final bool? read;
  final String? cursor;
  final int limit;

  factory ListAppMessagesQuery.fromWire(Map<String, Object?> map, [String path = "ListAppMessagesQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"type", "read", "cursor", "limit"}, path);
    return ListAppMessagesQuery(
      messageType: map["type"] == null ? null : _generatedRequestString(map["type"], '$path.type'),
      read: map["read"] == null ? null : _generatedRequestBool(map["read"], '$path.read'),
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
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

  factory ReadAppMessageCommand.fromWire(Map<String, Object?> map, [String path = "ReadAppMessageCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"messageId"}, path);
    return ReadAppMessageCommand(
      messageId: _generatedRequestString(map["messageId"], '$path.messageId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
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

CloudOperationRequestPayload encodeNotificationNotificationDeliveryJobAckIncomingCallPresentationGeneratedRequest(AckIncomingCallPresentationCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "deliveryKey": request.deliveryKey,
    },
  );
}

