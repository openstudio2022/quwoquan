/// RTC 领域 canonical 契约对象的 local_contract 构造器。
///
/// 唯一目的：让测试只声明它真正断言的字段，其余必填字段取契约中性默认值。
/// `copyWith` 以扩展形式提供，生成契约本身保持纯 wire 形状、不带可变语义。
/// 仅供测试树使用，禁止被 `lib/**` 或任何环境 App 装配引用。
library;

import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

CallParticipant buildCallParticipantContract({
  required String userId,
  required ParticipantRole role,
  required ParticipantStatus status,
  bool isMuted = false,
  bool isCameraOn = false,
  DateTime? joinedAt,
  DateTime? leftAt,
  CallInviteStatus? inviteStatus,
  String? invitedBy,
}) {
  return CallParticipant(
    userId: userId,
    role: role,
    status: status,
    isMuted: isMuted,
    isCameraOn: isCameraOn,
    joinedAt: joinedAt,
    leftAt: leftAt,
    inviteStatus: inviteStatus,
    invitedBy: invitedBy,
  );
}

CallSession buildCallSessionContract({
  required String id,
  required CallType callType,
  required CallStatus status,
  required String initiatorId,
  required String roomId,
  required DateTime createdAt,
  required DateTime updatedAt,
  String? initiatorRingtoneId,
  String? conversationId,
  String? circleId,
  int maxParticipants = 2,
  int participantCount = 2,
  List<CallParticipant>? participants,
  bool isScreenSharing = false,
  String? screenShareUserId,
  EndReason? endReason,
  int? durationMs,
  DateTime? startedAt,
  DateTime? endedAt,
}) {
  return CallSession(
    id: id,
    callType: callType,
    status: status,
    initiatorId: initiatorId,
    initiatorRingtoneId: initiatorRingtoneId,
    conversationId: conversationId,
    circleId: circleId,
    roomId: roomId,
    maxParticipants: maxParticipants,
    participantCount: participantCount,
    participants: participants,
    isScreenSharing: isScreenSharing,
    screenShareUserId: screenShareUserId,
    endReason: endReason,
    durationMs: durationMs,
    startedAt: startedAt,
    endedAt: endedAt,
    createdAt: createdAt,
    updatedAt: updatedAt,
  );
}

extension CallSessionContractTestCopy on CallSession {
  CallSession copyWith({
    String? id,
    CallType? callType,
    CallStatus? status,
    String? initiatorId,
    String? initiatorRingtoneId,
    String? conversationId,
    String? circleId,
    String? roomId,
    int? maxParticipants,
    int? participantCount,
    List<CallParticipant>? participants,
    bool? isScreenSharing,
    String? screenShareUserId,
    EndReason? endReason,
    int? durationMs,
    DateTime? startedAt,
    DateTime? endedAt,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return CallSession(
      id: id ?? this.id,
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
}
