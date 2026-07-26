import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/cloud/content/generated/content_errors.g.dart';
import 'package:quwoquan_app/core/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/components/media/video/player/video_playback_session_models.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

export 'package:quwoquan_app/components/media/video/player/video_playback_session_models.dart';

/// 播放控制的单一命令入口。
///
/// 原生 controller 由视频 surface 创建并在销毁时释放；任何页面、时间轴或浏览器
/// 控件只能通过本对象播放、暂停和 seek，从而避免 WorkBrowser 与播放器重复控制。
class VideoPlaybackSession extends ChangeNotifier {
  VideoPlaybackSession({
    this.transientControlsDuration = const Duration(seconds: 5),
    this.onNativeSignal,
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now,
       playbackSessionId =
           'video-${DateTime.now().toUtc().microsecondsSinceEpoch}-${_nextSessionId++}';

  static int _nextSessionId = 1;
  final Duration transientControlsDuration;
  final VideoNativeSignalObserver? onNativeSignal;
  final DateTime Function() _now;
  final String playbackSessionId;

  VideoPlayerController? _controller;
  Duration? _verifiedDuration;
  VideoPlaybackIntent _intent = VideoPlaybackIntent.interrupted;
  VideoPlaybackControlsVisibility _controlsVisibility =
      VideoPlaybackControlsVisibility.hidden;
  VideoPlaybackPauseReason? _pauseReason;
  Duration? _scrubTarget;
  bool _wasPlayingBeforeScrub = false;
  bool _isVisible = true;
  bool _isForeground = true;
  bool _autoEligible = false;
  bool _lastKnownPlaying = false;
  bool _hasFailure = false;
  Duration _lastStablePosition = Duration.zero;
  RuntimeFailure? _runtimeFailure;
  VideoSeekLifecycleEvent? _lastSeekLifecycleEvent;
  int _generation = 0;
  Timer? _controlsTimer;
  int? _readyMs;
  int _rebufferCount = 0;
  int _rebufferMs = 0;
  DateTime? _rebufferStartedAt;
  int _seekCount = 0;
  int _seekFailureCount = 0;
  int _seekCommandMaxMs = 0;
  int _seekSettleMaxMs = 0;
  int? _ttffMs;
  int _droppedFrames = 0;
  int _processedVideoFrames = 0;
  int _audioUnderrunCount = 0;
  bool _hasNativePlaybackDiagnostics = false;
  String? _rendererMode;
  String? _decoderQueueMode;
  bool? _decoderFallbackEnabled;
  String _seekEvidenceSource = 'controller_command_completion';
  String _playbackMode = 'manual';
  DateTime? _effectivePlaybackStartedAt;
  int _effectivePlayMs = 0;
  DateTime? _pendingSeekStartedAt;
  Duration? _pendingSeekTarget;
  int? _pendingSeekGeneration;
  int _nextSeekRequestId = 0;
  int? _pendingSeekRequestId;
  StreamSubscription<VideoNativePlaybackSignal>? _nativeSignalSubscription;
  int _nativeSignalBindingGeneration = 0;

  VideoPlaybackSnapshot get snapshot {
    final value = _controller?.value;
    final initialized = value?.isInitialized ?? false;
    final nativeDuration = initialized ? value!.duration : Duration.zero;
    final duration = nativeDuration > Duration.zero
        ? nativeDuration
        : (_verifiedDuration ?? Duration.zero);
    final position = initialized
        ? (value!.isBuffering ? _lastStablePosition : value.position)
        : Duration.zero;
    final isPlaying = initialized && value!.isPlaying;
    final isBuffering = initialized && value!.isBuffering;
    return VideoPlaybackSnapshot(
      transport: _resolveTransport(
        initialized: initialized,
        duration: duration,
        position: position,
        isPlaying: isPlaying,
        isBuffering: isBuffering,
      ),
      intent: _intent,
      controlsVisibility: _controlsVisibility,
      position: position,
      duration: duration,
      isInitialized: initialized,
      isPlaying: isPlaying,
      isBuffering: isBuffering,
      hasController: _controller != null,
      generation: _generation,
      pauseReason: _pauseReason,
      scrubTarget: _scrubTarget,
      verifiedDuration: _verifiedDuration,
      runtimeFailure: _runtimeFailure,
      lastSeekLifecycleEvent: _lastSeekLifecycleEvent,
    );
  }

  /// 真正由平台 renderer 确认过首帧；controller initialize 不能代替。
  bool get hasNativeFirstFrameEvidence => _ttffMs != null;

  /// 当前一次 release seek 已收到原生 discontinuity 后的渲染帧。
  bool get hasNativeSeekSettleEvidence =>
      _lastSeekLifecycleEvent?.hasNativeSettleEvidence ?? false;

  /// 仅在当前 release seek 已有 native settle 时暴露对应目标。
  Duration? get nativeSeekSettledTarget {
    final event = _lastSeekLifecycleEvent;
    if (event == null || !event.hasNativeSettleEvidence) {
      return null;
    }
    return event.target;
  }

  void attach(
    VideoPlayerController controller, {
    Duration? verifiedDuration,
    int? readyMs,
    Stream<VideoNativePlaybackSignal>? nativeSignals,
  }) {
    if (identical(_controller, controller)) {
      _verifiedDuration = verifiedDuration ?? _verifiedDuration;
      _readyMs = readyMs ?? _readyMs;
      _notify();
      return;
    }
    _settleEffectivePlaybackInterval();
    _detachListener();
    _controller = controller;
    _lastKnownPlaying = controller.value.isPlaying;
    _verifiedDuration = verifiedDuration ?? _verifiedDuration;
    _hasFailure = false;
    _runtimeFailure = null;
    _lastSeekLifecycleEvent = null;
    _lastStablePosition = controller.value.isInitialized
        ? controller.value.position
        : Duration.zero;
    _readyMs = readyMs;
    _rebufferCount = 0;
    _rebufferMs = 0;
    _rebufferStartedAt = controller.value.isBuffering ? DateTime.now() : null;
    _seekCount = 0;
    _seekFailureCount = 0;
    _seekCommandMaxMs = 0;
    _seekSettleMaxMs = 0;
    _ttffMs = null;
    _droppedFrames = 0;
    _processedVideoFrames = 0;
    _audioUnderrunCount = 0;
    _hasNativePlaybackDiagnostics = false;
    _rendererMode = null;
    _decoderQueueMode = null;
    _decoderFallbackEnabled = null;
    _seekEvidenceSource = 'controller_command_completion';
    _pendingSeekStartedAt = null;
    _pendingSeekTarget = null;
    _pendingSeekGeneration = null;
    _pendingSeekRequestId = null;
    _effectivePlaybackStartedAt = null;
    _effectivePlayMs = 0;
    _playbackMode = _autoEligible ? 'autoplay' : 'manual';
    _generation += 1;
    controller.addListener(_handleControllerValueChanged);
    _bindNativeSignals(
      nativeSignals ?? const Stream<VideoNativePlaybackSignal>.empty(),
    );
    _startEffectivePlaybackIntervalIfEligible();
    _syncAutomaticPlayback();
    _notify();
  }

  void detach(VideoPlayerController controller) {
    if (!identical(_controller, controller)) {
      return;
    }
    _settleEffectivePlaybackInterval();
    _detachListener();
    _stopRebuffering();
    _controller = null;
    _lastKnownPlaying = false;
    _scrubTarget = null;
    _wasPlayingBeforeScrub = false;
    _lastStablePosition = Duration.zero;
    _runtimeFailure = null;
    _lastSeekLifecycleEvent = null;
    _pendingSeekStartedAt = null;
    _pendingSeekTarget = null;
    _pendingSeekGeneration = null;
    _pendingSeekRequestId = null;
    _generation += 1;
    _notify();
  }

  void setVerifiedDuration(Duration? duration) {
    _verifiedDuration = duration != null && duration > Duration.zero
        ? duration
        : null;
    _notify();
  }

  void markFailure() {
    _hasFailure = true;
    _intent = VideoPlaybackIntent.interrupted;
    _pauseReason = VideoPlaybackPauseReason.failure;
    _scrubTarget = null;
    _controlsTimer?.cancel();
    _controlsVisibility = VideoPlaybackControlsVisibility.hidden;
    _notify();
  }

  /// 首页焦点仲裁或分集 settle 后设置自动播放资格。
  void setAutomaticPlaybackEligible(bool eligible) {
    _autoEligible = eligible;
    if (eligible && _intent != VideoPlaybackIntent.manualPause) {
      _intent = VideoPlaybackIntent.autoEligible;
      _pauseReason = null;
    } else if (!eligible && _intent == VideoPlaybackIntent.autoEligible) {
      _intent = VideoPlaybackIntent.interrupted;
      _pauseReason = VideoPlaybackPauseReason.focusLost;
    }
    _syncAutomaticPlayback();
    _notify();
  }

  void setVisibility(bool visible) {
    if (_isVisible == visible) {
      return;
    }
    _settleEffectivePlaybackInterval();
    _isVisible = visible;
    if (!visible) {
      _pauseFor(VideoPlaybackPauseReason.offscreen);
    } else {
      _startEffectivePlaybackIntervalIfEligible();
      _syncAutomaticPlayback();
    }
    _notify();
  }

  void setForeground(bool foreground) {
    if (_isForeground == foreground) {
      return;
    }
    _settleEffectivePlaybackInterval();
    _isForeground = foreground;
    if (!foreground) {
      _pauseFor(VideoPlaybackPauseReason.appLifecycle);
    } else {
      _startEffectivePlaybackIntervalIfEligible();
      _syncAutomaticPlayback();
    }
    _notify();
  }

  Future<void> toggle() async {
    if (snapshot.isPlaying) {
      await pauseByUser();
    } else {
      await playByUser();
    }
  }

  Future<void> playByUser() async {
    _intent = VideoPlaybackIntent.manualPlay;
    _pauseReason = null;
    _scrubTarget = null;
    if (snapshot.isEnded) {
      final controller = _controller;
      final generation = _generation;
      await controller?.seekTo(Duration.zero);
      if (!identical(controller, _controller) || generation != _generation) {
        return;
      }
      _lastStablePosition = Duration.zero;
    }
    await _playIfAllowed(userInitiated: true);
    showTransientControls();
    _notify();
  }

  Future<void> pauseByUser() async {
    _intent = VideoPlaybackIntent.manualPause;
    _pauseReason = VideoPlaybackPauseReason.user;
    _controlsTimer?.cancel();
    _controlsVisibility = VideoPlaybackControlsVisibility.pinned;
    await _controller?.pause();
    _notify();
  }

  Future<void> beginScrub() async {
    final current = snapshot;
    if (!current.canSeek) {
      return;
    }
    _settleEffectivePlaybackInterval();
    _wasPlayingBeforeScrub = current.isPlaying;
    _scrubTarget = current.position;
    _runtimeFailure = null;
    _controlsTimer?.cancel();
    _controlsVisibility = VideoPlaybackControlsVisibility.pinned;
    await _controller?.pause();
    _notify();
  }

  void updateScrubTarget(Duration target) {
    final duration = snapshot.duration;
    if (duration <= Duration.zero) {
      return;
    }
    _scrubTarget = _clampDuration(target, duration);
    _notify();
  }

  /// 无障碍与键盘的固定步长 seek，仍复用同一 scrub/seek 状态机。
  Future<void> seekRelative(Duration delta) async {
    final current = snapshot;
    if (!current.canSeek) {
      return;
    }
    await beginScrub();
    updateScrubTarget(current.position + delta);
    await endScrub();
  }

  Future<void> endScrub({bool commit = true}) async {
    final target = _scrubTarget;
    final shouldResume =
        _wasPlayingBeforeScrub && _intent != VideoPlaybackIntent.manualPause;
    final controller = _controller;
    final generation = _generation;
    _scrubTarget = null;
    _wasPlayingBeforeScrub = false;
    if (commit && target != null && controller != null) {
      final seekRequestId = ++_nextSeekRequestId;
      _seekCount += 1;
      _pendingSeekStartedAt = _now();
      _pendingSeekTarget = target;
      _pendingSeekGeneration = generation;
      _pendingSeekRequestId = seekRequestId;
      _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
        phase: VideoSeekLifecyclePhase.requested,
        target: target,
        generation: generation,
        elapsedMs: 0,
        hasNativeSettleEvidence: false,
      );
      _notify();
      final stopwatch = Stopwatch()..start();
      try {
        await controller.seekTo(target);
        stopwatch.stop();
        if (!identical(controller, _controller) || generation != _generation) {
          if (_isCurrentPendingSeek(
            requestId: seekRequestId,
            generation: generation,
          )) {
            _clearPendingSeek(requestId: seekRequestId);
            _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
              phase: VideoSeekLifecyclePhase.superseded,
              target: target,
              generation: generation,
              elapsedMs: stopwatch.elapsedMilliseconds,
              hasNativeSettleEvidence: false,
            );
            _notify();
          }
          return;
        }
        // 原生 rendered-frame settle 可能先于平台方法响应送达；必须保留更强的
        // 原生证据，不能被命令完成覆盖，同时仍要继续执行下方的 release-seek 恢复。
        if (_isCurrentPendingSeek(
          requestId: seekRequestId,
          generation: generation,
        )) {
          _seekCommandMaxMs = stopwatch.elapsedMilliseconds > _seekCommandMaxMs
              ? stopwatch.elapsedMilliseconds
              : _seekCommandMaxMs;
          _lastStablePosition = target;
          _runtimeFailure = null;
          _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
            phase: VideoSeekLifecyclePhase.commandCompleted,
            target: target,
            generation: generation,
            elapsedMs: stopwatch.elapsedMilliseconds,
            hasNativeSettleEvidence: false,
          );
        } else if (!_hasNativeSettleForSeek(
          target: target,
          generation: generation,
        )) {
          return;
        }
      } catch (error, stackTrace) {
        stopwatch.stop();
        developer.log(
          'video seek command failed',
          name: 'VideoPlaybackSession',
          error: error,
          stackTrace: stackTrace,
        );
        if (_isCurrentPendingSeek(
          requestId: seekRequestId,
          generation: generation,
        )) {
          _clearPendingSeek(requestId: seekRequestId);
          if (!identical(controller, _controller) ||
              generation != _generation) {
            return;
          }
          _seekFailureCount += 1;
          _seekCommandMaxMs = stopwatch.elapsedMilliseconds > _seekCommandMaxMs
              ? stopwatch.elapsedMilliseconds
              : _seekCommandMaxMs;
          _runtimeFailure = _seekRuntimeFailure(generation);
          _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
            phase: VideoSeekLifecyclePhase.failed,
            target: target,
            generation: generation,
            elapsedMs: stopwatch.elapsedMilliseconds,
            hasNativeSettleEvidence: false,
          );
        } else if (!_hasNativeSettleForSeek(
          target: target,
          generation: generation,
        )) {
          return;
        }
      }
    }
    if (shouldResume &&
        _isForeground &&
        _isVisible &&
        (_autoEligible || _intent == VideoPlaybackIntent.manualPlay)) {
      await controller?.play();
    }
    if (snapshot.isPlaying) {
      showTransientControls();
    } else {
      _controlsVisibility = VideoPlaybackControlsVisibility.pinned;
    }
    _notify();
  }

  RuntimeFailure _seekRuntimeFailure(int generation) {
    final errorCode = ContentErrorCode.mediaSeekFailed;
    return RuntimeFailure(
      code: errorCode.code,
      semanticReason: 'seek_command_failed',
      transportStatus: errorCode.httpStatus,
      origin: RuntimeFailureOrigin.localClient,
      kind: RuntimeFailureKind.unavailable,
      nature: RuntimeFailureNature.transient,
      location: const RuntimeFailureLocation(
        businessObject: 'content.post',
        functionModule: 'video_playback_seek',
      ),
      context: RuntimeFailureContext(
        attributes: <RuntimeContextAttribute>[
          RuntimeContextAttribute(
            key: 'sessionGeneration',
            value: generation.toString(),
          ),
          const RuntimeContextAttribute(
            key: 'evidenceSource',
            value: 'controller_command_completion',
          ),
        ],
      ),
      recovery: RuntimeRecoveryDirective(
        action: errorCode.recoveryAction,
        afterSeconds: errorCode.recoveryAfterSeconds,
      ),
    );
  }

  void showTransientControls() {
    _controlsTimer?.cancel();
    _controlsVisibility = VideoPlaybackControlsVisibility.transient;
    _controlsTimer = Timer(transientControlsDuration, () {
      if (_controlsVisibility == VideoPlaybackControlsVisibility.transient &&
          snapshot.isPlaying) {
        _controlsVisibility = VideoPlaybackControlsVisibility.hidden;
        _notify();
      }
    });
    _notify();
  }

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
        _seekSettleMaxMs = settleMs > _seekSettleMaxMs
            ? settleMs
            : _seekSettleMaxMs;
        _seekEvidenceSource = 'native_settled';
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
    _pendingSeekStartedAt = null;
    _pendingSeekTarget = null;
    _pendingSeekGeneration = null;
    _pendingSeekRequestId = null;
  }

  /// 构造匿名 QoE 汇总并保持会话可继续使用；调用者可在 controller 释放前调用。
  VideoPlaybackQoeSummary takeQoeSummary({
    String result = 'success',
    String? failReasonCode,
  }) {
    _stopRebuffering();
    _settleEffectivePlaybackInterval();
    final observedDuration = _controller?.value.isInitialized ?? false
        ? _controller!.value.duration
        : null;
    final declaredDuration = _verifiedDuration;
    return VideoPlaybackQoeSummary(
      readyMs: _readyMs ?? 0,
      rebufferCount: _rebufferCount,
      rebufferMs: _rebufferMs,
      effectivePlaybackMs: _effectivePlayMs,
      seekCount: _seekCount,
      seekFailureCount: _seekFailureCount,
      seekCommandMaxMs: _seekCommandMaxMs,
      seekSettleMaxMs: _seekSettleMaxMs,
      seekEvidenceSource: _seekEvidenceSource,
      playbackMode: _playbackMode,
      result: result,
      ttffMs: _ttffMs,
      droppedFrames: _hasNativePlaybackDiagnostics ? _droppedFrames : null,
      processedVideoFrames: _hasNativePlaybackDiagnostics
          ? _processedVideoFrames
          : null,
      audioUnderrunCount: _hasNativePlaybackDiagnostics
          ? _audioUnderrunCount
          : null,
      rendererMode: _rendererMode,
      decoderQueueMode: _decoderQueueMode,
      decoderFallbackEnabled: _decoderFallbackEnabled,
      declaredDurationMs: _toPositiveMilliseconds(declaredDuration),
      observedDurationMs: _toPositiveMilliseconds(observedDuration),
      durationMismatch: _durationMismatch(declaredDuration, observedDuration),
      failReasonCode: failReasonCode,
    );
  }

  VideoEffectivePlaybackEvidence takeEffectivePlaybackEvidence() {
    _settleEffectivePlaybackInterval();
    final current = snapshot;
    final durationMs = current.duration.inMilliseconds;
    final ratio = durationMs <= 0
        ? 0.0
        : (current.position.inMilliseconds / durationMs).clamp(0.0, 1.0);
    return VideoEffectivePlaybackEvidence(
      playbackSessionId: playbackSessionId,
      effectivePlayMs: _effectivePlayMs,
      consumedRatio: ratio,
      totalUnits: durationMs <= 0 ? 0 : (durationMs / 1000).round(),
    );
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

  @override
  void dispose() {
    _settleEffectivePlaybackInterval();
    _controlsTimer?.cancel();
    _detachListener();
    _clearPendingSeek();
    _controller = null;
    super.dispose();
  }
}
