import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/rtc/livekit_room_service.dart';
import 'package:quwoquan_app/cloud/rtc/rtc_signal_events.dart';
import 'package:quwoquan_app/cloud/runtime/generated/rtc/rtc_signal_payloads.g.dart';
import 'package:quwoquan_app/application/rtc/call_session/call_participant_presentation.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/application/rtc/call_session/rtc_media_qoe_tracker.dart';
import 'package:quwoquan_app/cloud/runtime/generated/ops/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/services/active_call_service.dart';
import 'package:quwoquan_app/ui/rtc/models/call_session_signal_projection.dart';
import 'package:quwoquan_app/ui/rtc/models/call_session_state.dart';
import 'package:quwoquan_app/ui/rtc/models/call_state.dart';
import 'package:quwoquan_app/ui/rtc/providers/call_participants_provider.dart';
import 'package:quwoquan_app/ui/rtc/widgets/call_quality_indicator.dart';
import 'package:quwoquan_app/core/errors/runtime_error_display.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

export 'package:quwoquan_app/ui/rtc/models/call_session_state.dart';

final liveKitRoomServiceProvider = Provider<LiveKitRoomService>((ref) {
  final service = LiveKitRoomService();
  ref.onDispose(() => service.dispose());
  return service;
});

class CallSessionNotifier extends Notifier<CallSessionState> {
  Timer? _timeoutTimer;
  StreamSubscription<void>? _participantsSub;
  StreamSubscription<RtcSignalEvent>? _signalSub;
  LiveKitRoomService? _connectionListenerRoom;
  String? _mediaConnectedReportedCallId;
  final RtcMediaQoeTracker _mediaQoe = RtcMediaQoeTracker();
  int _signalRefreshGeneration = 0;
  String? _mediaCredentialsCallId;
  String _liveKitToken = '';
  String _liveKitUrl = '';
  bool _liveKitEnableVideo = false;
  bool _mediaConnectInFlight = false;

  @override
  CallSessionState build() {
    // 通话信令是会话状态的权威事实源（LiveKit 房间事件只兜底媒体面）：
    // 对端接听/挂断/取消、参与者变更、屏幕共享状态全部经 realtime 单通道对齐。
    _signalSub = ref
        .read(rtcSignalEventBusProvider)
        .events
        .listen(_onSignalEvent);
    ref.onDispose(() {
      _signalSub?.cancel();
      _signalSub = null;
      _cancelTimeoutTimer();
      _detachLiveKitObservers();
    });
    return const CallSessionState();
  }

  /// realtime 信令消费：只处理当前会话的事件（callId 对齐）。
  void _onSignalEvent(RtcSignalEvent event) {
    final currentCallId = state.session?.callId ?? '';
    if (currentCallId.isEmpty || event.callId != currentCallId) {
      return;
    }
    switch (event.payload) {
      case RtcCallAnsweredWsPayload():
        // 呼出方：对端已接听，进入建连过程态（媒体连通后由
        // ReportMediaConnected/call.connected 推进 in_call）。
        if (state.status == CallStatus.ringing ||
            state.status == CallStatus.initiated) {
          state = state.copyWith(
            status: CallStatus.connecting,
            session: state.session?.copyWith(status: 'connecting'),
          );
        }
      case RtcCallEndedWsPayload(data: final data):
        // 对端挂断/取消/服务端 no_answer 超时：任意阶段都收尾，
        // 不再依赖 LiveKit 断连兜底（connecting 阶段无媒体连接可依赖）。
        if (state.status != CallStatus.ended) {
          _signalRefreshGeneration += 1;
          state = state.copyWith(
            session: projectCallSessionEnded(state.session!, data),
            isLocalScreenSharing: false,
          );
          _endCallState();
        }
      case RtcCallConnectedWsPayload(data: final data):
        _markMediaConnected();
        final session = state.session!;
        state = state.copyWith(
          status: CallStatus.inCall,
          session: session.copyWith(
            status: 'in_call',
            participantCount: data.participantCount,
          ),
          isReconnecting: false,
        );
        _scheduleSignalRefresh(currentCallId);
      case RtcParticipantJoinedWsPayload(data: final data):
        state = state.copyWith(
          session: state.session?.copyWith(
            participantCount: data.participantCount,
          ),
        );
        _scheduleSignalRefresh(currentCallId);
      case RtcParticipantLeftWsPayload(data: final data):
        // 聚合参与者/建连状态变化：从 CallQuery 拉最新事实刷新 roster。
        state = state.copyWith(
          session: state.session?.copyWith(
            participantCount: data.participantCount,
          ),
        );
        _scheduleSignalRefresh(currentCallId);
      case RtcScreenShareStartedWsPayload(data: final data):
        final isLocalScreenShare =
            _isLocalParticipant(data.userId) ||
            (state.isLocalScreenSharing &&
                state.session?.screenShareUserId == data.userId);
        state = state.copyWith(
          session: state.session?.copyWith(
            isScreenSharing: true,
            screenShareUserId: data.userId,
          ),
          isLocalScreenSharing: isLocalScreenShare,
        );
      case RtcScreenShareStoppedWsPayload():
        final session = state.session;
        if (session != null) {
          // copyWith 的 null 语义无法清空 sharer；显式重建共享终止事实。
          state = state.copyWith(
            session: projectCallSessionWithoutScreenShare(session),
            isLocalScreenSharing: false,
          );
        }
      default:
        break;
    }
  }

