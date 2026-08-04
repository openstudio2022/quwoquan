// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 93359367b8614f01bb5e1c51e37af383332b01f117cc1c6cf39e4fdf838e49d2

library;

import '../operation_request_payload.dart';

part '../generated/requests/notification/notification_operation_contracts.g.requests.g.dart';

enum NotificationType {
  social("social"),
  content("content"),
  circle("circle"),
  system("system"),
  assistant("assistant");

  const NotificationType(this.wireName);

  final String wireName;

  static NotificationType fromWire(Object? value, String path) {
    return switch (value) {
      "social" => NotificationType.social,
      "content" => NotificationType.content,
      "circle" => NotificationType.circle,
      "system" => NotificationType.system,
      "assistant" => NotificationType.assistant,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class AckIncomingCallPresentationResult {
  const AckIncomingCallPresentationResult({
    required this.deliveryKey,
    required this.deviceId,
    required this.status,
    required this.raced,
    required this.acknowledgedAt,
  });

  final String deliveryKey;
  final String deviceId;
  final String status;
  final bool raced;
  final DateTime acknowledgedAt;

  factory AckIncomingCallPresentationResult.fromWire(Map<String, Object?> map, [String path = "AckIncomingCallPresentationResult"]) {
    _rejectUnknownFields(map, const <String>{"deliveryKey", "deviceId", "status", "raced", "acknowledgedAt"}, path);
    return AckIncomingCallPresentationResult(
      deliveryKey: _requiredNonBlankString(map["deliveryKey"], '$path.deliveryKey'),
      deviceId: _requiredNonBlankString(map["deviceId"], '$path.deviceId'),
      status: _requiredNonBlankString(map["status"], '$path.status'),
      raced: _requiredBool(map["raced"], '$path.raced'),
      acknowledgedAt: _requiredTimestamp(map["acknowledgedAt"], '$path.acknowledgedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "deliveryKey": deliveryKey,
    "deviceId": deviceId,
    "status": status,
    "raced": raced,
    "acknowledgedAt": acknowledgedAt.toUtc().toIso8601String(),
  };
}

final class AppMessage {
  const AppMessage({
    required this.messageId,
    required this.userId,
    required this.messageType,
    required this.source,
    required this.sourceId,
    required this.destination,
    required this.title,
    required this.summary,
    required this.target,
    required this.read,
    required this.createdAt,
    this.deliveredAt,
    this.ackedAt,
    this.readAt,
  });

  final String messageId;
  final String userId;
  final NotificationType messageType;
  final String source;
  final String sourceId;
  final AppMessageDestination destination;
  final String title;
  final String summary;
  final AppMessageTarget target;
  final bool read;
  final DateTime createdAt;
  final DateTime? deliveredAt;
  final DateTime? ackedAt;
  final DateTime? readAt;

  factory AppMessage.fromWire(Map<String, Object?> map, [String path = "AppMessage"]) {
    _rejectUnknownFields(map, const <String>{"messageId", "userId", "messageType", "source", "sourceId", "destination", "title", "summary", "target", "read", "createdAt", "deliveredAt", "ackedAt", "readAt"}, path);
    return AppMessage(
      messageId: _requiredNonBlankString(map["messageId"], '$path.messageId'),
      userId: _requiredNonBlankString(map["userId"], '$path.userId'),
      messageType: NotificationType.fromWire(map["messageType"], '$path.messageType'),
      source: _requiredNonBlankString(map["source"], '$path.source'),
      sourceId: _requiredNonBlankString(map["sourceId"], '$path.sourceId'),
      destination: AppMessageDestination.fromWire(_requiredObject(map["destination"], '$path.destination'), '$path.destination'),
      title: _requiredNonBlankString(map["title"], '$path.title'),
      summary: _requiredNonBlankString(map["summary"], '$path.summary'),
      target: AppMessageTarget.fromWire(_requiredObject(map["target"], '$path.target'), '$path.target'),
      read: _requiredBool(map["read"], '$path.read'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      deliveredAt: map["deliveredAt"] == null ? null : _requiredTimestamp(map["deliveredAt"], '$path.deliveredAt'),
      ackedAt: map["ackedAt"] == null ? null : _requiredTimestamp(map["ackedAt"], '$path.ackedAt'),
      readAt: map["readAt"] == null ? null : _requiredTimestamp(map["readAt"], '$path.readAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "messageId": messageId,
    "userId": userId,
    "messageType": messageType.wireName,
    "source": source,
    "sourceId": sourceId,
    "destination": destination.toWire(),
    "title": title,
    "summary": summary,
    "target": target.toWire(),
    "read": read,
    "createdAt": createdAt.toUtc().toIso8601String(),
    if (deliveredAt != null) "deliveredAt": deliveredAt!.toUtc().toIso8601String(),
    if (ackedAt != null) "ackedAt": ackedAt!.toUtc().toIso8601String(),
    if (readAt != null) "readAt": readAt!.toUtc().toIso8601String(),
  };
}

final class AppMessageDestination {
  const AppMessageDestination({
    required this.type,
    required this.id,
  });

  final String type;
  final String id;

  factory AppMessageDestination.fromWire(Map<String, Object?> map, [String path = "AppMessageDestination"]) {
    _rejectUnknownFields(map, const <String>{"type", "id"}, path);
    return AppMessageDestination(
      type: _requiredString(map["type"], '$path.type'),
      id: _requiredString(map["id"], '$path.id'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "type": type,
    "id": id,
  };
}

final class AppMessageInboxSlice {
  const AppMessageInboxSlice({
    required this.items,
    this.nextCursor,
  });

  final List<AppMessage> items;
  final String? nextCursor;

  factory AppMessageInboxSlice.fromWire(Map<String, Object?> map, [String path = "AppMessageInboxSlice"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return AppMessageInboxSlice(
      items: List<AppMessage>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => AppMessage.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class AppMessageRouteQuery {
  const AppMessageRouteQuery({
    this.dimension,
  });

  final String? dimension;

  factory AppMessageRouteQuery.fromWire(Map<String, Object?> map, [String path = "AppMessageRouteQuery"]) {
    _rejectUnknownFields(map, const <String>{"dimension"}, path);
    return AppMessageRouteQuery(
      dimension: map["dimension"] == null ? null : _requiredString(map["dimension"], '$path.dimension'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (dimension != null) "dimension": dimension!,
  };
}

final class AppMessageTarget {
  const AppMessageTarget({
    required this.targetType,
    required this.targetId,
    this.routeId,
    this.routePath,
    required this.query,
  });

  final String targetType;
  final String targetId;
  final String? routeId;
  final String? routePath;
  final AppMessageRouteQuery query;

  factory AppMessageTarget.fromWire(Map<String, Object?> map, [String path = "AppMessageTarget"]) {
    _rejectUnknownFields(map, const <String>{"targetType", "targetId", "routeId", "routePath", "query"}, path);
    return AppMessageTarget(
      targetType: _requiredString(map["targetType"], '$path.targetType'),
      targetId: _requiredString(map["targetId"], '$path.targetId'),
      routeId: map["routeId"] == null ? null : _requiredString(map["routeId"], '$path.routeId'),
      routePath: map["routePath"] == null ? null : _requiredString(map["routePath"], '$path.routePath'),
      query: AppMessageRouteQuery.fromWire(_requiredObject(map["query"], '$path.query'), '$path.query'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "targetType": targetType,
    "targetId": targetId,
    if (routeId != null) "routeId": routeId!,
    if (routePath != null) "routePath": routePath!,
    "query": query.toWire(),
  };
}

final class AppMessageUnreadCountSlice {
  const AppMessageUnreadCountSlice({
    required this.unreadCount,
  });

  final int unreadCount;

  factory AppMessageUnreadCountSlice.fromWire(Map<String, Object?> map, [String path = "AppMessageUnreadCountSlice"]) {
    _rejectUnknownFields(map, const <String>{"unreadCount"}, path);
    return AppMessageUnreadCountSlice(
      unreadCount: _requiredNonNegativeInt(map["unreadCount"], '$path.unreadCount'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "unreadCount": unreadCount,
  };
}

AckIncomingCallPresentationResult decodeAckIncomingCallPresentationResult(Object? response) =>
    AckIncomingCallPresentationResult.fromWire(_requiredObject(response, "AckIncomingCallPresentationResult"), "AckIncomingCallPresentationResult");

AppMessage decodeAppMessage(Object? response) =>
    AppMessage.fromWire(_requiredObject(response, "AppMessage"), "AppMessage");

AppMessageInboxSlice decodeAppMessageInboxSlice(Object? response) =>
    AppMessageInboxSlice.fromWire(_requiredObject(response, "AppMessageInboxSlice"), "AppMessageInboxSlice");

AppMessageUnreadCountSlice decodeAppMessageUnreadCountSlice(Object? response) =>
    AppMessageUnreadCountSlice.fromWire(_requiredObject(response, "AppMessageUnreadCountSlice"), "AppMessageUnreadCountSlice");

Map<String, Object?> _requiredObject(Object? value, String path) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$path must be an object');
  }
  final result = <String, Object?>{};
  for (final entry in value.entries) {
    final key = entry.key;
    if (key is! String) {
      throw FormatException('$path contains a non-string field name');
    }
    result[key] = entry.value;
  }
  return result;
}

void _rejectUnknownFields(
  Map<String, Object?> value,
  Set<String> allowed,
  String path,
) {
  final unknown = value.keys.where((key) => !allowed.contains(key)).toList()
    ..sort();
  if (unknown.isNotEmpty) {
    throw FormatException('$path contains unknown fields: ${unknown.join(', ')}');
  }
}

String _requiredString(Object? value, String path) {
  if (value is! String) throw FormatException('$path must be a string');
  return value;
}

String _requiredNonBlankString(Object? value, String path) {
  final result = _requiredString(value, path);
  if (result.trim().isEmpty) {
    throw FormatException('$path must not be blank');
  }
  return result;
}

DateTime _requiredTimestamp(Object? value, String path) {
  final result = _requiredString(value, path);
  final parsed = DateTime.tryParse(result);
  if (parsed == null) {
    throw FormatException('$path must be an ISO-8601 timestamp');
  }
  return parsed;
}

int _requiredInt(Object? value, String path) {
  if (value is! int) throw FormatException('$path must be an int');
  return value;
}

int _requiredNonNegativeInt(Object? value, String path) {
  final result = _requiredInt(value, path);
  if (result < 0) {
    throw FormatException('$path must not be negative');
  }
  return result;
}

bool _requiredBool(Object? value, String path) {
  if (value is! bool) throw FormatException('$path must be a bool');
  return value;
}

List<Object?> _requiredList(Object? value, String path) {
  if (value is! List<Object?>) {
    throw FormatException('$path must be a list');
  }
  return value;
}
