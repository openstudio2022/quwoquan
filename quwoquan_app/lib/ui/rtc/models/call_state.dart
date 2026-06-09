import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

enum CallStatus {
  initiated,
  ringing,
  connecting,
  inCall,
  ended;

  static CallStatus fromString(String value) {
    return switch (value) {
      'initiated' => CallStatus.initiated,
      'ringing' => CallStatus.ringing,
      'connecting' => CallStatus.connecting,
      'in_call' => CallStatus.inCall,
      'ended' => CallStatus.ended,
      _ => CallStatus.initiated,
    };
  }

  String toApiString() {
    return switch (this) {
      CallStatus.initiated => 'initiated',
      CallStatus.ringing => 'ringing',
      CallStatus.connecting => 'connecting',
      CallStatus.inCall => 'in_call',
      CallStatus.ended => 'ended',
    };
  }

  bool get isActive =>
      this == CallStatus.initiated ||
      this == CallStatus.ringing ||
      this == CallStatus.connecting ||
      this == CallStatus.inCall;
}

/// 通话过程态（仅用于页面展示，不污染 [CallStatus] 状态机）。
///
/// 由 [resolveCallStage] 从权威输入（[CallStatus] / 参与者数 / 网络质量 /
/// 结束原因 / 重连标记）单一派生，杜绝页面各自拼接过程态文案（R24）。
enum CallStage {
  /// 正在接通（建连中）。
  connecting,

  /// 振铃：等待对方接听。
  ringing,

  /// 通话已建立但仅本人在房间，等待对方加入。
  waitingPeer,

  /// 通话中（多人或对端已连接）。
  inCall,

  /// 媒体连接中断，正在自动重连。
  reconnecting,

  /// 通话中但网络较弱（不中断，仅提示降级）。
  weakNetwork,

  /// 已结束：对方未接听。
  peerNoAnswer,

  /// 已结束：对方已离开。
  peerLeft,

  /// 已结束（其他原因）。
  ended;

  /// 是否为「仍在进行」的过程态（用于决定是否展示挂断/邀请等控制）。
  bool get isOngoing =>
      this == CallStage.connecting ||
      this == CallStage.ringing ||
      this == CallStage.waitingPeer ||
      this == CallStage.inCall ||
      this == CallStage.reconnecting ||
      this == CallStage.weakNetwork;

  /// 是否为终态。
  bool get isTerminal =>
      this == CallStage.peerNoAnswer ||
      this == CallStage.peerLeft ||
      this == CallStage.ended;
}

/// 由权威输入单一派生展示过程态。纯函数，便于过程态契约单测。
///
/// - [status] 通话状态机；
/// - [connectedPeerCount] 除本人外已连接参与者数；
/// - [isReconnecting] LiveKit 媒体重连中；
/// - [isWeakNetwork] 网络较弱（来自连接质量）；
/// - [endReason] 仅在 [status] == ended 时用于细分终态。
CallStage resolveCallStage({
  required CallStatus status,
  required int connectedPeerCount,
  bool isReconnecting = false,
  bool isWeakNetwork = false,
  EndReason? endReason,
}) {
  switch (status) {
    case CallStatus.initiated:
    case CallStatus.connecting:
      return CallStage.connecting;
    case CallStatus.ringing:
      return CallStage.ringing;
    case CallStatus.inCall:
      if (isReconnecting) {
        return CallStage.reconnecting;
      }
      if (connectedPeerCount <= 0) {
        return CallStage.waitingPeer;
      }
      if (isWeakNetwork) {
        return CallStage.weakNetwork;
      }
      return CallStage.inCall;
    case CallStatus.ended:
      return switch (endReason) {
        EndReason.timeout || EndReason.busy => CallStage.peerNoAnswer,
        EndReason.rejected => CallStage.peerNoAnswer,
        EndReason.initiatorHangup => CallStage.peerLeft,
        _ => CallStage.ended,
      };
  }
}

enum CallType {
  audio,
  video;

  static CallType fromString(String value) {
    return switch (value) {
      'video' => CallType.video,
      _ => CallType.audio,
    };
  }

  String toApiString() => name;

  bool get isVideo => this == CallType.video;
  bool get isAudio => this == CallType.audio;
}

