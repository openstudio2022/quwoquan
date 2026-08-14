// Code generated from canonical domain contracts. DO NOT EDIT.
// ContractGraph SHA256: ae0fd0a3a81ca25ad321276e82c2668626920098032d6fa00232e4637c87fa28

library;

import '../operation_request_payload.dart';

part '../generated/requests/rtc/rtc_operation_contracts.g.requests.g.dart';

enum CallInviteStatus {
  pending("pending"),
  ringing("ringing"),
  accepted("accepted"),
  declined("declined"),
  expired("expired"),
  cancelled("cancelled");

  const CallInviteStatus(this.wireName);

  final String wireName;

  static CallInviteStatus fromWire(Object? value, String path) {
    return switch (value) {
      "pending" => CallInviteStatus.pending,
      "ringing" => CallInviteStatus.ringing,
      "accepted" => CallInviteStatus.accepted,
      "declined" => CallInviteStatus.declined,
      "expired" => CallInviteStatus.expired,
      "cancelled" => CallInviteStatus.cancelled,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CallStatus {
  initiated("initiated"),
  ringing("ringing"),
  connecting("connecting"),
  inCall("in_call"),
  ended("ended");

  const CallStatus(this.wireName);

  final String wireName;

  static CallStatus fromWire(Object? value, String path) {
    return switch (value) {
      "initiated" => CallStatus.initiated,
      "ringing" => CallStatus.ringing,
      "connecting" => CallStatus.connecting,
      "in_call" => CallStatus.inCall,
      "ended" => CallStatus.ended,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum CallType {
  audio("audio"),
  video("video");

  const CallType(this.wireName);

  final String wireName;

  static CallType fromWire(Object? value, String path) {
    return switch (value) {
      "audio" => CallType.audio,
      "video" => CallType.video,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum EndReason {
  normal("normal"),
  cancelled("cancelled"),
  rejected("rejected"),
  noAnswer("no_answer"),
  error("error"),
  timeout("timeout"),
  lastLeave("last_leave"),
  accountClosed("account_closed"),
  accountSuspended("account_suspended");

  const EndReason(this.wireName);

  final String wireName;

  static EndReason fromWire(Object? value, String path) {
    return switch (value) {
      "normal" => EndReason.normal,
      "cancelled" => EndReason.cancelled,
      "rejected" => EndReason.rejected,
      "no_answer" => EndReason.noAnswer,
      "error" => EndReason.error,
      "timeout" => EndReason.timeout,
      "last_leave" => EndReason.lastLeave,
      "account_closed" => EndReason.accountClosed,
      "account_suspended" => EndReason.accountSuspended,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ParticipantRole {
  initiator("initiator"),
  invitee("invitee");

  const ParticipantRole(this.wireName);

  final String wireName;

  static ParticipantRole fromWire(Object? value, String path) {
    return switch (value) {
      "initiator" => ParticipantRole.initiator,
      "invitee" => ParticipantRole.invitee,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

enum ParticipantStatus {
  invited("invited"),
  ringing("ringing"),
  connecting("connecting"),
  connected("connected"),
  left("left"),
  timeout("timeout");

  const ParticipantStatus(this.wireName);

  final String wireName;

  static ParticipantStatus fromWire(Object? value, String path) {
    return switch (value) {
      "invited" => ParticipantStatus.invited,
      "ringing" => ParticipantStatus.ringing,
      "connecting" => ParticipantStatus.connecting,
      "connected" => ParticipantStatus.connected,
      "left" => ParticipantStatus.left,
      "timeout" => ParticipantStatus.timeout,
      _ => throw FormatException('$path has an invalid enum value'),
    };
  }
}

final class CallParticipant {
  const CallParticipant({
    required this.userId,
    required this.role,
    required this.status,
    required this.isMuted,
    required this.isCameraOn,
    this.joinedAt,
    this.leftAt,
    this.inviteStatus,
    this.invitedBy,
  });

  final String userId;
  final ParticipantRole role;
  final ParticipantStatus status;
  final bool isMuted;
  final bool isCameraOn;
  final DateTime? joinedAt;
  final DateTime? leftAt;
  final CallInviteStatus? inviteStatus;
  final String? invitedBy;

  factory CallParticipant.fromWire(Map<String, Object?> map, [String path = "CallParticipant"]) {
    _rejectUnknownFields(map, const <String>{"userId", "role", "status", "isMuted", "isCameraOn", "joinedAt", "leftAt", "inviteStatus", "invitedBy"}, path);
    return CallParticipant(
      userId: _requiredString(map["userId"], '$path.userId'),
      role: ParticipantRole.fromWire(map["role"], '$path.role'),
      status: ParticipantStatus.fromWire(map["status"], '$path.status'),
      isMuted: _requiredBool(map["isMuted"], '$path.isMuted'),
      isCameraOn: _requiredBool(map["isCameraOn"], '$path.isCameraOn'),
      joinedAt: map["joinedAt"] == null ? null : _requiredTimestamp(map["joinedAt"], '$path.joinedAt'),
      leftAt: map["leftAt"] == null ? null : _requiredTimestamp(map["leftAt"], '$path.leftAt'),
      inviteStatus: map["inviteStatus"] == null ? null : CallInviteStatus.fromWire(map["inviteStatus"], '$path.inviteStatus'),
      invitedBy: map["invitedBy"] == null ? null : _requiredString(map["invitedBy"], '$path.invitedBy'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "userId": userId,
    "role": role.wireName,
    "status": status.wireName,
    "isMuted": isMuted,
    "isCameraOn": isCameraOn,
    if (joinedAt != null) "joinedAt": joinedAt!.toUtc().toIso8601String(),
    if (leftAt != null) "leftAt": leftAt!.toUtc().toIso8601String(),
    if (inviteStatus != null) "inviteStatus": inviteStatus!.wireName,
    if (invitedBy != null) "invitedBy": invitedBy!,
  };
}

final class CallSession {
  const CallSession({
    required this.id,
    required this.callType,
    required this.status,
    required this.initiatorId,
    this.initiatorRingtoneId,
    this.conversationId,
    this.circleId,
    required this.roomId,
    required this.maxParticipants,
    required this.participantCount,
    this.participants,
    required this.isScreenSharing,
    this.screenShareUserId,
    this.endReason,
    this.durationMs,
    this.startedAt,
    this.endedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String id;
  final CallType callType;
  final CallStatus status;
  final String initiatorId;
  final String? initiatorRingtoneId;
  final String? conversationId;
  final String? circleId;
  final String roomId;
  final int maxParticipants;
  final int participantCount;
  final List<CallParticipant>? participants;
  final bool isScreenSharing;
  final String? screenShareUserId;
  final EndReason? endReason;
  final int? durationMs;
  final DateTime? startedAt;
  final DateTime? endedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CallSession.fromWire(Map<String, Object?> map, [String path = "CallSession"]) {
    _rejectUnknownFields(map, const <String>{"id", "callType", "status", "initiatorId", "initiatorRingtoneId", "conversationId", "circleId", "roomId", "maxParticipants", "participantCount", "participants", "isScreenSharing", "screenShareUserId", "endReason", "durationMs", "startedAt", "endedAt", "createdAt", "updatedAt"}, path);
    return CallSession(
      id: _requiredString(map["id"], '$path.id'),
      callType: CallType.fromWire(map["callType"], '$path.callType'),
      status: CallStatus.fromWire(map["status"], '$path.status'),
      initiatorId: _requiredString(map["initiatorId"], '$path.initiatorId'),
      initiatorRingtoneId: map["initiatorRingtoneId"] == null ? null : _requiredString(map["initiatorRingtoneId"], '$path.initiatorRingtoneId'),
      conversationId: map["conversationId"] == null ? null : _requiredString(map["conversationId"], '$path.conversationId'),
      circleId: map["circleId"] == null ? null : _requiredString(map["circleId"], '$path.circleId'),
      roomId: _requiredString(map["roomId"], '$path.roomId'),
      maxParticipants: _requiredInt(map["maxParticipants"], '$path.maxParticipants'),
      participantCount: _requiredInt(map["participantCount"], '$path.participantCount'),
      participants: map["participants"] == null ? null : List<CallParticipant>.unmodifiable(_requiredList(map["participants"], '$path.participants').asMap().entries.map((entry) => CallParticipant.fromWire(_requiredObject(entry.value, '$path.participants' + '[${entry.key}]'), '$path.participants' + '[${entry.key}]'))),
      isScreenSharing: _requiredBool(map["isScreenSharing"], '$path.isScreenSharing'),
      screenShareUserId: map["screenShareUserId"] == null ? null : _requiredString(map["screenShareUserId"], '$path.screenShareUserId'),
      endReason: map["endReason"] == null ? null : EndReason.fromWire(map["endReason"], '$path.endReason'),
      durationMs: map["durationMs"] == null ? null : _requiredInt(map["durationMs"], '$path.durationMs'),
      startedAt: map["startedAt"] == null ? null : _requiredTimestamp(map["startedAt"], '$path.startedAt'),
      endedAt: map["endedAt"] == null ? null : _requiredTimestamp(map["endedAt"], '$path.endedAt'),
      createdAt: _requiredTimestamp(map["createdAt"], '$path.createdAt'),
      updatedAt: _requiredTimestamp(map["updatedAt"], '$path.updatedAt'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "id": id,
    "callType": callType.wireName,
    "status": status.wireName,
    "initiatorId": initiatorId,
    if (initiatorRingtoneId != null) "initiatorRingtoneId": initiatorRingtoneId!,
    if (conversationId != null) "conversationId": conversationId!,
    if (circleId != null) "circleId": circleId!,
    "roomId": roomId,
    "maxParticipants": maxParticipants,
    "participantCount": participantCount,
    if (participants != null) "participants": participants!.map((value) => value.toWire()).toList(growable: false),
    "isScreenSharing": isScreenSharing,
    if (screenShareUserId != null) "screenShareUserId": screenShareUserId!,
    if (endReason != null) "endReason": endReason!.wireName,
    if (durationMs != null) "durationMs": durationMs!,
    if (startedAt != null) "startedAt": startedAt!.toUtc().toIso8601String(),
    if (endedAt != null) "endedAt": endedAt!.toUtc().toIso8601String(),
    "createdAt": createdAt.toUtc().toIso8601String(),
    "updatedAt": updatedAt.toUtc().toIso8601String(),
  };
}

final class RtcAnswerCallResult {
  const RtcAnswerCallResult({
    required this.session,
    required this.mediaAccess,
  });

  final CallSession session;
  final RtcMediaSessionAccess mediaAccess;

  factory RtcAnswerCallResult.fromWire(Map<String, Object?> map, [String path = "RtcAnswerCallResult"]) {
    _rejectUnknownFields(map, const <String>{"session", "mediaAccess"}, path);
    return RtcAnswerCallResult(
      session: CallSession.fromWire(_requiredObject(map["session"], '$path.session'), '$path.session'),
      mediaAccess: RtcMediaSessionAccess.fromWire(_requiredObject(map["mediaAccess"], '$path.mediaAccess'), '$path.mediaAccess'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "session": session.toWire(),
    "mediaAccess": mediaAccess.toWire(),
  };
}

final class RtcCallHistoryPage {
  const RtcCallHistoryPage({
    required this.items,
    this.nextCursor,
  });

  final List<CallSession> items;
  final String? nextCursor;

  factory RtcCallHistoryPage.fromWire(Map<String, Object?> map, [String path = "RtcCallHistoryPage"]) {
    _rejectUnknownFields(map, const <String>{"items", "nextCursor"}, path);
    return RtcCallHistoryPage(
      items: List<CallSession>.unmodifiable(_requiredList(map["items"], '$path.items').asMap().entries.map((entry) => CallSession.fromWire(_requiredObject(entry.value, '$path.items' + '[${entry.key}]'), '$path.items' + '[${entry.key}]'))),
      nextCursor: map["nextCursor"] == null ? null : _requiredString(map["nextCursor"], '$path.nextCursor'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "items": items.map((value) => value.toWire()).toList(growable: false),
    if (nextCursor != null) "nextCursor": nextCursor!,
  };
}

final class RtcInitiateCallResult {
  const RtcInitiateCallResult({
    required this.session,
    required this.mediaAccess,
  });

  final CallSession session;
  final RtcMediaSessionAccess mediaAccess;

  factory RtcInitiateCallResult.fromWire(Map<String, Object?> map, [String path = "RtcInitiateCallResult"]) {
    _rejectUnknownFields(map, const <String>{"session", "mediaAccess"}, path);
    return RtcInitiateCallResult(
      session: CallSession.fromWire(_requiredObject(map["session"], '$path.session'), '$path.session'),
      mediaAccess: RtcMediaSessionAccess.fromWire(_requiredObject(map["mediaAccess"], '$path.mediaAccess'), '$path.mediaAccess'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "session": session.toWire(),
    "mediaAccess": mediaAccess.toWire(),
  };
}

final class RtcJoinCredentials {
  const RtcJoinCredentials({
    required this.session,
    required this.mediaAccess,
  });

  final CallSession session;
  final RtcMediaSessionAccess mediaAccess;

  factory RtcJoinCredentials.fromWire(Map<String, Object?> map, [String path = "RtcJoinCredentials"]) {
    _rejectUnknownFields(map, const <String>{"session", "mediaAccess"}, path);
    return RtcJoinCredentials(
      session: CallSession.fromWire(_requiredObject(map["session"], '$path.session'), '$path.session'),
      mediaAccess: RtcMediaSessionAccess.fromWire(_requiredObject(map["mediaAccess"], '$path.mediaAccess'), '$path.mediaAccess'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "session": session.toWire(),
    "mediaAccess": mediaAccess.toWire(),
  };
}

final class RtcMediaSessionAccess {
  const RtcMediaSessionAccess({
    required this.accessToken,
  });

  final String accessToken;

  factory RtcMediaSessionAccess.fromWire(Map<String, Object?> map, [String path = "RtcMediaSessionAccess"]) {
    _rejectUnknownFields(map, const <String>{"accessToken"}, path);
    return RtcMediaSessionAccess(
      accessToken: _requiredNonBlankString(map["accessToken"], '$path.accessToken'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "accessToken": accessToken,
  };
}

CallSession decodeCallSession(Object? response) =>
    CallSession.fromWire(_requiredObject(response, "CallSession"), "CallSession");

RtcAnswerCallResult decodeRtcAnswerCallResult(Object? response) =>
    RtcAnswerCallResult.fromWire(_requiredObject(response, "RtcAnswerCallResult"), "RtcAnswerCallResult");

RtcCallHistoryPage decodeRtcCallHistoryPage(Object? response) =>
    RtcCallHistoryPage.fromWire(_requiredObject(response, "RtcCallHistoryPage"), "RtcCallHistoryPage");

RtcInitiateCallResult decodeRtcInitiateCallResult(Object? response) =>
    RtcInitiateCallResult.fromWire(_requiredObject(response, "RtcInitiateCallResult"), "RtcInitiateCallResult");

RtcJoinCredentials decodeRtcJoinCredentials(Object? response) =>
    RtcJoinCredentials.fromWire(_requiredObject(response, "RtcJoinCredentials"), "RtcJoinCredentials");

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
