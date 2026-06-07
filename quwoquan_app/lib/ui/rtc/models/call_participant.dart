import 'package:livekit_client/livekit_client.dart' show VideoTrack;
import 'package:quwoquan_app/cloud/rtc/models/call_participant_dto.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';

/// UI-oriented view model wrapping CallParticipantDto with derived properties.
///
/// [videoTrack] is the live LiveKit subscribed camera track when available; it
/// is intentionally excluded from `==`/`hashCode` (tracks are identity-stable
/// media objects, equality is keyed on userId + observable state). [isLocal]
/// marks the local participant so the tile can mirror/decorate accordingly.
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
  final VideoTrack? videoTrack;
  final bool isLocal;

  /// 信任关系（known=可信；possiblyUnknown=提示注意隐私）。
  final TrustRelation trustRelation;

  /// 来源标签（如「当前会话」「联系人」「其他群」），用于加人/入会信任提示。
  final String? sourceLabel;

  /// 媒体连接质量（端侧弱网指示来源之一），可空表示未知。
  final ConnectionQuality? connectionQuality;

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
    this.videoTrack,
    this.isLocal = false,
    this.trustRelation = TrustRelation.possiblyUnknown,
    this.sourceLabel,
    this.connectionQuality,
  });

  bool get hasVideoTrack => videoTrack != null;

  factory CallParticipant.fromDto(
    CallParticipantDto dto, {
    String? displayName,
    String? avatarUrl,
  }) {
    return CallParticipant(
      userId: dto.userId,
      displayName: displayName ?? dto.displayName ?? dto.userId,
      avatarUrl: avatarUrl ?? dto.avatarUrl,
      role: ParticipantRole.fromString(dto.role),
      status: ParticipantStatus.fromString(dto.status),
      isMuted: dto.isMuted,
      isCameraOn: dto.isCameraOn,
      isSpeaking: dto.isSpeaking,
      joinedAt: dto.joinedAt,
      leftAt: dto.leftAt,
      trustRelation: TrustRelation.fromString(dto.trustRelation),
      sourceLabel: dto.sourceLabel,
      connectionQuality: ConnectionQuality.fromString(dto.connectionQuality),
    );
  }

  bool get isConnected => status == ParticipantStatus.connected;
  bool get hasLeft => status == ParticipantStatus.left;
  bool get isInitiator => role == ParticipantRole.initiator;

  /// 是否需要展示隐私提示（非可信关系，提示用户注意保护隐私）。
  bool get needsTrustWarning => trustRelation == TrustRelation.possiblyUnknown;

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
    VideoTrack? videoTrack,
    bool clearVideoTrack = false,
    bool? isLocal,
    TrustRelation? trustRelation,
    String? sourceLabel,
    ConnectionQuality? connectionQuality,
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
      videoTrack: clearVideoTrack ? null : (videoTrack ?? this.videoTrack),
      isLocal: isLocal ?? this.isLocal,
      trustRelation: trustRelation ?? this.trustRelation,
      sourceLabel: sourceLabel ?? this.sourceLabel,
      connectionQuality: connectionQuality ?? this.connectionQuality,
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
          isSpeaking == other.isSpeaking &&
          identical(videoTrack, other.videoTrack) &&
          isLocal == other.isLocal &&
          trustRelation == other.trustRelation &&
          connectionQuality == other.connectionQuality;

  @override
  int get hashCode => Object.hash(
        userId,
        status,
        isMuted,
        isCameraOn,
        isSpeaking,
        isLocal,
        trustRelation,
        connectionQuality,
      );
}