  bool _isLocalParticipant(String? userId) {
    final candidate = userId?.trim() ?? '';
    if (candidate.isEmpty) return false;
    final localIdentity = _lkRoom.localParticipant?.identity.trim() ?? '';
    if (localIdentity.isNotEmpty && localIdentity == candidate) {
      return true;
    }
    return ref
        .read(callParticipantsProvider)
        .participants
        .any(
          (participant) =>
              participant.isLocal && participant.userId == candidate,
        );
  }

  LiveKitRoomService get _lkRoom => ref.read(liveKitRoomServiceProvider);
  AppUiSurface get _activeCallSurface =>
      state.callType.isVideo ? AppUiSurfaces.rtcVideo : AppUiSurfaces.rtcVoice;

  RuntimeFailureBase _failureFrom(Object error) =>
      runtimeFailureFromError(error) ??
      RuntimeFailure.unknown(code: RuntimeFailureCodes.cloudSystemUnavailable);

  /// 把可信 realtime `call.ringing` 负载投影为来电首帧。
  ///
  /// 这不是测试 seed：真实/alpha/gamma 都经同一事件通道调用；随后页面再用
  /// [refreshIncomingCall] 从 CallQuery 补全聚合详情。
  void seedIncomingCall({
    required String callId,
    required String callType,
    required String initiatorId,
    String? callerName,
    String? callerAvatarUrl,
    String? conversationId,
    String? sourceLabel,
    String? trustRelation,
    String? expiresAt,
  }) {
    final callerId = initiatorId.trim();
    final displayName = callerName?.trim().isNotEmpty == true
        ? callerName!.trim()
        : callerId;
    final now = DateTime.now().toUtc();
    final session = CallSessionDto(
      callId: callId,
      callType: callType,
      status: 'ringing',
      initiatorId: callerId,
      conversationId: conversationId,
      roomId: '',
      maxParticipants: 32,
      participantCount: 2,
      participants: <CallParticipantDto>[
        CallParticipantDto(
          userId: callerId,
          role: 'initiator',
          status: 'ringing',
          isCameraOn: callType == 'video',
        ),
      ],
      createdAt: now,
      updatedAt: now,
    );
    state = state.copyWith(
      session: session,
      incomingPresentation: IncomingCallPresentation(
        callerId: callerId,
        displayName: displayName,
        avatarUrl: callerAvatarUrl,
        sourceLabel: sourceLabel,
        trustRelation: trustRelation,
        expiresAt: DateTime.tryParse(expiresAt ?? '')?.toUtc(),
      ),
      status: CallStatus.ringing,
      callType: CallType.fromString(callType),
      isCameraOn: callType == 'video',
      isLoading: false,
      clearFailure: true,
    );
    _syncParticipantRoster(session);
  }

  Future<void> refreshIncomingCall(String callId) async {
    if (callId.trim().isEmpty) return;
    try {
      final session = await ref
          .read(rtcCallQueryProvider(AppUiSurfaces.rtcIncoming))
          .getCall(RtcGetCallQuery(callId: callId));
      if (state.session?.callId != null &&
          state.session?.callId != session.callId) {
        return;
      }
      if (session.status == 'ended') {
        state = state.copyWith(
          session: session,
          callType: CallType.fromString(session.callType),
          isCameraOn: session.callType == 'video',
          isLoading: false,
          clearFailure: true,
        );
        _syncParticipantRoster(session);
        _endCallState();
        return;
      }
      state = state.copyWith(
        session: session,
        status: CallStatus.fromString(session.status),
        callType: CallType.fromString(session.callType),
        isCameraOn: session.callType == 'video',
        isLoading: false,
        clearFailure: true,
      );
      _syncParticipantRoster(session);
    } catch (error) {
      // 保留 ringing 首帧，不用网络失败把来电页退化为空白；错误语义由页面
      // 消费并提供重试。
      state = state.copyWith(isLoading: false, failure: _failureFrom(error));
    }
  }

  Future<void> retryCurrentCall() async {
    final callId = state.session?.callId.trim() ?? '';
    if (callId.isEmpty) return;
    final generation = ++_signalRefreshGeneration;
    await _refreshCurrentCallFromSignal(callId, generation);
    if (state.session?.callId == callId &&
        state.status != CallStatus.ended &&
        _mediaCredentialsCallId == callId &&
        _liveKitToken.isNotEmpty) {
      if (_lkRoom.connectionState.value == RtcConnectionState.disconnected) {
        await _connectToLiveKit(
          _liveKitToken,
          url: _liveKitUrl,
          enableVideo: _liveKitEnableVideo,
        );
      } else if (_lkRoom.connectionState.value == RtcConnectionState.connected) {
        // 媒体已经连通但 ReportMediaConnected 曾耗尽重试时，不重建房间；
        // 复用同一 call 的显式重试入口重新提交聚合事实。
        _reportMediaConnectedOnce();
      }
    }
  }

