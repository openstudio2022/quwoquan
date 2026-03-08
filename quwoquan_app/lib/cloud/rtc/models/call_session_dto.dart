import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';

class CallSessionDto {
  final String id;
  final String callType;
  final String status;
  final String initiatorId;
  final String? conversationId;
  final String? circleId;
  final String roomId;
  final int maxParticipants;
  final int participantCount;
  final List<CallParticipantDto> participants;
  final bool isRecording;
  final String? recordingUrl;
  final bool isScreenSharing;
  final String? screenShareUserId;
  final String? endReason;
  final int? durationMs;
  final DateTime? startedAt;
  final DateTime? endedAt;
  final DateTime createdAt;
  final DateTime updatedAt;

  const CallSessionDto({
    required this.id,
    required this.callType,
    required this.status,
    required this.initiatorId,
    this.conversationId,
    this.circleId,
    required this.roomId,
    this.maxParticipants = 32,
    this.participantCount = 0,
    this.participants = const [],
    this.isRecording = false,
    this.recordingUrl,
    this.isScreenSharing = false,
    this.screenShareUserId,
    this.endReason,
    this.durationMs,
    this.startedAt,
    this.endedAt,
    required this.createdAt,
    required this.updatedAt,
  });

  factory CallSessionDto.fromMap(Map<String, dynamic> map) {
    final rawParticipants = map['participants'];
    final participants = <CallParticipantDto>[];
    if (rawParticipants is List) {
      for (final p in rawParticipants) {
        if (p is Map<String, dynamic>) {
          participants.add(CallParticipantDto.fromMap(p));
        }
      }
    }

    return CallSessionDto(
      id: (map['id'] ?? map['_id'] ?? '') as String,
      callType: map['callType'] as String? ?? 'audio',
      status: map['status'] as String? ?? 'initiated',
      initiatorId: map['initiatorId'] as String? ?? '',
      conversationId: map['conversationId'] as String?,
      circleId: map['circleId'] as String?,
      roomId: map['roomId'] as String? ?? '',
      maxParticipants: map['maxParticipants'] as int? ?? 32,
      participantCount: map['participantCount'] as int? ?? 0,
      participants: participants,
      isRecording: map['isRecording'] as bool? ?? false,
      recordingUrl: map['recordingUrl'] as String?,
      isScreenSharing: map['isScreenSharing'] as bool? ?? false,
      screenShareUserId: map['screenShareUserId'] as String?,
      endReason: map['endReason'] as String?,
      durationMs: map['durationMs'] as int?,
      startedAt: map['startedAt'] != null
          ? DateTime.tryParse(map['startedAt'] as String)
          : null,
      endedAt: map['endedAt'] != null
          ? DateTime.tryParse(map['endedAt'] as String)
          : null,
      createdAt: DateTime.tryParse(
              (map['createdAt'] as String?) ?? '') ??
          DateTime.now(),
      updatedAt: DateTime.tryParse(
              (map['updatedAt'] as String?) ?? '') ??
          DateTime.now(),
    );
  }

  Map<String, dynamic> toMap() {
    return {
      'id': id,
      'callType': callType,
      'status': status,
      'initiatorId': initiatorId,
      if (conversationId != null) 'conversationId': conversationId,
      if (circleId != null) 'circleId': circleId,
      'roomId': roomId,
      'maxParticipants': maxParticipants,
      'participantCount': participantCount,
      'participants': participants.map((p) => p.toMap()).toList(),
      'isRecording': isRecording,
      if (recordingUrl != null) 'recordingUrl': recordingUrl,
      'isScreenSharing': isScreenSharing,
      if (screenShareUserId != null) 'screenShareUserId': screenShareUserId,
      if (endReason != null) 'endReason': endReason,
      if (durationMs != null) 'durationMs': durationMs,
      if (startedAt != null) 'startedAt': startedAt!.toIso8601String(),
      if (endedAt != null) 'endedAt': endedAt!.toIso8601String(),
      'createdAt': createdAt.toIso8601String(),
      'updatedAt': updatedAt.toIso8601String(),
    };
  }

  CallSessionDto copyWith({
    String? id,
    String? callType,
    String? status,
    String? initiatorId,
    String? conversationId,
    String? circleId,
    String? roomId,
    int? maxParticipants,
    int? participantCount,
    List<CallParticipantDto>? participants,
    bool? isRecording,
    String? recordingUrl,
    bool? isScreenSharing,
    String? screenShareUserId,
    String? endReason,
    int? durationMs,
    DateTime? startedAt,
    DateTime? endedAt,
    DateTime? createdAt,
    DateTime? updatedAt,
  }) {
    return CallSessionDto(
      id: id ?? this.id,
      callType: callType ?? this.callType,
      status: status ?? this.status,
      initiatorId: initiatorId ?? this.initiatorId,
      conversationId: conversationId ?? this.conversationId,
      circleId: circleId ?? this.circleId,
      roomId: roomId ?? this.roomId,
      maxParticipants: maxParticipants ?? this.maxParticipants,
      participantCount: participantCount ?? this.participantCount,
      participants: participants ?? this.participants,
      isRecording: isRecording ?? this.isRecording,
      recordingUrl: recordingUrl ?? this.recordingUrl,
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

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallSessionDto &&
          runtimeType == other.runtimeType &&
          id == other.id &&
          status == other.status &&
          participantCount == other.participantCount &&
          isRecording == other.isRecording &&
          isScreenSharing == other.isScreenSharing &&
          updatedAt == other.updatedAt;

  @override
  int get hashCode => Object.hash(
        id,
        status,
        participantCount,
        isRecording,
        isScreenSharing,
        updatedAt,
      );
}
