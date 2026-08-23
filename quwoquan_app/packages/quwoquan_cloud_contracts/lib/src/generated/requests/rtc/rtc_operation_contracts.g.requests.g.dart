// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: e1ab11a794ec2c40267fa9f217db7841a15176dd0fe692c983f7fcf0cb7a180e

part of '../../../rtc/rtc_operation_contracts.g.dart';

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


List<Object?> _generatedRequestList(Object? value, String path) {
  if (value is List) return List<Object?>.from(value);
  throw FormatException('$path must be a list');
}

final class RtcCallIdCommand {
  RtcCallIdCommand({
    required String callId,
  }) : callId = callId.trim() {
    if (this.callId.isEmpty) {
      throw ArgumentError.value(this.callId, "callId", 'must not be blank');
    }
  }

  final String callId;

  factory RtcCallIdCommand.fromWire(Map<String, Object?> map, [String path = "RtcCallIdCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"callId"}, path);
    return RtcCallIdCommand(
      callId: _generatedRequestString(map["callId"], '$path.callId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "callId": this.callId,
  };
}

final class RtcGetCallQuery {
  RtcGetCallQuery({
    required String callId,
  }) : callId = callId.trim() {
    if (this.callId.isEmpty) {
      throw ArgumentError.value(this.callId, "callId", 'must not be blank');
    }
  }

  final String callId;

  factory RtcGetCallQuery.fromWire(Map<String, Object?> map, [String path = "RtcGetCallQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"callId"}, path);
    return RtcGetCallQuery(
      callId: _generatedRequestString(map["callId"], '$path.callId'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "callId": this.callId,
  };
}

final class RtcInitiateCallCommand {
  RtcInitiateCallCommand({
    required CallType callType,
    required List<String> inviteeIds,
    String? conversationId,
    String? circleId,
    int maxParticipants = 32,
  }) : callType = callType,
       inviteeIds = _normalizeGeneratedTextList(inviteeIds, deduplicate: false),
       conversationId = conversationId,
       circleId = circleId,
       maxParticipants = maxParticipants {
  }

  final CallType callType;
  final List<String> inviteeIds;
  final String? conversationId;
  final String? circleId;
  final int maxParticipants;

  factory RtcInitiateCallCommand.fromWire(Map<String, Object?> map, [String path = "RtcInitiateCallCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"callType", "inviteeIds", "conversationId", "circleId", "maxParticipants"}, path);
    return RtcInitiateCallCommand(
      callType: switch (map["callType"]) { "audio" => CallType.audio, "video" => CallType.video, _ => throw FormatException('$path.callType' + ' has an invalid enum value'), },
      inviteeIds: List<String>.unmodifiable(_generatedRequestList(map["inviteeIds"], '$path.inviteeIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.inviteeIds' + '[${entry.key}]'))),
      conversationId: map["conversationId"] == null ? null : _generatedRequestString(map["conversationId"], '$path.conversationId'),
      circleId: map["circleId"] == null ? null : _generatedRequestString(map["circleId"], '$path.circleId'),
      maxParticipants: map.containsKey("maxParticipants") ? _generatedRequestInt(map["maxParticipants"], '$path.maxParticipants') : 32,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "callType": this.callType.wireName,
    "inviteeIds": this.inviteeIds.map((value) => value).toList(growable: false),
    if (this.conversationId != null) "conversationId": this.conversationId!,
    if (this.circleId != null) "circleId": this.circleId!,
    "maxParticipants": this.maxParticipants,
  };
}

final class RtcInviteToCallCommand {
  RtcInviteToCallCommand({
    required String callId,
    required List<String> inviteeIds,
  }) : callId = callId.trim(),
       inviteeIds = _normalizeGeneratedTextList(inviteeIds, deduplicate: false) {
    if (this.callId.isEmpty) {
      throw ArgumentError.value(this.callId, "callId", 'must not be blank');
    }
  }

  final String callId;
  final List<String> inviteeIds;

  factory RtcInviteToCallCommand.fromWire(Map<String, Object?> map, [String path = "RtcInviteToCallCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"callId", "inviteeIds"}, path);
    return RtcInviteToCallCommand(
      callId: _generatedRequestString(map["callId"], '$path.callId'),
      inviteeIds: List<String>.unmodifiable(_generatedRequestList(map["inviteeIds"], '$path.inviteeIds').asMap().entries.map((entry) => _generatedRequestString(entry.value, '$path.inviteeIds' + '[${entry.key}]'))),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "callId": this.callId,
    "inviteeIds": this.inviteeIds.map((value) => value).toList(growable: false),
  };
}

final class RtcListCallsQuery {
  static const int defaultLimit = 20;
  static const int maximumLimit = 100;

  RtcListCallsQuery({
    String? cursor,
    int limit = 20,
    CallStatus? status,
    bool missedOnly = false,
  }) : cursor = cursor,
       limit = limit,
       status = status,
       missedOnly = missedOnly {
    if (this.limit <= 0) {
      throw ArgumentError.value(this.limit, "limit", "must be positive");
    }
    if (this.limit > 100) {
      throw ArgumentError.value(this.limit, "limit", "must not exceed 100");
    }
  }

  final String? cursor;
  final int limit;
  final CallStatus? status;
  final bool missedOnly;

  factory RtcListCallsQuery.fromWire(Map<String, Object?> map, [String path = "RtcListCallsQuery"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"cursor", "limit", "status", "missed"}, path);
    return RtcListCallsQuery(
      cursor: map["cursor"] == null ? null : _generatedRequestString(map["cursor"], '$path.cursor'),
      limit: map.containsKey("limit") ? _generatedRequestInt(map["limit"], '$path.limit') : 20,
      status: map["status"] == null ? null : switch (map["status"]) { "initiated" => CallStatus.initiated, "ringing" => CallStatus.ringing, "connecting" => CallStatus.connecting, "in_call" => CallStatus.inCall, "ended" => CallStatus.ended, _ => throw FormatException('$path.status' + ' has an invalid enum value'), },
      missedOnly: map.containsKey("missed") ? _generatedRequestBool(map["missed"], '$path.missed') : false,
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.status != null) "status": this.status!.wireName,
    "missed": this.missedOnly,
  };
}

final class RtcToggleCameraCommand {
  RtcToggleCameraCommand({
    required String callId,
    required bool cameraOn,
  }) : callId = callId.trim(),
       cameraOn = cameraOn {
    if (this.callId.isEmpty) {
      throw ArgumentError.value(this.callId, "callId", 'must not be blank');
    }
  }

  final String callId;
  final bool cameraOn;

  factory RtcToggleCameraCommand.fromWire(Map<String, Object?> map, [String path = "RtcToggleCameraCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"callId", "cameraOn"}, path);
    return RtcToggleCameraCommand(
      callId: _generatedRequestString(map["callId"], '$path.callId'),
      cameraOn: _generatedRequestBool(map["cameraOn"], '$path.cameraOn'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "callId": this.callId,
    "cameraOn": this.cameraOn,
  };
}

final class RtcToggleMuteCommand {
  RtcToggleMuteCommand({
    required String callId,
    required bool muted,
  }) : callId = callId.trim(),
       muted = muted {
    if (this.callId.isEmpty) {
      throw ArgumentError.value(this.callId, "callId", 'must not be blank');
    }
  }

  final String callId;
  final bool muted;

  factory RtcToggleMuteCommand.fromWire(Map<String, Object?> map, [String path = "RtcToggleMuteCommand"]) {
    _generatedRequestRejectUnknownFields(map, const <String>{"callId", "muted"}, path);
    return RtcToggleMuteCommand(
      callId: _generatedRequestString(map["callId"], '$path.callId'),
      muted: _generatedRequestBool(map["muted"], '$path.muted'),
    );
  }

  Map<String, Object?> toWire() => <String, Object?>{
    "callId": this.callId,
    "muted": this.muted,
  };
}

CloudOperationRequestPayload encodeRtcCallSessionAnswerCallGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionCancelCallGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionGetCallGeneratedRequest(RtcGetCallQuery request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionHangupCallGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionInitiateCallGeneratedRequest(RtcInitiateCallCommand request) {
  return CloudOperationRequestPayload(
    body: <String, Object?>{
      "callType": request.callType.wireName,
      "inviteeIds": request.inviteeIds.map((value) => value).toList(growable: false),
      if (request.conversationId != null) "conversationId": request.conversationId!,
      if (request.circleId != null) "circleId": request.circleId!,
      "maxParticipants": request.maxParticipants,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionInviteToCallGeneratedRequest(RtcInviteToCallCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
    body: <String, Object?>{
      "inviteeIds": request.inviteeIds.map((value) => value).toList(growable: false),
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionJoinCallGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionLeaveCallGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionListCallsGeneratedRequest(RtcListCallsQuery request) {
  return CloudOperationRequestPayload(
    queryParameters: <String, String>{
      "limit": (request.limit).toString(),
      if (request.cursor != null) "cursor": request.cursor!,
      if (request.status != null) "status": (request.status!.wireName).toString(),
      "missed": (request.missedOnly).toString(),
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionRejectCallGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionReportMediaConnectedGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionStartScreenShareGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionStopScreenShareGeneratedRequest(RtcCallIdCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionToggleCameraGeneratedRequest(RtcToggleCameraCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
    body: <String, Object?>{
      "cameraOn": request.cameraOn,
    },
  );
}

CloudOperationRequestPayload encodeRtcCallSessionToggleMuteGeneratedRequest(RtcToggleMuteCommand request) {
  return CloudOperationRequestPayload(
    pathParameters: <String, String>{
      "callId": request.callId,
    },
    body: <String, Object?>{
      "muted": request.muted,
    },
  );
}

