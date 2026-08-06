import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Rebuilds the canonical immutable wire for local realtime projections.
CallSession projectCallSession(
  CallSession session, {
  CallStatus? status,
  int? participantCount,
  bool? isScreenSharing,
  String? screenShareUserId,
  bool clearScreenShareUserId = false,
}) => CallSession(
  id: session.id,
  callType: session.callType,
  status: status ?? session.status,
  initiatorId: session.initiatorId,
  initiatorRingtoneId: session.initiatorRingtoneId,
  conversationId: session.conversationId,
  circleId: session.circleId,
  roomId: session.roomId,
  maxParticipants: session.maxParticipants,
  participantCount: participantCount ?? session.participantCount,
  participants: session.participants,
  isScreenSharing: isScreenSharing ?? session.isScreenSharing,
  screenShareUserId: clearScreenShareUserId
      ? null
      : (screenShareUserId ?? session.screenShareUserId),
  endReason: session.endReason,
  durationMs: session.durationMs,
  startedAt: session.startedAt,
  endedAt: session.endedAt,
  createdAt: session.createdAt,
  updatedAt: session.updatedAt,
);

/// 将屏幕共享终止信令投影回同一个 canonical CallSession。
CallSession projectCallSessionWithoutScreenShare(CallSession session) {
  return projectCallSession(
    session,
    isScreenSharing: false,
    clearScreenShareUserId: true,
  );
}

/// 将 `call.ended` 的服务端事实覆盖到当前 CallSession；事件未携带的字段保留。
CallSession projectCallSessionEnded(
  CallSession session,
  RtcCallEndedPayload data,
) {
  final endedAt = DateTime.tryParse(data.endedAt ?? '')?.toUtc();
  return CallSession(
    id: session.id,
    callType: data.callType ?? session.callType,
    status: CallStatus.ended,
    initiatorId: data.initiatorId ?? session.initiatorId,
    initiatorRingtoneId: session.initiatorRingtoneId,
    conversationId: data.conversationId ?? session.conversationId,
    circleId: session.circleId,
    roomId: session.roomId,
    maxParticipants: session.maxParticipants,
    participantCount: data.participantCount ?? session.participantCount,
    participants: session.participants,
    isScreenSharing: false,
    screenShareUserId: null,
    endReason: data.endReason ?? session.endReason,
    durationMs: data.durationMs ?? session.durationMs,
    startedAt: DateTime.tryParse(data.startedAt ?? '') ?? session.startedAt,
    endedAt: endedAt ?? session.endedAt,
    createdAt: session.createdAt,
    updatedAt: endedAt ?? session.updatedAt,
  );
}
