import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CallStatus, CallType, EndReason, ParticipantStatus;

export 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CallStatus, CallType, EndReason, ParticipantRole, ParticipantStatus;

extension CallStatusPresentation on CallStatus {
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
        EndReason.noAnswer ||
        EndReason.timeout ||
        EndReason.rejected => CallStage.peerNoAnswer,
        EndReason.lastLeave => CallStage.peerLeft,
        _ => CallStage.ended,
      };
  }
}

extension CallTypePresentation on CallType {
  bool get isVideo => this == CallType.video;
  bool get isAudio => this == CallType.audio;
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
      return '${CallText.callSummaryDurationPrefix}'
          '${formatDuration(duration)}';
    }
    return switch (endReason) {
      EndReason.cancelled => CallText.callSummaryCancelled,
      EndReason.rejected => CallText.callSummaryRejected,
      EndReason.noAnswer || EndReason.timeout => CallText.callSummaryNoAnswer,
      _ => CallText.callSummaryMissed,
    };
  }
}

extension ParticipantStatusPresentation on ParticipantStatus {
  bool get isActive =>
      this == ParticipantStatus.connecting ||
      this == ParticipantStatus.connected;
}

/// 信任关系两态（与 quwoquan_service/services/rtc-service/contracts/rtc/call_session/fields.yaml TrustRelation 对齐）。
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
