import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';

/// UI-oriented view model wrapping CallParticipantDto with derived properties.
class CallParticipant {
  final String userId;
  final String displayName;
  final String? avatarUrl;
  final ParticipantRole role;
  final ParticipantStatus status;
  final bool isMuted;
  final bool isCameraOn;
  final bool isSpeaking;
  final double audioLevel;
  final DateTime? joinedAt;
  final DateTime? leftAt;

  const CallParticipant({
    required this.userId,
    this.displayName = '',
    this.avatarUrl,
    this.role = ParticipantRole.invitee,
    this.status = ParticipantStatus.invited,
    this.isMuted = false,
    this.isCameraOn = true,
    this.isSpeaking = false,
    this.audioLevel = 0.0,
    this.joinedAt,
    this.leftAt,
  });

  factory CallParticipant.fromDto(
    CallParticipantDto dto, {
    String? displayName,
    String? avatarUrl,
  }) {
    return CallParticipant(
      userId: dto.userId,
      displayName: displayName ?? dto.userId,
      avatarUrl: avatarUrl,
      role: ParticipantRole.fromString(dto.role),
      status: ParticipantStatus.fromString(dto.status),
      isMuted: dto.isMuted,
      isCameraOn: dto.isCameraOn,
      joinedAt: dto.joinedAt,
      leftAt: dto.leftAt,
    );
  }

  bool get isConnected => status == ParticipantStatus.connected;
  bool get hasLeft => status == ParticipantStatus.left;
  bool get isInitiator => role == ParticipantRole.initiator;

  CallParticipant copyWith({
    String? userId,
    String? displayName,
    String? avatarUrl,
    ParticipantRole? role,
    ParticipantStatus? status,
    bool? isMuted,
    bool? isCameraOn,
    bool? isSpeaking,
    double? audioLevel,
    DateTime? joinedAt,
    DateTime? leftAt,
  }) {
    return CallParticipant(
      userId: userId ?? this.userId,
      displayName: displayName ?? this.displayName,
      avatarUrl: avatarUrl ?? this.avatarUrl,
      role: role ?? this.role,
      status: status ?? this.status,
      isMuted: isMuted ?? this.isMuted,
      isCameraOn: isCameraOn ?? this.isCameraOn,
      isSpeaking: isSpeaking ?? this.isSpeaking,
      audioLevel: audioLevel ?? this.audioLevel,
      joinedAt: joinedAt ?? this.joinedAt,
      leftAt: leftAt ?? this.leftAt,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallParticipant &&
          runtimeType == other.runtimeType &&
          userId == other.userId &&
          status == other.status &&
          isMuted == other.isMuted &&
          isCameraOn == other.isCameraOn &&
          isSpeaking == other.isSpeaking;

  @override
  int get hashCode => Object.hash(userId, status, isMuted, isCameraOn, isSpeaking);
}
