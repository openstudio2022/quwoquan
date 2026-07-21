import '../operation_request_payload.dart';

/// RTC CallSession 对象的 pure Dart contracts。
///
/// 真相源：contracts/metadata/rtc/call_session/{fields,service}.yaml。
/// 命令不携带 aggregate version；服务端以内部 CAS、命令回执与 outbox
/// 保证并发安全和幂等。

abstract interface class CallLifecycleCommandWriter {
  Future<RtcInitiateCallResultDto> initiateCall(RtcInitiateCallCommand command);

  Future<RtcAnswerCallResultDto> answerCall(RtcCallIdCommand command);

  Future<CallSessionDto> rejectCall(RtcCallIdCommand command);

  Future<CallSessionDto> cancelCall(RtcCallIdCommand command);

  Future<CallSessionDto> hangupCall(RtcCallIdCommand command);
}

abstract interface class CallParticipantCommandWriter {
  Future<RtcJoinCredentialsDto> joinCall(RtcCallIdCommand command);

  Future<CallSessionDto> leaveCall(RtcCallIdCommand command);

  Future<CallSessionDto> inviteToCall(RtcInviteToCallCommand command);

  /// 端侧首帧媒体连通后上报；≥2 人 connected 时会话进入 in_call。
  Future<CallSessionDto> reportMediaConnected(RtcCallIdCommand command);
}

abstract interface class CallMediaControlWriter {
  Future<CallSessionDto> toggleMute(RtcToggleMuteCommand command);

  Future<CallSessionDto> toggleCamera(RtcToggleCameraCommand command);
}

abstract interface class CallScreenShareWriter {
  Future<CallSessionDto> startScreenShare(RtcCallIdCommand command);

  Future<CallSessionDto> stopScreenShare(RtcCallIdCommand command);
}

abstract interface class CallQuery {
  Future<CallSessionDto> getCall(RtcGetCallQuery query);

  Future<RtcCallHistoryPage> listCalls(RtcListCallsQuery query);
}

final class RtcInitiateCallCommand {
  RtcInitiateCallCommand({
    required String callType,
    required List<String> inviteeIds,
    this.conversationId,
    this.circleId,
    this.maxParticipants = 32,
  }) : callType = _required(callType, 'callType'),
       inviteeIds = List<String>.unmodifiable(
         inviteeIds.map((id) => id.trim()).where((id) => id.isNotEmpty),
       ) {
    if (this.inviteeIds.isEmpty) {
      throw ArgumentError.value(inviteeIds, 'inviteeIds', 'must not be empty');
    }
    if (maxParticipants < 2 || maxParticipants > 32) {
      throw ArgumentError.value(
        maxParticipants,
        'maxParticipants',
        'must be between 2 and 32',
      );
    }
  }

  final String callType;
  final List<String> inviteeIds;
  final String? conversationId;
  final String? circleId;
  final int maxParticipants;
}

CloudOperationRequestPayload encodeRtcInitiateCallCommand(
  RtcInitiateCallCommand command,
) => CloudOperationRequestPayload(
  body: <String, Object?>{
    'callType': command.callType,
    'inviteeIds': command.inviteeIds,
    'conversationId': ?_optional(command.conversationId),
    'circleId': ?_optional(command.circleId),
    'maxParticipants': command.maxParticipants,
  },
);

final class RtcCallIdCommand {
  RtcCallIdCommand({required String callId})
    : callId = _required(callId, 'callId');

  final String callId;
}

CloudOperationRequestPayload encodeRtcCallIdCommand(RtcCallIdCommand command) =>
    CloudOperationRequestPayload(
      pathParameters: <String, String>{'callId': command.callId},
    );

final class RtcInviteToCallCommand {
  RtcInviteToCallCommand({
    required String callId,
    required List<String> inviteeIds,
  }) : callId = _required(callId, 'callId'),
       inviteeIds = List<String>.unmodifiable(
         inviteeIds.map((id) => id.trim()).where((id) => id.isNotEmpty),
       ) {
    if (this.inviteeIds.isEmpty) {
      throw ArgumentError.value(inviteeIds, 'inviteeIds', 'must not be empty');
    }
  }

