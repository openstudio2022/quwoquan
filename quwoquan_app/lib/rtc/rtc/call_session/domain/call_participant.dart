import 'package:quwoquan_app/core/platform/rtc_room_service.dart';
import 'package:quwoquan_app/rtc/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_cloud_contracts/generated/rtc_contracts.dart'
    as rtc_wire;

const int callParticipantSummaryLimit = 6;

int callParticipantOverflowCount(int participantCount) =>
    participantCount > callParticipantSummaryLimit
    ? participantCount - callParticipantSummaryLimit
    : 0;

/// UI-oriented view model wrapping CallParticipantViewData with derived properties.
///
/// [videoTrack] 与 [screenShareTrack] 分别承载平台 RTC 的 camera 与
/// screen-share 订阅轨道。轨道按 identity 参与相等性，避免轨道替换后
/// Riverpod 误判状态未变化；hashCode 只使用稳定展示事实，允许非相等对象同 hash。
/// [isLocal] 标记本地参与者，供画面镜像与装饰使用。
final class CallParticipantViewData {
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
  final RtcVideoTrack? videoTrack;
  final RtcVideoTrack? screenShareTrack;
  final bool isLocal;

  /// 信任关系（known=可信；possiblyUnknown=提示注意隐私）。
  final TrustRelation trustRelation;

  const CallParticipantViewData({
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
    this.screenShareTrack,
    this.isLocal = false,
    this.trustRelation = TrustRelation.possiblyUnknown,
  });

  bool get hasVideoTrack => videoTrack != null;
  bool get hasScreenShareTrack => screenShareTrack != null;

  /// CallParticipantViewData 精简后只承载参与状态；展示名/头像/关系上下文由
  /// 调用方经联系人/成员快照注入，未注入时回退 userId 与保守信任提示。
  factory CallParticipantViewData.fromWire(
    rtc_wire.CallParticipant wire, {
    String? displayName,
    String? avatarUrl,
    TrustRelation trustRelation = TrustRelation.possiblyUnknown,
  }) {
    return CallParticipantViewData(
      userId: wire.userId,
      displayName: displayName ?? wire.userId,
      avatarUrl: avatarUrl,
      role: wire.role,
      status: wire.status,
      isMuted: wire.isMuted,
      isCameraOn: wire.isCameraOn,
      joinedAt: wire.joinedAt,
      leftAt: wire.leftAt,
      trustRelation: trustRelation,
    );
  }

  bool get isConnected => status == ParticipantStatus.connected;
  bool get hasLeft => status == ParticipantStatus.left;
  bool get isInitiator => role == ParticipantRole.initiator;

  /// 是否需要展示隐私提示（非可信关系，提示用户注意保护隐私）。
  bool get needsTrustWarning => trustRelation == TrustRelation.possiblyUnknown;

  CallParticipantViewData copyWith({
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
    RtcVideoTrack? videoTrack,
    bool clearVideoTrack = false,
    RtcVideoTrack? screenShareTrack,
    bool clearScreenShareTrack = false,
    bool? isLocal,
    TrustRelation? trustRelation,
  }) {
    return CallParticipantViewData(
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
      screenShareTrack: clearScreenShareTrack
          ? null
          : (screenShareTrack ?? this.screenShareTrack),
      isLocal: isLocal ?? this.isLocal,
      trustRelation: trustRelation ?? this.trustRelation,
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallParticipantViewData &&
          runtimeType == other.runtimeType &&
          userId == other.userId &&
          status == other.status &&
          isMuted == other.isMuted &&
          isCameraOn == other.isCameraOn &&
          isSpeaking == other.isSpeaking &&
          identical(videoTrack, other.videoTrack) &&
          identical(screenShareTrack, other.screenShareTrack) &&
          isLocal == other.isLocal &&
          trustRelation == other.trustRelation;

  @override
  int get hashCode => Object.hash(
    userId,
    status,
    isMuted,
    isCameraOn,
    isSpeaking,
    isLocal,
    trustRelation,
  );
}