  void _scheduleSignalRefresh(String expectedCallId) {
    final generation = ++_signalRefreshGeneration;
    unawaited(_refreshCurrentCallFromSignal(expectedCallId, generation));
  }

  Future<void> _refreshCurrentCallFromSignal(
    String expectedCallId,
    int generation,
  ) async {
    try {
      final session = await ref
          .read(rtcCallQueryProvider(_activeCallSurface))
          .getCall(RtcGetCallQuery(callId: expectedCallId));
      if (generation != _signalRefreshGeneration ||
          state.session?.callId != expectedCallId ||
          state.status == CallStatus.ended) {
        return;
      }
      var nextStatus = CallStatus.fromString(session.status);
      var nextSession = session;
      // call.connected 已是服务端事件事实；读模型短暂滞后不得把状态回退到
      // ringing/connecting。
      if (state.status == CallStatus.inCall &&
          nextStatus != CallStatus.inCall &&
          nextStatus != CallStatus.ended) {
        nextStatus = CallStatus.inCall;
        nextSession = session.copyWith(status: 'in_call');
      }
      if (nextStatus == CallStatus.ended) {
        state = state.copyWith(
          session: nextSession,
          callType: CallType.fromString(nextSession.callType),
          isLoading: false,
          clearFailure: true,
        );
        _syncParticipantRoster(nextSession);
        _endCallState();
        return;
      }
      state = state.copyWith(
        session: nextSession,
        status: nextStatus,
        callType: CallType.fromString(nextSession.callType),
        isCameraOn: nextSession.callType == 'video',
        isLoading: false,
        clearFailure: true,
      );
      _syncParticipantRoster(nextSession);
    } catch (error) {
      if (generation == _signalRefreshGeneration &&
          state.session?.callId == expectedCallId &&
          state.status != CallStatus.ended) {
        state = state.copyWith(failure: _failureFrom(error));
      }
    }
  }

  Future<String?> initiateCall({
    required RtcCallEntryIntent intent,
    required List<String> selectedInviteeIds,
    required AppUiSurface sourceSurface,
  }) async {
    if (state.isLoading) return null;
    final callTypeStr = intent.mediaType.wireValue;
    try {
      state = state.copyWith(
        isLoading: true,
        clearFailure: true,
        callType: CallType.fromString(callTypeStr),
        isCameraOn: callTypeStr == 'video',
        status: CallStatus.initiated,
      );

      final result = await RtcCallEntryCoordinator(
        lifecycleWriter: ref.read(
          rtcCallLifecycleCommandWriterProvider(sourceSurface),
        ),
      ).initiate(intent, selectedInviteeIds: selectedInviteeIds);
      final session = result.session;

      state = state.copyWith(
        session: session,
        status: CallStatus.ringing,
        isLoading: false,
      );
      _syncParticipantRoster(session);

      ref
          .read(activeCallProvider.notifier)
          .startCall(
            callId: session.callId,
            callType: callTypeStr,
            participants: session.participants,
          );

      await _connectToLiveKit(
        result.token,
        url: result.livekitUrl,
        enableVideo: callTypeStr == 'video',
      );

      _startTimeoutTimer();
      return session.callId;
    } catch (e) {
      state = state.copyWith(isLoading: false, failure: _failureFrom(e));
      return null;
    }
  }

  Future<void> answerCall(String callId) async {
    if (state.isLoading) return;
    try {
      state = state.copyWith(isLoading: true, clearFailure: true);
      _cancelTimeoutTimer();

      final answer = await ref
          .read(
            rtcCallLifecycleCommandWriterProvider(AppUiSurfaces.rtcIncoming),
          )
          .answerCall(RtcCallIdCommand(callId: callId));
      final session = answer.session;
      // Preserve the call type established during the ringing phase;
      // the answer response must not silently override it (e.g., mock data
      // may always return a 'video' session regardless of actual type).
      final type = state.callType;
      final token = answer.token;

      // 接听后进入 connecting；媒体连通（_connectToLiveKit 成功 +
      // ReportMediaConnected）才推进 in_call，与服务端状态机同源。
      state = state.copyWith(
        session: session,
        status: CallStatus.connecting,
        callType: type,
        isCameraOn: type.isVideo,
        isLoading: false,
      );
      _syncParticipantRoster(session);

      ref
          .read(activeCallProvider.notifier)
          .startCall(
            callId: session.callId,
            callType: session.callType,
            participants: session.participants,
          );

      await _connectToLiveKit(
        token,
        url: answer.livekitUrl,
        enableVideo: type.isVideo,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, failure: _failureFrom(e));
    }
  }

  Future<void> rejectCall(String callId) async {
    try {
      _cancelTimeoutTimer();
      final endedSession = await ref
          .read(
            rtcCallLifecycleCommandWriterProvider(AppUiSurfaces.rtcIncoming),
          )
          .rejectCall(RtcCallIdCommand(callId: callId));
      if (state.session?.callId != callId) return;
      state = state.copyWith(session: endedSession);
      _endCallState();
    } catch (e) {
      if (state.session?.callId == callId) {
        state = state.copyWith(failure: _failureFrom(e));
      }
    }
  }

