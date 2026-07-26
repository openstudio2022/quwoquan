import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将屏幕共享终止信令投影回同一个 CallSession DTO。
///
/// generated `copyWith` 的 nullable 字段无法显式清空，因此在此集中重建，
/// 避免页面、provider 和测试各自维护第二套清空逻辑。
CallSessionDto projectCallSessionWithoutScreenShare(CallSessionDto session) {
  return CallSessionDto(
    callId: session.callId,
    callType: session.callType,
    status: session.status,
    initiatorId: session.initiatorId,
    initiatorRingtoneId: session.initiatorRingtoneId,
    conversationId: session.conversationId,
    circleId: session.circleId,
    roomId: session.roomId,
    maxParticipants: session.maxParticipants,
    participantCount: session.participantCount,
    participants: session.participants,
    isScreenSharing: false,
    endReason: session.endReason,
    durationMs: session.durationMs,
    startedAt: session.startedAt,
    endedAt: session.endedAt,
    createdAt: session.createdAt,
    updatedAt: session.updatedAt,
  );
}

/// 将 `call.ended` 的服务端事实覆盖到当前 CallSession；事件未携带的字段保留。
CallSessionDto projectCallSessionEnded(
  CallSessionDto session,
  RtcCallEndedPayload data,
) {
  final endedAt = DateTime.tryParse(data.endedAt ?? '')?.toUtc();
  return CallSessionDto(
    callId: session.callId,
    callType: data.callType ?? session.callType,
    status: 'ended',
    initiatorId: data.initiatorId ?? session.initiatorId,
    initiatorRingtoneId: session.initiatorRingtoneId,
    conversationId: data.conversationId ?? session.conversationId,
    circleId: session.circleId,
    roomId: session.roomId,
    maxParticipants: session.maxParticipants,
    participantCount: data.participantCount ?? session.participantCount,
    participants: session.participants,
    isScreenSharing: false,
    endReason: data.endReason ?? session.endReason,
    durationMs: data.durationMs ?? session.durationMs,
    startedAt: DateTime.tryParse(data.startedAt ?? '') ?? session.startedAt,
    endedAt: endedAt ?? session.endedAt,
    createdAt: session.createdAt,
    updatedAt: endedAt ?? session.updatedAt,
  );
}
