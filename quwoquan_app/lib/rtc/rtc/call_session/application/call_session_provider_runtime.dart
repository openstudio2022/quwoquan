part of 'call_session_provider.dart';

extension _CallSessionNotifierRuntime on CallSessionNotifier {
  void _syncParticipantRoster(CallSession session) {
    final incoming = _runtimeState.incomingPresentation;
    unawaited(
      _runtimeRef
          .read(callParticipantsProvider.notifier)
          .syncRoster(
            session.participants ?? const <CallParticipant>[],
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

  Future<void> _connectMediaTransport(
    String accessToken, {
    bool enableVideo = false,
  }) async {
    if (_mediaConnectInFlight) return;
    final callId = _runtimeState.session?.id ?? '';
    _mediaCredentialsCallId = callId;
    _mediaAccessToken = accessToken.trim();
    _mediaAccessEnableVideo = enableVideo;
    _beginMediaQoeAttempt();
    // 服务端未下发媒体凭据时 fail-fast（禁止端侧硬拼地址或伪造本地成功）。
    if (_mediaAccessToken.isEmpty) {
      _mediaQoe.markDisconnect(RtcMediaDisconnectReason.endpointUnavailable);
      _runtimeState = _runtimeState.copyWith(
        failure: _failureFrom(
          StateError('rtc media access token is unavailable'),
        ),
      );
      return;
    }
    // 建连阶段进入「连接中」过程态：振铃/接听后到媒体连通前的可见反馈。
    if (_runtimeState.status != CallStatus.inCall) {
      _runtimeState = _runtimeState.copyWith(status: CallStatus.connecting);
    }
    // 重连前移除旧 room observer/subscription，避免同一事件被重复消费。
    _detachLiveKitObservers();
    _mediaConnectInFlight = true;
    try {
      await _lkRoom.connect(
        accessToken: _mediaAccessToken,
        enableVideo: enableVideo,
        enableAudio: true,
      );
      // LiveKit 只代表媒体运行态已连通；CallSession 业务态由
      // ReportMediaConnected 回执 / call.connected 信令推进。
      _runtimeState = _runtimeState.copyWith(isReconnecting: false);

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
      _runtimeState = _runtimeState.copyWith(failure: _failureFrom(e));
    } finally {
      _mediaConnectInFlight = false;
    }
  }

  void _beginMediaQoeAttempt() {
    final callId = _runtimeState.session?.id ?? '';
    if (callId.isNotEmpty) {
      _mediaQoe.beginAttempt(callId);
    }
  }

  void _markMediaConnected() {
    _mediaQoe.markMediaConnected();
  }

  void _reportMediaConnectedOnce() {
    final callId = _runtimeState.session?.id ?? '';
    if (callId.isEmpty) return;
    if (_mediaConnectedReportedCallId == callId) return;
    _mediaConnectedReportedCallId = callId;
    unawaited(_reportMediaConnected(callId));
  }

  Future<void> _reportMediaConnected(String expectedCallId) async {
    try {
      final session = await _runtimeRef
          .read(rtcCallParticipantCommandWriterProvider(_activeCallSurface))
          .reportMediaConnected(RtcCallIdCommand(callId: expectedCallId));
      if (_runtimeState.session?.id == expectedCallId &&
          session.id == expectedCallId &&
          _runtimeState.status != CallStatus.ended) {
        if (session.status == CallStatus.inCall) {
          _markMediaConnected();
        }
        _runtimeState = _runtimeState.copyWith(
          session: session,
          status: session.status,
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
      if (_runtimeState.session?.id == expectedCallId &&
          _runtimeState.status != CallStatus.ended) {
        _runtimeState = _runtimeState.copyWith(failure: failure);
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
            _runtimeState.status != CallStatus.ended);
    if (reconnecting && !_runtimeState.isReconnecting) {
      _mediaQoe.markReconnectStarted();
    }
    if (connState == RtcConnectionState.disconnected &&
        _runtimeState.status != CallStatus.ended) {
      _mediaQoe.markDisconnect(RtcMediaDisconnectReason.unexpectedDisconnect);
    }
    if (connState == RtcConnectionState.connected &&
        _runtimeState.isReconnecting) {
      _mediaQoe.markReconnectRecovered();
    }
    if (reconnecting != _runtimeState.isReconnecting) {
      _runtimeState = _runtimeState.copyWith(isReconnecting: reconnecting);
    }
  }

  void _onQualityChanged() {
    final quality = _lkRoom.connectionQuality.value;
    _mediaQoe.updateNetworkQuality(switch (quality) {
      RtcNetworkQuality.excellent => RtcMediaNetworkQuality.excellent,
      RtcNetworkQuality.good => RtcMediaNetworkQuality.good,
      RtcNetworkQuality.poor ||
      RtcNetworkQuality.weak => RtcMediaNetworkQuality.poor,
    });
    _runtimeRef.read(callQualityProvider.notifier).update(switch (quality) {
      RtcNetworkQuality.excellent => NetworkQuality.good,
      RtcNetworkQuality.good => NetworkQuality.slight,
      RtcNetworkQuality.poor => NetworkQuality.poor,
      RtcNetworkQuality.weak => NetworkQuality.weak,
    });
  }

  void _onParticipantsChanged() {
    final dtos =
        _runtimeState.session?.participants ?? const <CallParticipant>[];
    _runtimeRef
        .read(callParticipantsProvider.notifier)
        .syncFromRtcRoom(_lkRoom, dtos);
  }

  void _endCallState({bool clearActiveCall = true}) {
    _cancelTimeoutTimer();
    _detachLiveKitObservers();
    unawaited(_disconnectLiveKit());
    if (clearActiveCall) {
      _runtimeRef.read(activeCallProvider.notifier).endCall();
    }
    _reportMediaQoeOnce();
    _reportCallOutcome();
    _mediaCredentialsCallId = null;
    _mediaAccessToken = '';
    _mediaAccessEnableVideo = false;
    _mediaConnectInFlight = false;
    _runtimeState = _runtimeState.copyWith(
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
    final session = _runtimeState.session;
    if (session == null) return;
    final terminal = _mediaQoe.finish(
      callId: session.id,
      callType: session.callType.wireName,
      participantCount: session.participantCount,
      abandonedBeforeAcceptance:
          _runtimeState.status == CallStatus.initiated ||
          _runtimeState.status == CallStatus.ringing,
      aggregateReachedInCall: session.startedAt != null,
      failReasonCode: _runtimeState.failure?.code,
    );
    if (terminal == null) return;
    unawaited(() async {
      try {
        await _runtimeRef
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
    final session = _runtimeState.session;
    if (session == null || _runtimeState.status == CallStatus.ended) return;
    final endedInCall = _runtimeState.status == CallStatus.inCall;
    final result = switch (_runtimeState.status) {
      CallStatus.inCall => 'completed',
      CallStatus.connecting => 'failed',
      _ => 'cancelled',
    };
    final startedAt = session.startedAt;
    unawaited(() async {
      try {
        await _runtimeRef
            .read(appTelemetryReporterProvider)
            .record(
              AppTelemetryPayload.rtcCallOutcome(
                callType: session.callType.wireName,
                result: result,
                durationMs: endedInCall && startedAt != null
                    ? DateTime.now().difference(startedAt).inMilliseconds
                    : null,
                failReasonCode: _runtimeState.failure?.code,
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
      if (_runtimeState.status == CallStatus.ringing ||
          _runtimeState.status == CallStatus.initiated) {
        unawaited(_refreshRingTimeoutState());
      }
    });
  }

  Future<void> _refreshRingTimeoutState() async {
    await retryCurrentCall();
    if (_runtimeState.status == CallStatus.ringing ||
        _runtimeState.status == CallStatus.initiated) {
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