  Future<void> cancelCall() async {
    final callId = state.session?.callId;
    if (callId == null) return;
    try {
      _cancelTimeoutTimer();
      final endedSession = await ref
          .read(
            rtcCallLifecycleCommandWriterProvider(AppUiSurfaces.rtcOutgoing),
          )
          .cancelCall(RtcCallIdCommand(callId: callId));
      if (state.session?.callId != callId) return;
      state = state.copyWith(session: endedSession);
      _endCallState();
    } catch (e) {
      if (state.session?.callId == callId) {
        state = state.copyWith(failure: _failureFrom(e));
        _startTimeoutTimer(delay: const Duration(seconds: 5));
      }
    }
  }

  Future<CallSessionActionResult> hangupCall({
    bool clearActiveCall = true,
  }) async {
    final callId = state.session?.callId;
    if (callId == null || callId.isEmpty) {
      return const CallSessionActionResult.notAttempted();
    }
    try {
      final endedSession = await ref
          .read(rtcCallLifecycleCommandWriterProvider(_activeCallSurface))
          .hangupCall(RtcCallIdCommand(callId: callId));
      if (state.session?.callId != callId) {
        return const CallSessionActionResult.notAttempted();
      }
      state = state.copyWith(session: endedSession);
      _endCallState(clearActiveCall: clearActiveCall);
      return const CallSessionActionResult.succeeded();
    } catch (e) {
      final failure = _failureFrom(e);
      if (state.session?.callId == callId) {
        state = state.copyWith(isLoading: false, failure: failure);
      }
      return CallSessionActionResult.failed(failure);
    }
  }

  Future<void> joinCall(String callId) async {
    if (state.isLoading) return;
    try {
      state = state.copyWith(isLoading: true, clearFailure: true);

      final creds = await ref
          .read(rtcCallParticipantCommandWriterProvider(_activeCallSurface))
          .joinCall(RtcCallIdCommand(callId: callId));
      final token = creds.token;
      final session = creds.session;
      final type = CallType.fromString(session.callType);

      state = state.copyWith(
        session: session,
        status: CallStatus.fromString(session.status),
        callType: type,
        isCameraOn: type.isVideo,
        isLoading: false,
      );
      _syncParticipantRoster(session);

      ref
          .read(activeCallProvider.notifier)
          .startCall(
            callId: session.callId,
            callType: session.callType,
            participants: session.participants,
          );

      await _connectToLiveKit(
        token,
        url: creds.livekitUrl,
        enableVideo: type.isVideo,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, failure: _failureFrom(e));
    }
  }

  Future<void> leaveCall() async {
    final callId = state.session?.callId;
    if (callId == null) return;
    try {
      final endedSession = await ref
          .read(rtcCallParticipantCommandWriterProvider(_activeCallSurface))
          .leaveCall(RtcCallIdCommand(callId: callId));
      if (state.session?.callId != callId) return;
      state = state.copyWith(session: endedSession);
      _endCallState();
    } catch (e) {
      if (state.session?.callId == callId) {
        state = state.copyWith(failure: _failureFrom(e));
      }
    }
  }

  Future<void> inviteToCall(List<String> inviteeIds) async {
    final callId = state.session?.callId;
    if (callId == null) return;
    try {
      final session = await ref
          .read(
            rtcCallParticipantCommandWriterProvider(
              AppUiSurfaces.rtcPickParticipants,
            ),
          )
          .inviteToCall(
            RtcInviteToCallCommand(callId: callId, inviteeIds: inviteeIds),
          );
      state = state.copyWith(session: session);
      _syncParticipantRoster(session);
    } catch (e) {
      state = state.copyWith(failure: _failureFrom(e));
    }
  }

  Future<void> toggleMute() async {
    final callId = state.session?.callId;
    if (callId == null) return;
    final targetMuted = !state.isMuted;
    final writer = ref.read(
      rtcCallMediaControlWriterProvider(_activeCallSurface),
    );
    if (targetMuted) {
      var localMuted = false;
      try {
        // 关闭采集时隐私优先：先停本地麦克风，再提交聚合投影。
        await _lkRoom.setMicrophoneEnabled(false);
        localMuted = true;
        if (state.session?.callId != callId) return;
        state = state.copyWith(isMuted: true);
        final session = await writer.toggleMute(
          RtcToggleMuteCommand(callId: callId, muted: true),
        );
        if (state.session?.callId == callId &&
            state.status != CallStatus.ended) {
          state = state.copyWith(
            session: session,
            isMuted: true,
            clearFailure: true,
          );
        }
      } catch (error) {
        if (state.session?.callId == callId) {
          state = state.copyWith(
            isMuted: localMuted ? true : state.isMuted,
            failure: _failureFrom(error),
          );
        }
      }
      return;
    }

    CallSessionDto? unmutedSession;
    try {
      // 开启采集时先让聚合授权，再开放本地麦克风，避免未授权音频短暂发布。
      unmutedSession = await writer.toggleMute(
        RtcToggleMuteCommand(callId: callId, muted: false),
      );
      if (state.session?.callId != callId || state.status == CallStatus.ended) {
        return;
      }
      await _lkRoom.setMicrophoneEnabled(true);
      state = state.copyWith(
        session: unmutedSession,
        isMuted: false,
        clearFailure: true,
      );
    } catch (error) {
      try {
        await _lkRoom.setMicrophoneEnabled(false);
      } catch (rollbackError, rollbackStackTrace) {
        developer.log(
          'RTC microphone privacy rollback failed',
          name: 'CallSessionNotifier',
          error: rollbackError.runtimeType,
          stackTrace: rollbackStackTrace,
        );
      }
      CallSessionDto? compensatedSession;
      if (unmutedSession != null) {
        try {
          compensatedSession = await writer.toggleMute(
            RtcToggleMuteCommand(callId: callId, muted: true),
          );
        } catch (compensationError, compensationStackTrace) {
          developer.log(
            'RTC mute aggregate compensation failed',
            name: 'CallSessionNotifier',
            error: compensationError.runtimeType,
            stackTrace: compensationStackTrace,
          );
        }
      }
      if (state.session?.callId == callId) {
        state = state.copyWith(
          session: compensatedSession ?? state.session,
          isMuted: true,
          failure: _failureFrom(error),
        );
      }
    }
  }

