// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: 760018c440e6f9fffff8b9f820e51930beaa94f2f093aff318150ff084655467

library;

import '../operation_request_payload.dart';

part '../generated/requests/notification/notification_operation_contracts.g.requests.g.dart';

enum AppMessageGatheringInvitationAction {
  accept("accept"),
  decline("decline");

  const AppMessageGatheringInvitationAction(this.wireName);

  final String wireName;

  static AppMessageGatheringInvitationAction fromWire(Object? value, String path) {
    return switch (value) {
      "accept" => AppMessageGatheringInvitationAction.accept,
      "decline" => AppMessageGatheringInvitationAction.decline,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum AppMessageGatheringInvitationStatus {
  pending("pending"),
  accepted("accepted"),
  declined("declined"),
  revoked("revoked"),
  cancelled("cancelled"),
  expired("expired");

  const AppMessageGatheringInvitationStatus(this.wireName);

  final String wireName;

  static AppMessageGatheringInvitationStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => AppMessageGatheringInvitationStatus.pending,
      "accepted" => AppMessageGatheringInvitationStatus.accepted,
      "declined" => AppMessageGatheringInvitationStatus.declined,
      "revoked" => AppMessageGatheringInvitationStatus.revoked,
      "cancelled" => AppMessageGatheringInvitationStatus.cancelled,
      "expired" => AppMessageGatheringInvitationStatus.expired,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

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
    this.gatheringInvitation,
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
  final AppMessageGatheringInvitation? gatheringInvitation;
  final bool read;
  final DateTime createdAt;
  final DateTime? deliveredAt;
  final DateTime? ackedAt;
  final DateTime? readAt;

  factory AppMessage.fromWire(Map<String, Object?> map, [String path = "AppMessage"]) {
    _rejectUnknownFields(map, const <String>{"messageId", "userId", "messageType", "source", "sourceId", "destination", "title", "summary", "target", "gatheringInvitation", "read", "createdAt", "deliveredAt", "ackedAt", "readAt"}, path);
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
      gatheringInvitation: map["gatheringInvitation"] == null ? null : AppMessageGatheringInvitation.fromWire(_requiredObject(map["gatheringInvitation"], '$path.gatheringInvitation'), '$path.gatheringInvitation'),
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
    if (gatheringInvitation != null) "gatheringInvitation": gatheringInvitation!.toWire(),
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

final class AppMessageGatheringInvitation {
  const AppMessageGatheringInvitation({
    required this.gatheringId,
    required this.inviterPersonaId,
    required this.recipientPersonaId,
    required this.purposeSummary,
    required this.schedule,
    required this.place,
    required this.participationVersion,
    required this.status,
    required this.actionIntents,
    this.expiresAt,
  });

  final String gatheringId;
  final String inviterPersonaId;
  final String recipientPersonaId;
  final String purposeSummary;
  final AppMessageGatheringInvitationSchedule schedule;
  final AppMessageGatheringInvitationPlace place;
  final int participationVersion;
  final AppMessageGatheringInvitationStatus status;
  final List<AppMessageGatheringInvitationActionIntent> actionIntents;
  final DateTime? expiresAt;

  factory AppMessageGatheringInvitation.fromWire(Map<String, Object?> map, [String path = "AppMessageGatheringInvitation"]) {
    _rejectUnknownFields(map, const <String>{"gatheringId", "inviterPersonaId", "recipientPersonaId", "purposeSummary", "schedule", "place", "participationVersion", "status", "actionIntents", "expiresAt"}, path);
    return AppMessageGatheringInvitation(
      gatheringId: _requiredString(map["gatheringId"], '$path.gatheringId'),
      inviterPersonaId: _requiredString(map["inviterPersonaId"], '$path.inviterPersonaId'),
      recipientPersonaId: _requiredString(map["recipientPersonaId"], '$path.recipientPersonaId'),
      purposeSummary: _requiredString(map["purposeSummary"], '$path.purposeSummary'),
      schedule: AppMessageGatheringInvitationSchedule.fromWire(_requiredObject(map["schedule"], '$path.schedule'), '$path.schedule'),
      place: AppMessageGatheringInvitationPlace.fromWire(_requiredObject(map["place"], '$path.place'), '$path.place'),
      participationVersion: _requiredInt(map["participationVersion"], '$path.participationVersion'),
      status: AppMessageGatheringInvitationStatus.fromWire(map["status"], '$path.status'),
      actionIntents: List<AppMessageGatheringInvitationActionIntent>.unmodifiable(_requiredBoundedList(map["actionIntents"], '$path.actionIntents', max: 2).asMap().entries.map((entry) => AppMessageGatheringInvitationActionIntent.fromWire(_requiredObject(entry.value, '$path.actionIntents' + '[${entry.key}]'), '$path.actionIntents' + '[${entry.key}]'))),
      expiresAt: map["expiresAt"] == null ? null : _requiredTimestamp(map["expiresAt"], '$path.expiresAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "gatheringId": gatheringId,
    "inviterPersonaId": inviterPersonaId,
    "recipientPersonaId": recipientPersonaId,
    "purposeSummary": purposeSummary,
    "schedule": schedule.toWire(),
    "place": place.toWire(),
    "participationVersion": participationVersion,
    "status": status.wireName,
    "actionIntents": actionIntents.map((value) => value.toWire()).toList(growable: false),
    if (expiresAt != null) "expiresAt": expiresAt!.toUtc().toIso8601String(),
  };
}

final class AppMessageGatheringInvitationActionIntent {
  const AppMessageGatheringInvitationActionIntent({
    required this.action,
    required this.expectedGatheringVersion,
    required this.expectedParticipationVersion,
  });

  final AppMessageGatheringInvitationAction action;
  final int expectedGatheringVersion;
  final int expectedParticipationVersion;

  factory AppMessageGatheringInvitationActionIntent.fromWire(Map<String, Object?> map, [String path = "AppMessageGatheringInvitationActionIntent"]) {
    _rejectUnknownFields(map, const <String>{"action", "expectedGatheringVersion", "expectedParticipationVersion"}, path);
    return AppMessageGatheringInvitationActionIntent(
      action: AppMessageGatheringInvitationAction.fromWire(map["action"], '$path.action'),
      expectedGatheringVersion: _requiredInt(map["expectedGatheringVersion"], '$path.expectedGatheringVersion'),
      expectedParticipationVersion: _requiredInt(map["expectedParticipationVersion"], '$path.expectedParticipationVersion'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "action": action.wireName,
    "expectedGatheringVersion": expectedGatheringVersion,
    "expectedParticipationVersion": expectedParticipationVersion,
  };
}

final class AppMessageGatheringInvitationPlace {
  const AppMessageGatheringInvitationPlace({
    required this.mode,
    this.coarsePlaceLabel,
    this.exactMeetingPoint,
  });

  final String mode;
  final String? coarsePlaceLabel;
  final String? exactMeetingPoint;

  factory AppMessageGatheringInvitationPlace.fromWire(Map<String, Object?> map, [String path = "AppMessageGatheringInvitationPlace"]) {
    _rejectUnknownFields(map, const <String>{"mode", "coarsePlaceLabel", "exactMeetingPoint"}, path);
    return AppMessageGatheringInvitationPlace(
      mode: _requiredString(map["mode"], '$path.mode'),
      coarsePlaceLabel: map["coarsePlaceLabel"] == null ? null : _requiredString(map["coarsePlaceLabel"], '$path.coarsePlaceLabel'),
      exactMeetingPoint: map["exactMeetingPoint"] == null ? null : _requiredString(map["exactMeetingPoint"], '$path.exactMeetingPoint'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "mode": mode,
    if (coarsePlaceLabel != null) "coarsePlaceLabel": coarsePlaceLabel!,
    if (exactMeetingPoint != null) "exactMeetingPoint": exactMeetingPoint!,
  };
}

final class AppMessageGatheringInvitationSchedule {
  const AppMessageGatheringInvitationSchedule({
    required this.timezone,
    this.startAt,
    this.endAt,
    this.dateLabel,
  });

  final String timezone;
  final DateTime? startAt;
  final DateTime? endAt;
  final String? dateLabel;

  factory AppMessageGatheringInvitationSchedule.fromWire(Map<String, Object?> map, [String path = "AppMessageGatheringInvitationSchedule"]) {
    _rejectUnknownFields(map, const <String>{"timezone", "startAt", "endAt", "dateLabel"}, path);
    return AppMessageGatheringInvitationSchedule(
      timezone: _requiredString(map["timezone"], '$path.timezone'),
      startAt: map["startAt"] == null ? null : _requiredTimestamp(map["startAt"], '$path.startAt'),
      endAt: map["endAt"] == null ? null : _requiredTimestamp(map["endAt"], '$path.endAt'),
      dateLabel: map["dateLabel"] == null ? null : _requiredString(map["dateLabel"], '$path.dateLabel'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "timezone": timezone,
    if (startAt != null) "startAt": startAt!.toUtc().toIso8601String(),
    if (endAt != null) "endAt": endAt!.toUtc().toIso8601String(),
    if (dateLabel != null) "dateLabel": dateLabel!,
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

List<Object?> _requiredBoundedList(
  Object? value,
  String path, {
  required int max,
}) {
  final result = _requiredList(value, path);
  if (result.length > max) {
    throw FormatException('$path must not contain more than $max items');
  }
  return result;
}
