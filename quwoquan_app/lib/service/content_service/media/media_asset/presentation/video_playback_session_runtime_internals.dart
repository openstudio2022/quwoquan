part of 'video_playback_session.dart';

extension _VideoPlaybackSessionRuntimeInternals on VideoPlaybackSession {
  void _syncAutomaticPlayback() {
    if (_intent == VideoPlaybackIntent.manualPause ||
        !_autoEligible ||
        !_isVisible ||
        !_isForeground) {
      _pauseFor(
        _pauseReason ??
            (_isForeground
                ? VideoPlaybackPauseReason.focusLost
                : VideoPlaybackPauseReason.appLifecycle),
      );
      return;
    }
    unawaited(_playIfAllowed());
  }

  void _pauseFor(VideoPlaybackPauseReason reason) {
    _pauseReason = reason;
    unawaited(_controller?.pause() ?? Future<void>.value());
  }

  Future<void> _playIfAllowed({bool userInitiated = false}) async {
    if ((!userInitiated && !_autoEligible) || !_isVisible || !_isForeground) {
      return;
    }
    await _controller?.play();
  }

  VideoPlaybackTransport _resolveTransport({
    required bool initialized,
    required Duration duration,
    required Duration position,
    required bool isPlaying,
    required bool isBuffering,
  }) {
    if (_hasFailure) {
      return VideoPlaybackTransport.failure;
    }
    if (_controller == null || !initialized) {
      return VideoPlaybackTransport.initializing;
    }
    if (_scrubTarget != null) {
      return VideoPlaybackTransport.scrubbing;
    }
    if (isBuffering) {
      return VideoPlaybackTransport.buffering;
    }
    if (duration > Duration.zero && position >= duration && !isPlaying) {
      return VideoPlaybackTransport.ended;
    }
    if (isPlaying) {
      return VideoPlaybackTransport.playing;
    }
    return VideoPlaybackTransport.paused;
  }

  Duration _clampDuration(Duration value, Duration max) {
    if (value < Duration.zero) {
      return Duration.zero;
    }
    return value > max ? max : value;
  }

  void _handleControllerValueChanged() {
    _settleEffectivePlaybackInterval();
    final value = _controller?.value;
    final isPlaying = value?.isPlaying ?? false;
    if (value?.isBuffering ?? false) {
      _startRebuffering();
    } else {
      _stopRebuffering();
      if (value?.isInitialized ?? false) {
        _lastStablePosition = value!.position;
      }
    }
    final startedPlaying = isPlaying && !_lastKnownPlaying;
    _lastKnownPlaying = isPlaying;
    _startEffectivePlaybackIntervalIfEligible();
    if (startedPlaying &&
        _controlsVisibility == VideoPlaybackControlsVisibility.hidden) {
      showTransientControls();
      return;
    }
    _notify();
  }

  void _detachListener() {
    _controller?.removeListener(_handleControllerValueChanged);
    _nativeSignalBindingGeneration += 1;
    unawaited(_nativeSignalSubscription?.cancel() ?? Future<void>.value());
    _nativeSignalSubscription = null;
  }

  void _advanceControllerEpoch({bool renew = true}) {
    final terminalCompleter = _controllerEpochTerminalCompleter;
    if (!terminalCompleter.isCompleted) {
      terminalCompleter.complete();
    }
    if (renew) {
      _controllerEpochTerminalCompleter = Completer<void>();
    }
  }

  void _bindNativeSignals(Stream<VideoNativePlaybackSignal> signals) {
    final bindingGeneration = _nativeSignalBindingGeneration + 1;
    _nativeSignalBindingGeneration = bindingGeneration;
    unawaited(_nativeSignalSubscription?.cancel() ?? Future<void>.value());
    _nativeSignalSubscription = signals.listen((signal) {
      if (bindingGeneration != _nativeSignalBindingGeneration) {
        return;
      }
      _handleNativePlaybackSignal(signal);
    });
  }