  Future<void> toggleCamera() async {
    final callId = state.session?.callId;
    if (callId == null) return;
    final targetCameraOn = !state.isCameraOn;
    final writer = ref.read(
      rtcCallMediaControlWriterProvider(_activeCallSurface),
    );
    if (!targetCameraOn) {
      var localCameraStopped = false;
      try {
        // 关闭画面时隐私优先：先停本地采集，再提交聚合投影。
        await _lkRoom.setCameraEnabled(false);
        localCameraStopped = true;
        if (state.session?.callId != callId) return;
        state = state.copyWith(isCameraOn: false);
        final session = await writer.toggleCamera(
          RtcToggleCameraCommand(callId: callId, cameraOn: false),
        );
        if (state.session?.callId == callId &&
            state.status != CallStatus.ended) {
          state = state.copyWith(
            session: session,
            isCameraOn: false,
            clearFailure: true,
          );
        }
      } catch (error) {
        if (state.session?.callId == callId) {
          state = state.copyWith(
            isCameraOn: localCameraStopped ? false : state.isCameraOn,
            failure: _failureFrom(error),
          );
        }
      }
      return;
    }

    CallSessionDto? cameraEnabledSession;
    try {
      // 开启画面时先让聚合授权，再开放本地摄像头。
      cameraEnabledSession = await writer.toggleCamera(
        RtcToggleCameraCommand(callId: callId, cameraOn: true),
      );
      if (state.session?.callId != callId || state.status == CallStatus.ended) {
        return;
      }
      await _lkRoom.setCameraEnabled(true);
      state = state.copyWith(
        session: cameraEnabledSession,
        isCameraOn: true,
        clearFailure: true,
      );
    } catch (error) {
      try {
        await _lkRoom.setCameraEnabled(false);
      } catch (rollbackError, rollbackStackTrace) {
        developer.log(
          'RTC camera privacy rollback failed',
          name: 'CallSessionNotifier',
          error: rollbackError.runtimeType,
          stackTrace: rollbackStackTrace,
        );
      }
      CallSessionDto? compensatedSession;
      if (cameraEnabledSession != null) {
        try {
          compensatedSession = await writer.toggleCamera(
            RtcToggleCameraCommand(callId: callId, cameraOn: false),
          );
        } catch (compensationError, compensationStackTrace) {
          developer.log(
            'RTC camera aggregate compensation failed',
            name: 'CallSessionNotifier',
            error: compensationError.runtimeType,
            stackTrace: compensationStackTrace,
          );
        }
      }
      if (state.session?.callId == callId) {
        state = state.copyWith(
          session: compensatedSession ?? state.session,
          isCameraOn: false,
          failure: _failureFrom(error),
        );
      }
    }
  }

  Future<bool> switchCamera() async {
    if (!state.isCameraOn || state.status == CallStatus.ended) return false;
    try {
      await _lkRoom.switchCamera();
      if (state.status != CallStatus.ended) {
        state = state.copyWith(clearFailure: true);
      }
      return true;
    } catch (error) {
      if (state.status != CallStatus.ended) {
        state = state.copyWith(failure: _failureFrom(error));
      }
      return false;
    }
  }

  Future<bool> setSpeakerOn(bool speakerOn) async {
    if (state.status == CallStatus.ended) return false;
    try {
      await _lkRoom.setSpeakerOn(speakerOn);
      if (state.status != CallStatus.ended) {
        state = state.copyWith(clearFailure: true);
      }
      return true;
    } catch (error) {
      if (state.status != CallStatus.ended) {
        state = state.copyWith(failure: _failureFrom(error));
      }
      return false;
    }
  }

