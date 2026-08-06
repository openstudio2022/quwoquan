import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

final class IncomingCallPresentation {
  const IncomingCallPresentation({
    required this.callerId,
    required this.displayName,
    this.avatarUrl,
    this.sourceLabel,
    this.trustRelation,
    this.expiresAt,
  });

  final String callerId;
  final String displayName;
  final String? avatarUrl;
  final String? sourceLabel;
  final String? trustRelation;
  final DateTime? expiresAt;
}

final class CallSessionActionResult {
  const CallSessionActionResult.succeeded() : succeeded = true, failure = null;

  const CallSessionActionResult.failed(this.failure) : succeeded = false;

  const CallSessionActionResult.notAttempted()
    : succeeded = false,
      failure = null;

  final bool succeeded;
  final RuntimeFailureBase? failure;
}

class CallSessionState {
  const CallSessionState({
    this.session,
    this.incomingPresentation,
    this.status = CallStatus.initiated,
    this.callType = CallType.audio,
    this.isMuted = false,
    this.isCameraOn = false,
    this.isLocalScreenSharing = false,
    this.isLoading = false,
    this.isReconnecting = false,
    this.failure,
  });

  final CallSession? session;
  final IncomingCallPresentation? incomingPresentation;
  final CallStatus status;
  final CallType callType;
  final bool isMuted;
  final bool isCameraOn;

  /// 本机是否拥有屏幕共享停止权或正在发布 LiveKit 屏幕轨道。
  ///
  /// 媒体发布失败且聚合补偿也失败时仍保持为 true，以便用户可幂等停止远端
  /// 共享事实；会话级共享状态始终只读 [session]。
  final bool isLocalScreenSharing;
  final bool isLoading;

  /// LiveKit 媒体重连中（连接质量中断后自动重连）；用于过程态派生。
  final bool isReconnecting;
  final RuntimeFailureBase? failure;

  String? get error =>
      failure == null ? null : runtimeFailureDisplayMessage(failure!);

  CallSessionState copyWith({
    CallSession? session,
    IncomingCallPresentation? incomingPresentation,
    CallStatus? status,
    CallType? callType,
    bool? isMuted,
    bool? isCameraOn,
    bool? isLocalScreenSharing,
    bool? isLoading,
    bool? isReconnecting,
    RuntimeFailureBase? failure,
    bool clearFailure = false,
  }) {
    return CallSessionState(
      session: session ?? this.session,
      incomingPresentation: incomingPresentation ?? this.incomingPresentation,
      status: status ?? this.status,
      callType: callType ?? this.callType,
      isMuted: isMuted ?? this.isMuted,
      isCameraOn: isCameraOn ?? this.isCameraOn,
      isLocalScreenSharing: isLocalScreenSharing ?? this.isLocalScreenSharing,
      isLoading: isLoading ?? this.isLoading,
      isReconnecting: isReconnecting ?? this.isReconnecting,
      failure: clearFailure ? null : (failure ?? this.failure),
    );
  }

  @override
  bool operator ==(Object other) =>
      identical(this, other) ||
      other is CallSessionState &&
          runtimeType == other.runtimeType &&
          session?.id == other.session?.id &&
          session?.status == other.session?.status &&
          session?.participantCount == other.session?.participantCount &&
          session?.isScreenSharing == other.session?.isScreenSharing &&
          session?.screenShareUserId == other.session?.screenShareUserId &&
          session?.endReason == other.session?.endReason &&
          incomingPresentation?.callerId ==
              other.incomingPresentation?.callerId &&
          incomingPresentation?.displayName ==
              other.incomingPresentation?.displayName &&
          status == other.status &&
          callType == other.callType &&
          isMuted == other.isMuted &&
          isCameraOn == other.isCameraOn &&
          isLocalScreenSharing == other.isLocalScreenSharing &&
          isLoading == other.isLoading &&
          isReconnecting == other.isReconnecting &&
          failure?.code == other.failure?.code;

  @override
  int get hashCode => Object.hash(
    session?.id,
    session?.status,
    session?.participantCount,
    session?.isScreenSharing,
    session?.screenShareUserId,
    session?.endReason,
    incomingPresentation?.callerId,
    incomingPresentation?.displayName,
    status,
    callType,
    isMuted,
    isCameraOn,
    isLocalScreenSharing,
    isLoading,
    isReconnecting,
    failure?.code,
  );
}