  final String callId;
  final List<String> inviteeIds;
}

CloudOperationRequestPayload encodeRtcInviteToCallCommand(
  RtcInviteToCallCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'callId': command.callId},
  body: <String, Object?>{'inviteeIds': command.inviteeIds},
);

final class RtcToggleMuteCommand {
  RtcToggleMuteCommand({required String callId, required this.muted})
    : callId = _required(callId, 'callId');

  final String callId;
  final bool muted;
}

CloudOperationRequestPayload encodeRtcToggleMuteCommand(
  RtcToggleMuteCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'callId': command.callId},
  body: <String, Object?>{'muted': command.muted},
);

final class RtcToggleCameraCommand {
  RtcToggleCameraCommand({required String callId, required this.cameraOn})
    : callId = _required(callId, 'callId');

  final String callId;
  final bool cameraOn;
}

CloudOperationRequestPayload encodeRtcToggleCameraCommand(
  RtcToggleCameraCommand command,
) => CloudOperationRequestPayload(
  pathParameters: <String, String>{'callId': command.callId},
  body: <String, Object?>{'cameraOn': command.cameraOn},
);

final class RtcGetCallQuery {
  RtcGetCallQuery({required String callId})
    : callId = _required(callId, 'callId');

  final String callId;
}

CloudOperationRequestPayload encodeRtcGetCallQuery(RtcGetCallQuery query) =>
    CloudOperationRequestPayload(
      pathParameters: <String, String>{'callId': query.callId},
    );

final class RtcListCallsQuery {
  RtcListCallsQuery({
    this.cursor,
    this.limit = 20,
    this.status,
    this.missedOnly = false,
  }) {
    if (limit < 1 || limit > 100) {
      throw ArgumentError.value(limit, 'limit', 'must be between 1 and 100');
    }
  }

  final String? cursor;
  final int limit;
  final String? status;
  final bool missedOnly;
}

CloudOperationRequestPayload encodeRtcListCallsQuery(RtcListCallsQuery query) =>
    CloudOperationRequestPayload(
      queryParameters: <String, String>{
        'limit': '${query.limit}',
        'cursor': ?_optional(query.cursor),
        'status': ?_optional(query.status),
        if (query.missedOnly) 'missed': 'true',
      },
    );

final class CallParticipantDto {
  const CallParticipantDto({
    required this.userId,
    this.role = 'invitee',
    this.status = 'invited',
    this.isMuted = false,
    this.isCameraOn = true,
    this.joinedAt,
    this.leftAt,
    this.inviteStatus,
    this.invitedBy,
  });

  final String userId;
  final String role;
  final String status;
  final bool isMuted;
  final bool isCameraOn;
  final DateTime? joinedAt;
  final DateTime? leftAt;
  final String? inviteStatus;
  final String? invitedBy;

  factory CallParticipantDto.fromMap(Map<Object?, Object?> map) =>
      CallParticipantDto(
        userId: _requiredField(map, 'userId'),
        role: _stringField(map, 'role') ?? 'invitee',
        status: _stringField(map, 'status') ?? 'invited',
        isMuted: _boolField(map, 'isMuted') ?? false,
        isCameraOn: _boolField(map, 'isCameraOn') ?? true,
        joinedAt: _timestampField(map, 'joinedAt'),
        leftAt: _timestampField(map, 'leftAt'),
        inviteStatus: _stringField(map, 'inviteStatus'),
        invitedBy: _stringField(map, 'invitedBy'),
      );

  Map<String, Object?> toMap() => <String, Object?>{
    'userId': userId,
    'role': role,
    'status': status,
    'isMuted': isMuted,
    'isCameraOn': isCameraOn,
    if (joinedAt != null) 'joinedAt': joinedAt!.toUtc().toIso8601String(),
    if (leftAt != null) 'leftAt': leftAt!.toUtc().toIso8601String(),
    if (inviteStatus != null) 'inviteStatus': inviteStatus,
    if (invitedBy != null) 'invitedBy': invitedBy,
  };