enum EndReason {
  completed,
  cancelled,
  rejected,
  timeout,
  busy,
  initiatorHangup,
  networkError,
  unknown;

  static EndReason fromString(String? value) {
    return switch (value) {
      'completed' => EndReason.completed,
      'cancelled' => EndReason.cancelled,
      'rejected' => EndReason.rejected,
      'timeout' => EndReason.timeout,
      'busy' => EndReason.busy,
      'initiator_hangup' => EndReason.initiatorHangup,
      'network_error' => EndReason.networkError,
      _ => EndReason.unknown,
    };
  }
}

/// 通话结束摘要：由时长 + 结束原因单一派生展示文案。
///
/// 现服务于结束态摘要；后续通话记录回插会话（待 chat `call` 消息契约）时
/// 复用同一派生，避免两套文案口径（R24/R31）。
class CallSummary {
  const CallSummary._();

  /// 时长格式 mm:ss（≥1h 显示 h:mm:ss）。
  static String formatDuration(Duration d) {
    final hours = d.inHours;
    final minutes = d.inMinutes.remainder(60).toString().padLeft(2, '0');
    final seconds = d.inSeconds.remainder(60).toString().padLeft(2, '0');
    if (hours > 0) {
      return '$hours:$minutes:$seconds';
    }
    return '$minutes:$seconds';
  }

  /// 通话结束摘要文案：接通过的显示时长；未接通的按原因显示。
  ///
  /// [connected] 表示曾建立通话（用于区分「时长」与「未接通原因」）。
  static String describe({
    required Duration duration,
    required EndReason endReason,
    required bool connected,
  }) {
    if (connected && duration > Duration.zero) {
      return '${UITextConstants.callSummaryDurationPrefix}'
          '${formatDuration(duration)}';
    }
    return switch (endReason) {
      EndReason.cancelled || EndReason.initiatorHangup =>
        UITextConstants.callSummaryCancelled,
      EndReason.rejected || EndReason.busy =>
        UITextConstants.callSummaryRejected,
      EndReason.timeout => UITextConstants.callSummaryNoAnswer,
      _ => UITextConstants.callSummaryMissed,
    };
  }
}

enum ParticipantRole {
  initiator,
  invitee;

  static ParticipantRole fromString(String value) {
    return switch (value) {
      'initiator' => ParticipantRole.initiator,
      _ => ParticipantRole.invitee,
    };
  }
}

enum ParticipantStatus {
  invited,
  ringing,
  connecting,
  connected,
  left,
  timeout;

  static ParticipantStatus fromString(String value) {
    return switch (value) {
      'invited' => ParticipantStatus.invited,
      'ringing' => ParticipantStatus.ringing,
      'connecting' => ParticipantStatus.connecting,
      'connected' => ParticipantStatus.connected,
      'left' => ParticipantStatus.left,
      'timeout' => ParticipantStatus.timeout,
      _ => ParticipantStatus.invited,
    };
  }

  bool get isActive =>
      this == ParticipantStatus.connecting ||
      this == ParticipantStatus.connected;
}

/// 信任关系两态（与 contracts/metadata/rtc/call_session/fields.yaml TrustRelation 对齐）。
/// known=可信（联系人/关注对象/当前会话或群成员）；possiblyUnknown=提示注意隐私。
enum TrustRelation {
  known,
  possiblyUnknown;

  static TrustRelation fromString(String? value) {
    return switch (value) {
      'known' => TrustRelation.known,
      _ => TrustRelation.possiblyUnknown,
    };
  }

  bool get isKnown => this == TrustRelation.known;
}

/// 参与者连接质量（与 fields.yaml ConnectionQuality 对齐，端侧弱网指示来源之一）。
enum ConnectionQuality {
  excellent,
  good,
  poor,
  unavailable;

  static ConnectionQuality? fromString(String? value) {
    return switch (value) {
      'excellent' => ConnectionQuality.excellent,
      'good' => ConnectionQuality.good,
      'poor' => ConnectionQuality.poor,
      'unavailable' => ConnectionQuality.unavailable,
      _ => null,
    };
  }

  bool get isWeak =>
      this == ConnectionQuality.poor || this == ConnectionQuality.unavailable;
}
