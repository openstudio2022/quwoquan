// Code generated from the accepted ContractGraph. DO NOT EDIT.
// ContractGraph SHA256: 07b120d8c226ad653523b7a2965cf1f9e0f43704e848966de103c40df7ab319a

part of '../../../rtc/call_session_contracts.dart';

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

final class RtcCallIdCommand {
  RtcCallIdCommand({
    required String callId,
  }) : callId = callId.trim() {
    if (this.callId.isEmpty) {
      throw ArgumentError.value(this.callId, "callId", 'must not be blank');
    }
  }

  final String callId;

  Map<String, Object?> toJson() => <String, Object?>{
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

  Map<String, Object?> toJson() => <String, Object?>{
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

  Map<String, Object?> toJson() => <String, Object?>{
    "callType": switch (this.callType) { CallType.audio => "audio", CallType.video => "video", },
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

  Map<String, Object?> toJson() => <String, Object?>{
    "callId": this.callId,
    "inviteeIds": this.inviteeIds.map((value) => value).toList(growable: false),
  };
}

final class RtcListCallsQuery {
  const RtcListCallsQuery({
    String? cursor,
    int limit = 20,
    CallStatus? status,
    bool missedOnly = false,
  }) : cursor = cursor,
       limit = limit,
       status = status,
       missedOnly = missedOnly;

  final String? cursor;
  final int limit;
  final CallStatus? status;
  final bool missedOnly;

  Map<String, Object?> toJson() => <String, Object?>{
    if (this.cursor != null) "cursor": this.cursor!,
    "limit": this.limit,
    if (this.status != null) "status": switch (this.status!) { CallStatus.initiated => "initiated", CallStatus.ringing => "ringing", CallStatus.connecting => "connecting", CallStatus.inCall => "in_call", CallStatus.ended => "ended", },
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

  Map<String, Object?> toJson() => <String, Object?>{
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

  Map<String, Object?> toJson() => <String, Object?>{
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
      "callType": switch (request.callType) { CallType.audio => "audio", CallType.video => "video", },
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
      if (request.status != null) "status": (switch (request.status!) { CallStatus.initiated => "initiated", CallStatus.ringing => "ringing", CallStatus.connecting => "connecting", CallStatus.inCall => "in_call", CallStatus.ended => "ended", }).toString(),
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