  CallParticipantDto copyWith({
    String? userId,
    String? role,
    String? status,
    bool? isMuted,
    bool? isCameraOn,
    DateTime? joinedAt,
    DateTime? leftAt,
    String? inviteStatus,
    String? invitedBy,
  }) => CallParticipantDto(
    userId: userId ?? this.userId,
    role: role ?? this.role,
    status: status ?? this.status,
    isMuted: isMuted ?? this.isMuted,
    isCameraOn: isCameraOn ?? this.isCameraOn,
    joinedAt: joinedAt ?? this.joinedAt,
    leftAt: leftAt ?? this.leftAt,
    inviteStatus: inviteStatus ?? this.inviteStatus,
    invitedBy: invitedBy ?? this.invitedBy,
  );
}

final class CallSessionDto {
  const CallSessionDto({
    required this.callId,
    this.callType = 'audio',
    this.status = 'initiated',
    required this.initiatorId,
    this.initiatorRingtoneId,
    this.conversationId,
    this.circleId,
    required this.roomId,
    this.maxParticipants = 32,
    this.participantCount = 0,
    this.participants = const <CallParticipantDto>[],
    this.isScreenSharing = false,
    this.screenShareUserId,
    this.endReason,
    this.durationMs,
    this.startedAt,
    this.endedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  final String callId;
  final String callType;
  final String status;
  final String initiatorId;
  final String? initiatorRingtoneId;
  final String? conversationId;
  final String? circleId;
  final String roomId;
  final int maxParticipants;
  final int participantCount;
  final List<CallParticipantDto> participants;
  final bool isScreenSharing;
  final String? screenShareUserId;
  final String? endReason;
  final int? durationMs;
  final DateTime? startedAt;
  final DateTime? endedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  factory CallSessionDto.fromMap(Map<Object?, Object?> map) {
    final rawParticipants = map['participants'];
    final participants = <CallParticipantDto>[];
    if (rawParticipants is List<Object?>) {
      for (final raw in rawParticipants) {
        if (raw is Map<Object?, Object?>) {
          participants.add(CallParticipantDto.fromMap(raw));
        }
      }
    }
    return CallSessionDto(
      callId: _requiredField(map, 'callId'),
      callType: _stringField(map, 'callType') ?? 'audio',
      status: _stringField(map, 'status') ?? 'initiated',
      initiatorId: _requiredField(map, 'initiatorId'),
      initiatorRingtoneId: _stringField(map, 'initiatorRingtoneId'),
      conversationId: _stringField(map, 'conversationId'),
      circleId: _stringField(map, 'circleId'),
      roomId: _requiredField(map, 'roomId'),
      maxParticipants: _intField(map, 'maxParticipants') ?? 32,
      participantCount: _intField(map, 'participantCount') ?? 0,
      participants: List<CallParticipantDto>.unmodifiable(participants),
      isScreenSharing: _boolField(map, 'isScreenSharing') ?? false,
      screenShareUserId: _stringField(map, 'screenShareUserId'),
      endReason: _stringField(map, 'endReason'),
      durationMs: _intField(map, 'durationMs'),
      startedAt: _timestampField(map, 'startedAt'),
      endedAt: _timestampField(map, 'endedAt'),
      createdAt: _requiredTimestamp(map, 'createdAt'),
      updatedAt: _requiredTimestamp(map, 'updatedAt'),
    );
  }

  Map<String, Object?> toMap() => <String, Object?>{
    'callId': callId,
    'callType': callType,
    'status': status,
    'initiatorId': initiatorId,
    if (initiatorRingtoneId != null) 'initiatorRingtoneId': initiatorRingtoneId,
    if (conversationId != null) 'conversationId': conversationId,
    if (circleId != null) 'circleId': circleId,
    'roomId': roomId,
    'maxParticipants': maxParticipants,
    'participantCount': participantCount,
    'participants': participants
        .map((participant) => participant.toMap())
        .toList(),
    'isScreenSharing': isScreenSharing,
    if (screenShareUserId != null) 'screenShareUserId': screenShareUserId,
    if (endReason != null) 'endReason': endReason,
    if (durationMs != null) 'durationMs': durationMs,
    if (startedAt != null) 'startedAt': startedAt!.toUtc().toIso8601String(),
    if (endedAt != null) 'endedAt': endedAt!.toUtc().toIso8601String(),
    'createdAt': createdAt.toUtc().toIso8601String(),
    'updatedAt': updatedAt.toUtc().toIso8601String(),
  };

  CallSessionDto copyWith({
    String? callId,
    String? callType,
    String? status,
    String? initiatorId,
    String? initiatorRingtoneId,
    String? conversationId,
    String? circleId,
    String? roomId,
    int? maxParticipants,
    int? participantCount,
    List<CallParticipantDto>? participants,
    bool? isScreenSharing,
    String? screenShareUserId,
    String? endReason,
    int? durationMs,
    DateTime? startedAt,
    DateTime? endedAt,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) => CallSessionDto(
    callId: callId ?? this.callId,
    callType: callType ?? this.callType,
    status: status ?? this.status,
    initiatorId: initiatorId ?? this.initiatorId,
    initiatorRingtoneId: initiatorRingtoneId ?? this.initiatorRingtoneId,
    conversationId: conversationId ?? this.conversationId,
    circleId: circleId ?? this.circleId,
    roomId: roomId ?? this.roomId,
    maxParticipants: maxParticipants ?? this.maxParticipants,
    participantCount: participantCount ?? this.participantCount,
    participants: participants ?? this.participants,
    isScreenSharing: isScreenSharing ?? this.isScreenSharing,
    screenShareUserId: screenShareUserId ?? this.screenShareUserId,
    endReason: endReason ?? this.endReason,
    durationMs: durationMs ?? this.durationMs,
    startedAt: startedAt ?? this.startedAt,
    endedAt: endedAt ?? this.endedAt,
    createdAt: createdAt ?? this.createdAt,
    updatedAt: updatedAt ?? this.updatedAt,
  );
}

final class RtcMediaSessionAccessDto {
  const RtcMediaSessionAccessDto({required this.accessToken});

  final String accessToken;

  factory RtcMediaSessionAccessDto.fromMap(Map<Object?, Object?> map) {
    final accessToken = _stringField(map, 'accessToken');
    if (accessToken == null) {
      throw const FormatException('mediaAccess must contain accessToken');
    }
    return RtcMediaSessionAccessDto(accessToken: accessToken);
  }
}

final class RtcInitiateCallResultDto {
  const RtcInitiateCallResultDto({
    required this.session,
    required this.mediaAccess,
  });

  final CallSessionDto session;
  final RtcMediaSessionAccessDto mediaAccess;
}

final class RtcAnswerCallResultDto {
  const RtcAnswerCallResultDto({
    required this.session,
    required this.mediaAccess,
  });

  final CallSessionDto session;
  final RtcMediaSessionAccessDto mediaAccess;
}

final class RtcJoinCredentialsDto {
  const RtcJoinCredentialsDto({
    required this.session,
    required this.mediaAccess,
  });

  final CallSessionDto session;
  final RtcMediaSessionAccessDto mediaAccess;

  String get roomId => session.roomId;
  String get callId => session.callId;
}

final class RtcCallHistoryPage {
  const RtcCallHistoryPage({required this.items, this.nextCursor});

  final List<CallSessionDto> items;
  final String? nextCursor;
}

CallSessionDto decodeRtcCallSession(Object? response) =>
    CallSessionDto.fromMap(_object(response, 'CallSession'));

RtcInitiateCallResultDto decodeRtcInitiateCallResult(Object? response) {
  final root = _object(response, 'InitiateCall result');
  return RtcInitiateCallResultDto(
    session: CallSessionDto.fromMap(
      _nestedObject(root, 'session', 'InitiateCall result'),
    ),
    mediaAccess: RtcMediaSessionAccessDto.fromMap(
      _nestedObject(root, 'mediaAccess', 'InitiateCall result'),
    ),
  );
}

RtcAnswerCallResultDto decodeRtcAnswerCallResult(Object? response) {
  final root = _object(response, 'AnswerCall result');
  final session = CallSessionDto.fromMap(
    _nestedObject(root, 'session', 'AnswerCall result'),
  );
  return RtcAnswerCallResultDto(
    session: session,
    mediaAccess: RtcMediaSessionAccessDto.fromMap(
      _nestedObject(root, 'mediaAccess', 'AnswerCall result'),
    ),
  );
}

RtcJoinCredentialsDto decodeRtcJoinCallResult(Object? response) {
  final root = _object(response, 'JoinCall result');
  return RtcJoinCredentialsDto(
    session: CallSessionDto.fromMap(
      _nestedObject(root, 'session', 'JoinCall result'),
    ),
    mediaAccess: RtcMediaSessionAccessDto.fromMap(
      _nestedObject(root, 'mediaAccess', 'JoinCall result'),
    ),
  );
}

RtcCallHistoryPage decodeRtcCallHistoryPage(Object? response) {
  final root = _object(response, 'CallHistory page');
  final rawItems = root['items'];
  if (rawItems is! List<Object?>) {
    throw const FormatException('CallHistory page items must be a JSON list');
  }
  final items = <CallSessionDto>[];
  for (final raw in rawItems) {
    if (raw is! Map<Object?, Object?>) {
      throw const FormatException('CallHistory item must be a JSON object');
    }
    items.add(CallSessionDto.fromMap(raw));
  }
  return RtcCallHistoryPage(
    items: List<CallSessionDto>.unmodifiable(items),
    nextCursor: _stringField(root, 'nextCursor'),
  );
}

Map<Object?, Object?> _object(Object? value, String name) {
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name must be a JSON object');
  }
  return value;
}

Map<Object?, Object?> _nestedObject(
  Map<Object?, Object?> root,
  String key,
  String name,
) {
  final value = root[key];
  if (value is! Map<Object?, Object?>) {
    throw FormatException('$name missing object "$key"');
  }
  return value;
}

String _requiredField(Map<Object?, Object?> root, String key) {
  final value = _stringField(root, key);
  if (value == null) {
    throw FormatException('missing required field "$key"');
  }
  return value;
}

String? _stringField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value == null) return null;
  if (value is! String) {
    throw FormatException('field "$key" must be a string');
  }
  final text = value.trim();
  return text.isEmpty ? null : text;
}

bool? _boolField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value == null) return null;
  if (value is! bool) {
    throw FormatException('field "$key" must be a bool');
  }
  return value;
}

int? _intField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value == null) return null;
  if (value is! num) {
    throw FormatException('field "$key" must be a number');
  }
  return value.toInt();
}

DateTime? _timestampField(Map<Object?, Object?> root, String key) {
  final value = root[key];
  if (value == null) return null;
  if (value is! String || value.trim().isEmpty) {
    throw FormatException('field "$key" must be an ISO-8601 string');
  }
  return DateTime.parse(value.trim()).toUtc();
}

DateTime _requiredTimestamp(Map<Object?, Object?> root, String key) {
  final value = _timestampField(root, key);
  if (value == null) {
    throw FormatException('missing required timestamp "$key"');
  }
  return value;
}

String _required(String value, String name) {
  final text = value.trim();
  if (text.isEmpty) {
    throw ArgumentError.value(value, name, 'must not be empty');
  }
  return text;
}

String? _optional(String? value) {
  final text = value?.trim();
  return text == null || text.isEmpty ? null : text;
}