  Future<void> startScreenShare() async {
    final callId = state.session?.callId;
    if (callId == null || state.isLocalScreenSharing) return;
    CallSessionDto? startedSession;
    var mediaStartAttempted = false;
    try {
      // 先由 CallSession 聚合裁决互斥与权限，再发布 LiveKit track，避免在
      // screen_share_conflict 等拒绝场景中短暂泄露未授权画面。
      startedSession = await ref
          .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
          .startScreenShare(RtcCallIdCommand(callId: callId));
      if (state.session?.callId != callId || state.status == CallStatus.ended) {
        await ref
            .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
            .stopScreenShare(RtcCallIdCommand(callId: callId));
        return;
      }
      mediaStartAttempted = true;
      await _lkRoom.startScreenShare();
      if (state.session?.callId == callId && state.status != CallStatus.ended) {
        state = state.copyWith(
          session: startedSession,
          isLocalScreenSharing: true,
          clearFailure: true,
        );
      }
    } catch (error, stackTrace) {
      // SDK 可能在原生采集已启动后才抛错；只要调用过 start 就幂等尝试
      // stop，不能仅以 Future 是否正常完成判断敏感画面是否正在发布。
      if (mediaStartAttempted) {
        try {
          await _lkRoom.stopScreenShare();
        } catch (rollbackError, rollbackStackTrace) {
          developer.log(
            'RTC screen-share rollback failed',
            name: 'CallSessionNotifier',
            error: rollbackError.runtimeType,
            stackTrace: rollbackStackTrace,
          );
        }
      }
      CallSessionDto? compensatedSession;
      if (startedSession != null) {
        try {
          compensatedSession = await ref
              .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
              .stopScreenShare(RtcCallIdCommand(callId: callId));
        } catch (compensationError, compensationStackTrace) {
          developer.log(
            'RTC screen-share aggregate compensation failed',
            name: 'CallSessionNotifier',
            error: compensationError.runtimeType,
            stackTrace: compensationStackTrace,
          );
        }
      }
      if (state.session?.callId == callId) {
        final compensationSucceeded = compensatedSession != null;
        state = state.copyWith(
          session: compensationSucceeded
              ? projectCallSessionWithoutScreenShare(compensatedSession)
              : (startedSession ?? state.session),
          // 补偿失败时保留停止入口；此时服务端仍认为当前用户拥有共享，
          // 页面显示接收中而不是伪报共享已成功。
          isLocalScreenSharing:
              startedSession != null && !compensationSucceeded,
          failure: _failureFrom(error),
        );
      }
      developer.log(
        'RTC screen-share start failed',
        name: 'CallSessionNotifier',
        error: error.runtimeType,
        stackTrace: stackTrace,
      );
    }
  }

  Future<void> stopScreenShare() async {
    final callId = state.session?.callId;
    if (callId == null) return;
    Object? mediaStopError;
    StackTrace? mediaStopStackTrace;
    try {
      await _lkRoom.stopScreenShare();
    } catch (error, stackTrace) {
      mediaStopError = error;
      mediaStopStackTrace = stackTrace;
      // 若 SDK 无法确认采集已停止，断开房间是隐私优先的最后保障；用户可从
      // 结构化失败横幅重连同一 CallSession，不创建第二会话。
      await _disconnectLiveKit();
    }
    if (state.session?.callId == callId) {
      state = state.copyWith(isLocalScreenSharing: false);
    }
    try {
      final session = await ref
          .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
          .stopScreenShare(RtcCallIdCommand(callId: callId));
      if (state.session?.callId == callId && state.status != CallStatus.ended) {
        state = state.copyWith(
          session: projectCallSessionWithoutScreenShare(session),
          isLocalScreenSharing: false,
          clearFailure: mediaStopError == null,
          failure: mediaStopError == null ? null : _failureFrom(mediaStopError),
        );
      }
    } catch (error) {
      if (state.session?.callId == callId) {
        state = state.copyWith(
          // 服务端停止失败时保留停止入口，允许幂等重试；本地 track 已先停。
          isLocalScreenSharing: true,
          failure: _failureFrom(error),
        );
      }
    }
    if (mediaStopError != null) {
      developer.log(
        'RTC screen-share media stop failed; room disconnected',
        name: 'CallSessionNotifier',
        error: mediaStopError.runtimeType,
        stackTrace: mediaStopStackTrace,
      );
    }
  }

  void loadFromSession(CallSessionDto session) {
    final type = CallType.fromString(session.callType);
    state = CallSessionState(
      session: session,
      status: CallStatus.fromString(session.status),
      callType: type,
      isCameraOn: type.isVideo,
      isMuted: false,
      isLocalScreenSharing: false,
    );
    _syncParticipantRoster(session);
  }

  void _syncParticipantRoster(CallSessionDto session) {
    final incoming = state.incomingPresentation;
    unawaited(
      ref
          .read(callParticipantsProvider.notifier)
          .syncRoster(
            session.participants,
            conversationId: session.conversationId,
            callerFallback: incoming == null
                ? null
                : CallParticipantPresentation(
                    userId: incoming.callerId,
                    displayName: incoming.displayName,
                    avatarUrl: incoming.avatarUrl,
                    knownInCurrentContext:
                        incoming.trustRelation == 'known' ||
                        session.conversationId?.isNotEmpty == true,
                  ),
          ),
    );
  }