  void _handleNativePlaybackSignal(VideoNativePlaybackSignal signal) {
    final observer = onNativeSignal;
    if (observer != null) {
      unawaited(
        Future<void>.sync(() => observer(signal)).catchError((
          Object error,
          StackTrace stackTrace,
        ) {
          developer.log(
            'native playback diagnostic observer failed',
            name: 'VideoPlaybackSession',
            error: error,
            stackTrace: stackTrace,
          );
        }),
      );
    }
    switch (signal.kind) {
      case VideoNativePlaybackSignalKind.playbackDiagnostics:
        _hasNativePlaybackDiagnostics = true;
        _rendererMode = signal.rendererMode;
        _decoderQueueMode = signal.decoderQueueMode;
        _decoderFallbackEnabled = signal.decoderFallbackEnabled;
        _notify();
      case VideoNativePlaybackSignalKind.renderedFirstFrame:
        final ttffMs = signal.ttffMs;
        if (_ttffMs == null && ttffMs != null && ttffMs >= 0) {
          _ttffMs = ttffMs;
          _notify();
        }
      case VideoNativePlaybackSignalKind.seekSettled:
        final pendingTarget = _pendingSeekTarget;
        final pendingGeneration = _pendingSeekGeneration;
        final pendingStartedAt = _pendingSeekStartedAt;
        if (pendingTarget == null ||
            pendingGeneration == null ||
            pendingStartedAt == null ||
            pendingGeneration != _generation) {
          return;
        }
        final targetMs = signal.targetPositionMs;
        // Android 会回传原生 seek 调用时记录的精确目标；必须严格相等，避免旧 seek
        // 的渲染帧错误结算相邻的新目标，进而把陈旧帧写成 QoE 证据。
        if (targetMs == null || targetMs != pendingTarget.inMilliseconds) {
          return;
        }
        final settledPositionMs = signal.settledPositionMs;
        if (settledPositionMs != null &&
            (settledPositionMs - pendingTarget.inMilliseconds).abs() > 2000) {
          return;
        }
        final settleMs = signal.settleMs;
        if (settleMs == null || settleMs < 0) {
          return;
        }
        if (_pendingSeekPurpose == _VideoSeekPurpose.sourceSwitch) {
          final requestId = _pendingSeekRequestId;
          if (requestId == null) {
            return;
          }
          _completeSourceSwitchSeek(
            requestId: requestId,
            generation: pendingGeneration,
            result: VideoSourceSwitchSeekResult(
              outcome: VideoSourceSwitchSeekOutcome.nativeSettled,
              target: pendingTarget,
              observedPosition: Duration(
                milliseconds: settledPositionMs ?? pendingTarget.inMilliseconds,
              ),
              elapsedMs: settleMs,
              evidenceCapability:
                  _pendingSourceSwitchSeekEvidenceCapability ??
                  VideoSeekSettleEvidenceCapability.nativeRenderedFrame,
            ),
          );
          return;
        }
        _seekSettleMaxMs = settleMs > _seekSettleMaxMs
            ? settleMs
            : _seekSettleMaxMs;
        _seekEvidenceSource = AppTelemetryValueSeekEvidenceSource.nativeSettled;
        _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
          phase: VideoSeekLifecyclePhase.commandCompleted,
          target: pendingTarget,
          generation: pendingGeneration,
          elapsedMs: settleMs,
          hasNativeSettleEvidence: true,
        );
        _lastStablePosition = Duration(
          milliseconds: settledPositionMs ?? pendingTarget.inMilliseconds,
        );
        _runtimeFailure = null;
        _clearPendingSeek();
        _notify();
      case VideoNativePlaybackSignalKind.droppedVideoFrames:
        final droppedFrames = signal.droppedFrames;
        if (droppedFrames == null || droppedFrames <= 0) {
          return;
        }
        _hasNativePlaybackDiagnostics = true;
        _droppedFrames += droppedFrames;
        _notify();
      case VideoNativePlaybackSignalKind.audioUnderrun:
        _hasNativePlaybackDiagnostics = true;
        _audioUnderrunCount += 1;
        _notify();
      case VideoNativePlaybackSignalKind.videoFrameProcessing:
        final processedFrames = signal.processedFrames;
        if (processedFrames == null || processedFrames <= 0) {
          return;
        }
        _hasNativePlaybackDiagnostics = true;
        _processedVideoFrames += processedFrames;
        _notify();
    }
  }

  bool _isCurrentPendingSeek({
    required int requestId,
    required int generation,
  }) {
    return _pendingSeekRequestId == requestId &&
        _pendingSeekGeneration == generation;
  }

  bool _hasNativeSettleForSeek({
    required Duration target,
    required int generation,
  }) {
    final event = _lastSeekLifecycleEvent;
    return event != null &&
        event.generation == generation &&
        event.target == target &&
        event.hasNativeSettleEvidence;
  }

  void _clearPendingSeek({int? requestId}) {
    if (requestId != null && _pendingSeekRequestId != requestId) {
      return;
    }
    final terminalCompleter = _pendingSeekTerminalCompleter;
    _pendingSeekStartedAt = null;
    _pendingSeekTarget = null;
    _pendingSeekGeneration = null;
    _pendingSeekRequestId = null;
    _pendingSeekPurpose = null;
    _pendingSeekTerminalCompleter = null;
    _pendingSourceSwitchSeekCompleter = null;
    _pendingSourceSwitchSeekEvidenceCapability = null;
    if (terminalCompleter != null && !terminalCompleter.isCompleted) {
      terminalCompleter.complete();
    }
  }

  void _startRebuffering() {
    _rebufferStartedAt ??= DateTime.now();
  }

  void _stopRebuffering() {
    final startedAt = _rebufferStartedAt;
    if (startedAt == null) {
      return;
    }
    _rebufferMs += DateTime.now().difference(startedAt).inMilliseconds;
    _rebufferCount += 1;
    _rebufferStartedAt = null;
  }

  void _settleEffectivePlaybackInterval() {
    final startedAt = _effectivePlaybackStartedAt;
    if (startedAt == null) {
      return;
    }
    final elapsedMs = _now().difference(startedAt).inMilliseconds;
    if (elapsedMs > 0) {
      _effectivePlayMs += elapsedMs;
    }
    _effectivePlaybackStartedAt = null;
  }

  void _startEffectivePlaybackIntervalIfEligible() {
    final value = _controller?.value;
    if (_effectivePlaybackStartedAt != null ||
        value == null ||
        !value.isInitialized ||
        !value.isPlaying ||
        value.isBuffering ||
        _scrubTarget != null ||
        !_isVisible ||
        !_isForeground) {
      return;
    }
    _effectivePlaybackStartedAt = _now();
  }

  int? _toPositiveMilliseconds(Duration? duration) {
    if (duration == null || duration <= Duration.zero) {
      return null;
    }
    return duration.inMilliseconds;
  }

  bool? _durationMismatch(Duration? declared, Duration? observed) {
    if (declared == null ||
        observed == null ||
        declared <= Duration.zero ||
        observed <= Duration.zero) {
      return null;
    }
    final difference = (declared.inMilliseconds - observed.inMilliseconds)
        .abs();
    final toleranceMs = (declared.inMilliseconds * 2 ~/ 100) < 1000
        ? 1000
        : declared.inMilliseconds * 2 ~/ 100;
    return difference > toleranceMs;
  }

  void _notify() {
    if (!hasListeners) {
      return;
    }
    notifyListeners();
  }
}
