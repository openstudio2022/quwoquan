import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_signal_events.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participant_presentation.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/public/rtc_call_entry_coordinator.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/rtc_media_qoe_tracker.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/platform/rtc_room_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/active_call_service.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_session_signal_projection.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_session_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_state.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/application/call_participants_provider.dart';
import 'package:quwoquan_app/service/rtc_service/rtc/call_session/presentation/call_quality_indicator.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

export 'package:quwoquan_app/service/rtc_service/rtc/call_session/domain/call_session_state.dart';

part 'call_session_provider_runtime.dart';

final rtcRoomServiceProvider = Provider<RtcRoomService>((ref) {
  final service = RtcRoomService(
    connectionUrl: CloudRuntimeConfig.rtcMediaConnectionUrl,
  );
  ref.onDispose(() => service.dispose());
  return service;
});

class CallSessionNotifier extends Notifier<CallSessionState> {
  Timer? _timeoutTimer;
  StreamSubscription<void>? _participantsSub;
  StreamSubscription<RtcSignalEvent>? _signalSub;
  RtcRoomService? _connectionListenerRoom;
  String? _mediaConnectedReportedCallId;
  final RtcMediaQoeTracker _mediaQoe = RtcMediaQoeTracker();
  int _signalRefreshGeneration = 0;
  String? _mediaCredentialsCallId;
  String _mediaAccessToken = '';
  bool _mediaAccessEnableVideo = false;
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
    final currentCallId = state.session?.id ?? '';
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
            session: state.session == null
                ? null
                : projectCallSession(
                    state.session!,
                    status: CallStatus.connecting,
                  ),
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
          session: projectCallSession(
            session,
            status: CallStatus.inCall,
            participantCount: data.participantCount,
          ),
          isReconnecting: false,
        );
        _scheduleSignalRefresh(currentCallId);
      case RtcParticipantJoinedWsPayload(data: final data):
        state = state.copyWith(
          session: state.session == null
              ? null
              : projectCallSession(
                  state.session!,
                  participantCount: data.participantCount,
                ),
        );
        _scheduleSignalRefresh(currentCallId);
      case RtcParticipantLeftWsPayload(data: final data):
        // 聚合参与者/建连状态变化：从 CallQuery 拉最新事实刷新 roster。
        state = state.copyWith(
          session: state.session == null
              ? null
              : projectCallSession(
                  state.session!,
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
          session: state.session == null
              ? null
              : projectCallSession(
                  state.session!,
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

  RtcRoomService get _lkRoom => ref.read(rtcRoomServiceProvider);
  AppUiSurface get _activeCallSurface =>
      state.callType.isVideo ? AppUiSurfaces.rtcVideo : AppUiSurfaces.rtcVoice;

  RuntimeFailureBase _failureFrom(Object error) =>
      runtimeFailureFromError(error) ??
      RuntimeFailure.unknown(code: RuntimeFailureCodes.cloudSystemUnavailable);

  CallSessionState get _runtimeState => state;
  set _runtimeState(CallSessionState value) => state = value;
  Ref get _runtimeRef => ref;

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
    final parsedCallType = CallType.fromWire(callType, 'callType');
    final callerId = initiatorId.trim();
    final displayName = callerName?.trim().isNotEmpty == true
        ? callerName!.trim()
        : callerId;
    final now = DateTime.now().toUtc();
    final session = CallSession(
      id: callId,
      callType: parsedCallType,
      status: CallStatus.ringing,
      initiatorId: callerId,
      conversationId: conversationId,
      roomId: '',
      maxParticipants: 32,
      participantCount: 2,
      participants: <CallParticipant>[
        CallParticipant(
          userId: callerId,
          role: ParticipantRole.initiator,
          status: ParticipantStatus.ringing,
          isMuted: false,
          isCameraOn: parsedCallType.isVideo,
        ),
      ],
      isScreenSharing: false,
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
      callType: parsedCallType,
      isCameraOn: parsedCallType.isVideo,
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
      if (state.session?.id != null && state.session?.id != session.id) {
        return;
      }
      if (session.status == CallStatus.ended) {
        state = state.copyWith(
          session: session,
          callType: session.callType,
          isCameraOn: session.callType.isVideo,
          isLoading: false,
          clearFailure: true,
        );
        _syncParticipantRoster(session);
        _endCallState();
        return;
      }
      state = state.copyWith(
        session: session,
        status: session.status,
        callType: session.callType,
        isCameraOn: session.callType.isVideo,
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
    final callId = state.session?.id.trim() ?? '';
    if (callId.isEmpty) return;
    final generation = ++_signalRefreshGeneration;
    await _refreshCurrentCallFromSignal(callId, generation);
    if (state.session?.id == callId &&
        state.status != CallStatus.ended &&
        _mediaCredentialsCallId == callId &&
        _mediaAccessToken.isNotEmpty) {
      if (_lkRoom.connectionState.value == RtcConnectionState.disconnected) {
        await _connectMediaTransport(
          _mediaAccessToken,
          enableVideo: _mediaAccessEnableVideo,
        );
      } else if (_lkRoom.connectionState.value ==
          RtcConnectionState.connected) {
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
          state.session?.id != expectedCallId ||
          state.status == CallStatus.ended) {
        return;
      }
      var nextStatus = session.status;
      var nextSession = session;
      // call.connected 已是服务端事件事实；读模型短暂滞后不得把状态回退到
      // ringing/connecting。
      if (state.status == CallStatus.inCall &&
          nextStatus != CallStatus.inCall &&
          nextStatus != CallStatus.ended) {
        nextStatus = CallStatus.inCall;
        nextSession = projectCallSession(session, status: CallStatus.inCall);
      }
      if (nextStatus == CallStatus.ended) {
        state = state.copyWith(
          session: nextSession,
          callType: nextSession.callType,
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
        callType: nextSession.callType,
        isCameraOn: nextSession.callType.isVideo,
        isLoading: false,
        clearFailure: true,
      );
      _syncParticipantRoster(nextSession);
    } catch (error) {
      if (generation == _signalRefreshGeneration &&
          state.session?.id == expectedCallId &&
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
        callType: CallType.fromWire(callTypeStr, 'callType'),
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
            callId: session.id,
            callType: callTypeStr,
            participants: session.participants ?? const <CallParticipant>[],
          );

      await _connectMediaTransport(
        result.mediaAccess.accessToken,
        enableVideo: callTypeStr == 'video',
      );

      _startTimeoutTimer();
      return session.id;
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
      // 接听后进入 connecting；媒体连通（_connectMediaTransport 成功 +
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
            callId: session.id,
            callType: session.callType.wireName,
            participants: session.participants ?? const <CallParticipant>[],
          );

      await _connectMediaTransport(
        answer.mediaAccess.accessToken,
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
      if (state.session?.id != callId) return;
      state = state.copyWith(session: endedSession);
      _endCallState();
    } catch (e) {
      if (state.session?.id == callId) {
        state = state.copyWith(failure: _failureFrom(e));
      }
    }
  }

  Future<void> cancelCall() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      _cancelTimeoutTimer();
      final endedSession = await ref
          .read(
            rtcCallLifecycleCommandWriterProvider(AppUiSurfaces.rtcOutgoing),
          )
          .cancelCall(RtcCallIdCommand(callId: callId));
      if (state.session?.id != callId) return;
      state = state.copyWith(session: endedSession);
      _endCallState();
    } catch (e) {
      if (state.session?.id == callId) {
        state = state.copyWith(failure: _failureFrom(e));
        _startTimeoutTimer(delay: const Duration(seconds: 5));
      }
    }
  }

  Future<CallSessionActionResult> hangupCall({
    bool clearActiveCall = true,
  }) async {
    final callId = state.session?.id;
    if (callId == null || callId.isEmpty) {
      return const CallSessionActionResult.notAttempted();
    }
    try {
      final endedSession = await ref
          .read(rtcCallLifecycleCommandWriterProvider(_activeCallSurface))
          .hangupCall(RtcCallIdCommand(callId: callId));
      if (state.session?.id != callId) {
        return const CallSessionActionResult.notAttempted();
      }
      state = state.copyWith(session: endedSession);
      _endCallState(clearActiveCall: clearActiveCall);
      return const CallSessionActionResult.succeeded();
    } catch (e) {
      final failure = _failureFrom(e);
      if (state.session?.id == callId) {
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
      final session = creds.session;
      final type = session.callType;

      state = state.copyWith(
        session: session,
        status: session.status,
        callType: type,
        isCameraOn: type.isVideo,
        isLoading: false,
      );
      _syncParticipantRoster(session);

      ref
          .read(activeCallProvider.notifier)
          .startCall(
            callId: session.id,
            callType: session.callType.wireName,
            participants: session.participants ?? const <CallParticipant>[],
          );

      await _connectMediaTransport(
        creds.mediaAccess.accessToken,
        enableVideo: type.isVideo,
      );
    } catch (e) {
      state = state.copyWith(isLoading: false, failure: _failureFrom(e));
    }
  }

  Future<void> leaveCall() async {
    final callId = state.session?.id;
    if (callId == null) return;
    try {
      final endedSession = await ref
          .read(rtcCallParticipantCommandWriterProvider(_activeCallSurface))
          .leaveCall(RtcCallIdCommand(callId: callId));
      if (state.session?.id != callId) return;
      state = state.copyWith(session: endedSession);
      _endCallState();
    } catch (e) {
      if (state.session?.id == callId) {
        state = state.copyWith(failure: _failureFrom(e));
      }
    }
  }

  Future<void> inviteToCall(List<String> inviteeIds) async {
    final callId = state.session?.id;
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
    final callId = state.session?.id;
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
        if (state.session?.id != callId) return;
        state = state.copyWith(isMuted: true);
        final session = await writer.toggleMute(
          RtcToggleMuteCommand(callId: callId, muted: true),
        );
        if (state.session?.id == callId && state.status != CallStatus.ended) {
          state = state.copyWith(
            session: session,
            isMuted: true,
            clearFailure: true,
          );
        }
      } catch (error) {
        if (state.session?.id == callId) {
          state = state.copyWith(
            isMuted: localMuted ? true : state.isMuted,
            failure: _failureFrom(error),
          );
        }
      }
      return;
    }

    CallSession? unmutedSession;
    try {
      // 开启采集时先让聚合授权，再开放本地麦克风，避免未授权音频短暂发布。
      unmutedSession = await writer.toggleMute(
        RtcToggleMuteCommand(callId: callId, muted: false),
      );
      if (state.session?.id != callId || state.status == CallStatus.ended) {
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
      CallSession? compensatedSession;
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
      if (state.session?.id == callId) {
        state = state.copyWith(
          session: compensatedSession ?? state.session,
          isMuted: true,
          failure: _failureFrom(error),
        );
      }
    }
  }

  Future<void> toggleCamera() async {
    final callId = state.session?.id;
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
        if (state.session?.id != callId) return;
        state = state.copyWith(isCameraOn: false);
        final session = await writer.toggleCamera(
          RtcToggleCameraCommand(callId: callId, cameraOn: false),
        );
        if (state.session?.id == callId && state.status != CallStatus.ended) {
          state = state.copyWith(
            session: session,
            isCameraOn: false,
            clearFailure: true,
          );
        }
      } catch (error) {
        if (state.session?.id == callId) {
          state = state.copyWith(
            isCameraOn: localCameraStopped ? false : state.isCameraOn,
            failure: _failureFrom(error),
          );
        }
      }
      return;
    }

    CallSession? cameraEnabledSession;
    try {
      // 开启画面时先让聚合授权，再开放本地摄像头。
      cameraEnabledSession = await writer.toggleCamera(
        RtcToggleCameraCommand(callId: callId, cameraOn: true),
      );
      if (state.session?.id != callId || state.status == CallStatus.ended) {
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
      CallSession? compensatedSession;
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
      if (state.session?.id == callId) {
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
    final callId = state.session?.id;
    if (callId == null || state.isLocalScreenSharing) return;
    CallSession? startedSession;
    var mediaStartAttempted = false;
    try {
      // 先由 CallSession 聚合裁决互斥与权限，再发布 LiveKit track，避免在
      // screen_share_conflict 等拒绝场景中短暂泄露未授权画面。
      startedSession = await ref
          .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
          .startScreenShare(RtcCallIdCommand(callId: callId));
      if (state.session?.id != callId || state.status == CallStatus.ended) {
        await ref
            .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
            .stopScreenShare(RtcCallIdCommand(callId: callId));
        return;
      }
      mediaStartAttempted = true;
      await _lkRoom.startScreenShare();
      if (state.session?.id == callId && state.status != CallStatus.ended) {
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
      CallSession? compensatedSession;
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
      if (state.session?.id == callId) {
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
    final callId = state.session?.id;
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
    if (state.session?.id == callId) {
      state = state.copyWith(isLocalScreenSharing: false);
    }
    try {
      final session = await ref
          .read(rtcCallScreenShareWriterProvider(AppUiSurfaces.rtcVideo))
          .stopScreenShare(RtcCallIdCommand(callId: callId));
      if (state.session?.id == callId && state.status != CallStatus.ended) {
        state = state.copyWith(
          session: projectCallSessionWithoutScreenShare(session),
          isLocalScreenSharing: false,
          clearFailure: mediaStopError == null,
          failure: mediaStopError == null ? null : _failureFrom(mediaStopError),
        );
      }
    } catch (error) {
      if (state.session?.id == callId) {
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

  void loadFromSession(CallSession session) {
    final type = session.callType;
    state = CallSessionState(
      session: session,
      status: session.status,
      callType: type,
      isCameraOn: type.isVideo,
      isMuted: false,
      isLocalScreenSharing: false,
    );
    _syncParticipantRoster(session);
  }
}

final callSessionProvider =
    NotifierProvider<CallSessionNotifier, CallSessionState>(
      CallSessionNotifier.new,
    );