  Future<void> _connectToLiveKit(
    String token, {
    required String url,
    bool enableVideo = false,
  }) async {
    if (_mediaConnectInFlight) return;
    final callId = state.session?.callId ?? '';
    _mediaCredentialsCallId = callId;
    _liveKitToken = token.trim();
    _liveKitUrl = url.trim();
    _liveKitEnableVideo = enableVideo;
    _beginMediaQoeAttempt();
    // 服务端未下发媒体凭据时 fail-fast（禁止端侧硬拼地址或伪造本地成功）。
    if (_liveKitToken.isEmpty || _liveKitUrl.isEmpty) {
      _mediaQoe.markDisconnect(RtcMediaDisconnectReason.endpointUnavailable);
      state = state.copyWith(
        failure: _failureFrom(
          StateError('rtc livekit credentials are unavailable'),
        ),
      );
      return;
    }
    // 建连阶段进入「连接中」过程态：振铃/接听后到媒体连通前的可见反馈。
    if (state.status != CallStatus.inCall) {
      state = state.copyWith(status: CallStatus.connecting);
    }
    // 重连前移除旧 room observer/subscription，避免同一事件被重复消费。
    _detachLiveKitObservers();
    _mediaConnectInFlight = true;
    try {
      await _lkRoom.connect(
        url: _liveKitUrl,
        token: _liveKitToken,
        enableVideo: enableVideo,
        enableAudio: true,
      );
      // LiveKit 只代表媒体运行态已连通；CallSession 业务态由
      // ReportMediaConnected 回执 / call.connected 信令推进。
      state = state.copyWith(isReconnecting: false);

      // 建连事实上报服务端（驱动聚合 in_call/startedAt 与 call.connected 信令；
      // 通话记录时长依赖 startedAt）。失败不打断本地通话：generated client 按
      // metadata retry policy 自动重试，剩余偏差由 call.connected/getCall 对齐。
      _reportMediaConnectedOnce();

      _lkRoom.connectionState.addListener(_onConnectionStateChanged);
      _connectionListenerRoom = _lkRoom;
      _lkRoom.connectionQuality.addListener(_onQualityChanged);
      _lkRoom.activeSpeaker.addListener(_onParticipantsChanged);

      // Initial sync once connected, then on every room participant/track event.
      _onParticipantsChanged();
      _participantsSub = _lkRoom.onParticipantsChanged.listen(
        (_) => _onParticipantsChanged(),
      );
    } catch (e) {
      _mediaQoe.markDisconnect(RtcMediaDisconnectReason.connectFailed);
      state = state.copyWith(failure: _failureFrom(e));
    } finally {
      _mediaConnectInFlight = false;
    }
  }

  void _beginMediaQoeAttempt() {
    final callId = state.session?.callId ?? '';
    if (callId.isNotEmpty) {
      _mediaQoe.beginAttempt(callId);
    }
  }

  void _markMediaConnected() {
    _mediaQoe.markMediaConnected();
  }

  void _reportMediaConnectedOnce() {
    final callId = state.session?.callId ?? '';
    if (callId.isEmpty) return;
    if (_mediaConnectedReportedCallId == callId) return;
    _mediaConnectedReportedCallId = callId;
    unawaited(_reportMediaConnected(callId));
  }

  Future<void> _reportMediaConnected(String expectedCallId) async {
    try {
      final session = await ref
          .read(rtcCallParticipantCommandWriterProvider(_activeCallSurface))
          .reportMediaConnected(RtcCallIdCommand(callId: expectedCallId));
      if (state.session?.callId == expectedCallId &&
          session.callId == expectedCallId &&
          state.status != CallStatus.ended) {
        if (session.status == 'in_call') {
          _markMediaConnected();
        }
        state = state.copyWith(
          session: session,
          status: CallStatus.fromString(session.status),
          clearFailure: true,
        );
        _syncParticipantRoster(session);
      }
    } catch (error, stackTrace) {
      if (_mediaConnectedReportedCallId == expectedCallId) {
        // “已上报”只代表成功完成；失败后释放闩锁，让显式重试能够修复
        // LiveKit 已连通而 CallSession 仍停在 connecting 的偏差。
        _mediaConnectedReportedCallId = null;
      }
      final failure = _failureFrom(error);
      if (state.session?.callId == expectedCallId &&
          state.status != CallStatus.ended) {
        state = state.copyWith(failure: failure);
      }
      developer.log(
        'RTC media-connected report failed',
        name: 'CallSessionNotifier',
        error: failure.code,
        stackTrace: stackTrace,
      );
    }
  }

  void _onConnectionStateChanged() {
    final connState = _lkRoom.connectionState.value;
    final reconnecting =
        connState == RtcConnectionState.reconnecting ||
        (connState == RtcConnectionState.disconnected &&
            state.status != CallStatus.ended);
    if (reconnecting && !state.isReconnecting) {
      _mediaQoe.markReconnectStarted();
    }
    if (connState == RtcConnectionState.disconnected &&
        state.status != CallStatus.ended) {
      _mediaQoe.markDisconnect(RtcMediaDisconnectReason.unexpectedDisconnect);
    }
    if (connState == RtcConnectionState.connected && state.isReconnecting) {
      _mediaQoe.markReconnectRecovered();
    }
    if (reconnecting != state.isReconnecting) {
      state = state.copyWith(isReconnecting: reconnecting);
    }
  }

  void _onQualityChanged() {
    final q = _lkRoom.connectionQuality.value;
    final quality = q.toNetworkQuality();
    _mediaQoe.updateNetworkQuality(switch (quality) {
      NetworkQuality.good => RtcMediaNetworkQuality.excellent,
      NetworkQuality.slight => RtcMediaNetworkQuality.good,
      NetworkQuality.weak || NetworkQuality.poor => RtcMediaNetworkQuality.poor,
    });
    ref.read(callQualityProvider.notifier).update(quality);
  }

  void _onParticipantsChanged() {
    final dtos = state.session?.participants ?? const <CallParticipantDto>[];
    ref.read(callParticipantsProvider.notifier).syncFromLiveKit(_lkRoom, dtos);
  }

  void _endCallState({bool clearActiveCall = true}) {
    _cancelTimeoutTimer();
    _detachLiveKitObservers();
    unawaited(_disconnectLiveKit());
    if (clearActiveCall) {
      ref.read(activeCallProvider.notifier).endCall();
    }
    _reportMediaQoeOnce();
    _reportCallOutcome();
    _mediaCredentialsCallId = null;
    _liveKitToken = '';
    _liveKitUrl = '';
    _liveKitEnableVideo = false;
    _mediaConnectInFlight = false;
    state = state.copyWith(
      status: CallStatus.ended,
      isLocalScreenSharing: false,
      isLoading: false,
      isReconnecting: false,
    );
  }

  void _detachLiveKitObservers() {
    final participantsSub = _participantsSub;
    _participantsSub = null;
    if (participantsSub != null) {
      unawaited(participantsSub.cancel());
    }
    final room = _connectionListenerRoom;
    room?.connectionState.removeListener(_onConnectionStateChanged);
    room?.connectionQuality.removeListener(_onQualityChanged);
    room?.activeSpeaker.removeListener(_onParticipantsChanged);
    _connectionListenerRoom = null;
  }

  void _reportMediaQoeOnce() {
    final session = state.session;
    if (session == null) return;
    final terminal = _mediaQoe.finish(
      callId: session.callId,
      callType: session.callType,
      participantCount: session.participantCount,
      abandonedBeforeAcceptance:
          state.status == CallStatus.initiated ||
          state.status == CallStatus.ringing,
      aggregateReachedInCall: session.startedAt != null,
      failReasonCode: state.failure?.code,
    );
    if (terminal == null) return;
    unawaited(() async {
      try {
        await ref
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.rtcMediaQoe(
                callType: terminal.callType,
                result: terminal.result.wireValue,
                connectTimeMs: terminal.connectTimeMs,
                mediaConnected: terminal.mediaConnected,
                reconnectCount: terminal.reconnectCount,
                disconnectReason: terminal.disconnectReason?.wireValue,
                networkQuality: terminal.networkQuality.wireValue,
                participantCount: terminal.participantCount,
                failReasonCode: terminal.failReasonCode,
              ),
            );
      } catch (error, stackTrace) {
        developer.log(
          'RTC media QoE telemetry failed',
          name: 'CallSessionNotifier',
          error: error.runtimeType,
          stackTrace: stackTrace,
        );
      }
    }());
  }

  Future<void> _disconnectLiveKit() async {
    try {
      await _lkRoom.disconnect();
    } catch (error, stackTrace) {
      developer.log(
        'RTC media disconnect failed',
        name: 'CallSessionNotifier',
        error: error.runtimeType,
        stackTrace: stackTrace,
      );
    }
  }

  /// 通话结束一次性上报结果（rtc_call_outcome，metadata event_catalog 真相源）。
  void _reportCallOutcome() {
    final session = state.session;
    if (session == null || state.status == CallStatus.ended) return;
    final endedInCall = state.status == CallStatus.inCall;
    final result = switch (state.status) {
      CallStatus.inCall => 'completed',
      CallStatus.connecting => 'failed',
      _ => 'cancelled',
    };
    final startedAt = session.startedAt;
    unawaited(() async {
      try {
        await ref
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.rtcCallOutcome(
                callType: session.callType,
                result: result,
                durationMs: endedInCall && startedAt != null
                    ? DateTime.now().difference(startedAt).inMilliseconds
                    : null,
                failReasonCode: state.failure?.code,
                participantCount: session.participantCount,
              ),
            );
      } catch (error, stackTrace) {
        developer.log(
          'RTC call-outcome telemetry failed',
          name: 'CallSessionNotifier',
          error: error.runtimeType,
          stackTrace: stackTrace,
        );
      }
    }());
  }

  void _startTimeoutTimer({Duration delay = const Duration(seconds: 35)}) {
    _cancelTimeoutTimer();
    _timeoutTimer = Timer(delay, () {
      if (state.status == CallStatus.ringing ||
          state.status == CallStatus.initiated) {
        unawaited(_refreshRingTimeoutState());
      }
    });
  }

  Future<void> _refreshRingTimeoutState() async {
    await retryCurrentCall();
    if (state.status == CallStatus.ringing ||
        state.status == CallStatus.initiated) {
      // `no_answer` 只能由服务端 ring-timeout sweeper 写入。若本次读取早于
      // sweeper 或暂时失败，继续短轮询，而不是由客户端误发 CancelCall。
      _startTimeoutTimer(delay: const Duration(seconds: 5));
    }
  }

  void _cancelTimeoutTimer() {
    _timeoutTimer?.cancel();
    _timeoutTimer = null;
  }
}

final callSessionProvider =
    NotifierProvider<CallSessionNotifier, CallSessionState>(
      CallSessionNotifier.new,
    );
