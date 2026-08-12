import 'dart:async';
import 'dart:developer' as developer;

import 'package:flutter/foundation.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/runtime/errors/generated/content/content_errors.g.dart';
import 'package:quwoquan_app/runtime/observability/generated/app_telemetry_catalog.g.dart';
import 'package:quwoquan_app/runtime/shell/loading/app_request_wait_controller.dart';
import 'package:quwoquan_app/runtime/platform/video_native_playback_signals.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session_models.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

export 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_playback_session_models.dart';

part 'video_playback_session_seek_support.dart';
part 'video_playback_session_seek_internals.dart';
part 'video_playback_session_runtime_internals.dart';

/// 播放控制的单一命令入口。
///
/// 原生 controller 由视频 surface 创建并在销毁时释放；任何页面、时间轴或浏览器
/// 控件只能通过本对象播放、暂停和 seek，从而避免 WorkBrowser 与播放器重复控制。
class VideoPlaybackSession extends ChangeNotifier {
  VideoPlaybackSession({
    this.transientControlsDuration = const Duration(seconds: 5),
    this.seekCommandTimeout = AppRequestWaitTimings.foregroundReadDeadline,
    this.onNativeSignal,
    DateTime Function()? now,
  }) : _now = now ?? DateTime.now,
       playbackSessionId =
           'video-${DateTime.now().toUtc().microsecondsSinceEpoch}-${_nextSessionId++}';

  static int _nextSessionId = 1;
  static const Duration _sourceSwitchReadbackPollInterval = Duration(
    milliseconds: 40,
  );
  final Duration transientControlsDuration;
  final Duration seekCommandTimeout;
  final VideoNativeSignalObserver? onNativeSignal;
  final DateTime Function() _now;
  final String playbackSessionId;
  final _VideoSeekCommandAdmission _seekCommandAdmission =
      _VideoSeekCommandAdmission();

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
  VideoSourceSwitchSeekResult? _lastSourceSwitchSeekResult;
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
  String _seekEvidenceSource =
      AppTelemetryValueSeekEvidenceSource.controllerCommandCompletion;
  String _playbackMode = 'manual';
  DateTime? _effectivePlaybackStartedAt;
  int _effectivePlayMs = 0;
  DateTime? _pendingSeekStartedAt;
  Duration? _pendingSeekTarget;
  int? _pendingSeekGeneration;
  int _nextSeekRequestId = 0;
  int? _pendingSeekRequestId;
  _VideoSeekPurpose? _pendingSeekPurpose;
  Completer<void>? _pendingSeekTerminalCompleter;
  Completer<VideoSourceSwitchSeekResult>? _pendingSourceSwitchSeekCompleter;
  VideoSeekSettleEvidenceCapability? _pendingSourceSwitchSeekEvidenceCapability;
  Completer<void> _controllerEpochTerminalCompleter = Completer<void>();
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
      lastSourceSwitchSeekResult: _lastSourceSwitchSeekResult,
    );
  }

  /// 真正由平台 renderer 确认过首帧；controller initialize 不能代替。
  bool get hasNativeFirstFrameEvidence => _ttffMs != null;

  /// 当前一次 release seek 已收到原生 discontinuity 后的渲染帧。
  bool get hasNativeSeekSettleEvidence =>
      _lastSeekLifecycleEvent?.hasNativeSettleEvidence ?? false;

  @visibleForTesting
  int get debugUnresolvedPhysicalSeekControllerCount =>
      _seekCommandAdmission.unresolvedControllerCount;

  @visibleForTesting
  int get debugUnresolvedPhysicalSeekCommandCount =>
      _seekCommandAdmission.totalUnresolved;

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
    bool synchronizeAutomaticPlayback = true,
  }) {
    if (identical(_controller, controller)) {
      _verifiedDuration = verifiedDuration ?? _verifiedDuration;
      _readyMs = readyMs ?? _readyMs;
      _notify();
      return;
    }
    _supersedePendingSeek();
    _advanceControllerEpoch();
    _settleEffectivePlaybackInterval();
    _detachListener();
    _controller = controller;
    _lastKnownPlaying = controller.value.isPlaying;
    _verifiedDuration = verifiedDuration ?? _verifiedDuration;
    _hasFailure = false;
    _runtimeFailure = null;
    _lastSeekLifecycleEvent = null;
    _lastSourceSwitchSeekResult = null;
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
    _seekEvidenceSource =
        AppTelemetryValueSeekEvidenceSource.controllerCommandCompletion;
    _pendingSeekStartedAt = null;
    _pendingSeekTarget = null;
    _pendingSeekGeneration = null;
    _pendingSeekRequestId = null;
    _pendingSeekPurpose = null;
    _pendingSeekTerminalCompleter = null;
    _pendingSourceSwitchSeekCompleter = null;
    _pendingSourceSwitchSeekEvidenceCapability = null;
    _effectivePlaybackStartedAt = null;
    _effectivePlayMs = 0;
    _playbackMode = _autoEligible ? 'autoplay' : 'manual';
    _generation += 1;
    controller.addListener(_handleControllerValueChanged);
    _bindNativeSignals(
      nativeSignals ?? const Stream<VideoNativePlaybackSignal>.empty(),
    );
    _startEffectivePlaybackIntervalIfEligible();
    if (synchronizeAutomaticPlayback) {
      _syncAutomaticPlayback();
    }
    _notify();
  }

  void detach(VideoPlayerController controller) {
    if (!identical(_controller, controller)) {
      return;
    }
    _supersedePendingSeek();
    _advanceControllerEpoch();
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
    _lastSourceSwitchSeekResult = null;
    _pendingSeekStartedAt = null;
    _pendingSeekTarget = null;
    _pendingSeekGeneration = null;
    _pendingSeekRequestId = null;
    _pendingSeekPurpose = null;
    _pendingSeekTerminalCompleter = null;
    _pendingSourceSwitchSeekCompleter = null;
    _pendingSourceSwitchSeekEvidenceCapability = null;
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
      if (controller == null) {
        return;
      }
      final generation = _generation;
      final deadline = _VideoSeekDeadline(seekCommandTimeout);
      _seekCount += 1;
      _seekEvidenceSource =
          AppTelemetryValueSeekEvidenceSource.controllerCommandCompletion;
      _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
        phase: VideoSeekLifecyclePhase.requested,
        target: Duration.zero,
        generation: generation,
        elapsedMs: 0,
        hasNativeSettleEvidence: false,
      );
      _notify();
      final waitResult = await _waitForPhysicalSeekCommand(
        controller: controller,
        target: Duration.zero,
        terminal: _controllerEpochTerminalCompleter.future,
        deadline: deadline,
      );
      if (waitResult.disposition == _VideoSeekWaitDisposition.terminal ||
          !identical(controller, _controller) ||
          generation != _generation) {
        return;
      }
      if (waitResult.disposition == _VideoSeekWaitDisposition.completed) {
        _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
            ? deadline.elapsedMs
            : _seekCommandMaxMs;
        _lastStablePosition = Duration.zero;
        _runtimeFailure = null;
        _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
          phase: VideoSeekLifecyclePhase.commandCompleted,
          target: Duration.zero,
          generation: generation,
          elapsedMs: deadline.elapsedMs,
          hasNativeSettleEvidence: false,
        );
      } else {
        final timedOut =
            waitResult.disposition ==
            _VideoSeekWaitDisposition.deadlineExceeded;
        final capacityExceeded =
            waitResult.disposition ==
            _VideoSeekWaitDisposition.capacityExceeded;
        developer.log(
          capacityExceeded
              ? 'video replay seek command rejected: '
                    'unresolved command capacity reached'
              : timedOut
              ? 'video replay seek command timed out'
              : 'video replay seek command failed',
          name: 'VideoPlaybackSession',
          error: waitResult.error,
          stackTrace: waitResult.stackTrace,
        );
        _seekFailureCount += 1;
        if (!capacityExceeded) {
          _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
              ? deadline.elapsedMs
              : _seekCommandMaxMs;
        }
        _runtimeFailure = _seekRuntimeFailure(
          generation,
          semanticReason: capacityExceeded
              ? 'seek_command_capacity_exceeded'
              : timedOut
              ? 'seek_command_timeout'
              : 'seek_command_failed',
        );
        _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
          phase: capacityExceeded
              ? VideoSeekLifecyclePhase.commandCapacityExceeded
              : timedOut
              ? VideoSeekLifecyclePhase.commandTimedOut
              : VideoSeekLifecyclePhase.failed,
          target: Duration.zero,
          generation: generation,
          elapsedMs: deadline.elapsedMs,
          hasNativeSettleEvidence: false,
        );
        _notify();
        return;
      }
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
      _supersedePendingSeek();
      final seekRequestId = ++_nextSeekRequestId;
      final terminalCompleter = Completer<void>();
      _seekCount += 1;
      _pendingSeekStartedAt = _now();
      _pendingSeekTarget = target;
      _pendingSeekGeneration = generation;
      _pendingSeekRequestId = seekRequestId;
      _pendingSeekPurpose = _VideoSeekPurpose.userRelease;
      _pendingSeekTerminalCompleter = terminalCompleter;
      _pendingSourceSwitchSeekCompleter = null;
      _seekEvidenceSource =
          AppTelemetryValueSeekEvidenceSource.controllerCommandCompletion;
      _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
        phase: VideoSeekLifecyclePhase.requested,
        target: target,
        generation: generation,
        elapsedMs: 0,
        hasNativeSettleEvidence: false,
      );
      _notify();
      final deadline = _VideoSeekDeadline(seekCommandTimeout);
      final waitResult = await _waitForPhysicalSeekCommand(
        controller: controller,
        target: target,
        terminal: terminalCompleter.future,
        deadline: deadline,
      );
      switch (waitResult.disposition) {
        case _VideoSeekWaitDisposition.completed:
          if (!identical(controller, _controller) ||
              generation != _generation) {
            if (_isCurrentPendingSeek(
              requestId: seekRequestId,
              generation: generation,
            )) {
              _clearPendingSeek(requestId: seekRequestId);
              _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
                phase: VideoSeekLifecyclePhase.superseded,
                target: target,
                generation: generation,
                elapsedMs: deadline.elapsedMs,
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
            _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
                ? deadline.elapsedMs
                : _seekCommandMaxMs;
            _lastStablePosition = target;
            _runtimeFailure = null;
            _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
              phase: VideoSeekLifecyclePhase.commandCompleted,
              target: target,
              generation: generation,
              elapsedMs: deadline.elapsedMs,
              hasNativeSettleEvidence: false,
            );
          } else if (!_hasNativeSettleForSeek(
            target: target,
            generation: generation,
          )) {
            return;
          }
        case _VideoSeekWaitDisposition.failed:
          developer.log(
            'video seek command failed',
            name: 'VideoPlaybackSession',
            error: waitResult.error,
            stackTrace: waitResult.stackTrace,
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
            _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
                ? deadline.elapsedMs
                : _seekCommandMaxMs;
            _runtimeFailure = _seekRuntimeFailure(generation);
            _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
              phase: VideoSeekLifecyclePhase.failed,
              target: target,
              generation: generation,
              elapsedMs: deadline.elapsedMs,
              hasNativeSettleEvidence: false,
            );
          } else if (!_hasNativeSettleForSeek(
            target: target,
            generation: generation,
          )) {
            return;
          }
        case _VideoSeekWaitDisposition.deadlineExceeded:
          developer.log(
            'video seek command timed out',
            name: 'VideoPlaybackSession',
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
            _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
                ? deadline.elapsedMs
                : _seekCommandMaxMs;
            _runtimeFailure = _seekRuntimeFailure(
              generation,
              semanticReason: 'seek_command_timeout',
            );
            _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
              phase: VideoSeekLifecyclePhase.commandTimedOut,
              target: target,
              generation: generation,
              elapsedMs: deadline.elapsedMs,
              hasNativeSettleEvidence: false,
            );
          } else if (!_hasNativeSettleForSeek(
            target: target,
            generation: generation,
          )) {
            return;
          }
        case _VideoSeekWaitDisposition.capacityExceeded:
          developer.log(
            'video seek command rejected: unresolved command capacity reached',
            name: 'VideoPlaybackSession',
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
            _runtimeFailure = _seekRuntimeFailure(
              generation,
              semanticReason: 'seek_command_capacity_exceeded',
            );
            _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
              phase: VideoSeekLifecyclePhase.commandCapacityExceeded,
              target: target,
              generation: generation,
              elapsedMs: deadline.elapsedMs,
              hasNativeSettleEvidence: false,
            );
          } else if (!_hasNativeSettleForSeek(
            target: target,
            generation: generation,
          )) {
            return;
          }
        case _VideoSeekWaitDisposition.terminal:
          if (!_hasNativeSettleForSeek(
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

  /// 同资产播放源切换后的唯一位置恢复入口。
  ///
  /// 调用方必须先 [attach] 新 controller；Android 等已声明原生能力的
  /// 平台只在 discontinuity 后的渲染帧信号到达时计为 native settle。
  /// 其他平台只能进行 controller position readback，结果会显式保留
  /// native unsupported 边界。
  Future<VideoSourceSwitchSeekResult> restoreSourceSwitchPosition(
    Duration target, {
    required VideoSeekSettleEvidenceCapability evidenceCapability,
    Duration settleTimeout = const Duration(seconds: 2),
    Duration readbackTolerance = const Duration(seconds: 2),
  }) async {
    final controller = _controller;
    final generation = _generation;
    final tolerance = readbackTolerance >= Duration.zero
        ? readbackTolerance
        : Duration.zero;
    _seekCount += 1;

    if (controller == null ||
        !controller.value.isInitialized ||
        target <= Duration.zero) {
      final result = VideoSourceSwitchSeekResult(
        outcome: VideoSourceSwitchSeekOutcome.settleUnsupported,
        target: target,
        elapsedMs: 0,
        evidenceCapability: evidenceCapability,
      );
      _recordSourceSwitchSeekResult(result, generation: generation);
      return result;
    }

    _supersedePendingSeek();

    final seekRequestId = ++_nextSeekRequestId;
    final completer = Completer<VideoSourceSwitchSeekResult>();
    final terminalCompleter = Completer<void>();
    _pendingSeekStartedAt = _now();
    _pendingSeekTarget = target;
    _pendingSeekGeneration = generation;
    _pendingSeekRequestId = seekRequestId;
    _pendingSeekPurpose = _VideoSeekPurpose.sourceSwitch;
    _pendingSeekTerminalCompleter = terminalCompleter;
    _pendingSourceSwitchSeekCompleter = completer;
    _pendingSourceSwitchSeekEvidenceCapability = evidenceCapability;
    _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
      phase: VideoSeekLifecyclePhase.requested,
      target: target,
      generation: generation,
      elapsedMs: 0,
      hasNativeSettleEvidence: false,
    );
    _notify();

    final deadline = _VideoSeekDeadline(settleTimeout);
    final commandWait = await _waitForPhysicalSeekCommand(
      controller: controller,
      target: target,
      terminal: terminalCompleter.future,
      deadline: deadline,
    );
    if (commandWait.disposition == _VideoSeekWaitDisposition.terminal ||
        completer.isCompleted) {
      return completer.future;
    }
    if (!identical(controller, _controller) || generation != _generation) {
      final result = _sourceSwitchSupersededResult(
        target: target,
        elapsedMs: deadline.elapsedMs,
        evidenceCapability: evidenceCapability,
      );
      if (!completer.isCompleted) {
        completer.complete(result);
      }
      return result;
    }
    if (commandWait.disposition == _VideoSeekWaitDisposition.failed ||
        commandWait.disposition == _VideoSeekWaitDisposition.deadlineExceeded ||
        commandWait.disposition == _VideoSeekWaitDisposition.capacityExceeded) {
      final timedOut =
          commandWait.disposition == _VideoSeekWaitDisposition.deadlineExceeded;
      final capacityExceeded =
          commandWait.disposition == _VideoSeekWaitDisposition.capacityExceeded;
      developer.log(
        capacityExceeded
            ? 'video source-switch seek command rejected: '
                  'unresolved command capacity reached'
            : timedOut
            ? 'video source-switch seek command timed out'
            : 'video source-switch seek command failed',
        name: 'VideoPlaybackSession',
        error: commandWait.error,
        stackTrace: commandWait.stackTrace,
      );
      _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
          ? deadline.elapsedMs
          : _seekCommandMaxMs;
      final result = VideoSourceSwitchSeekResult(
        outcome: capacityExceeded
            ? VideoSourceSwitchSeekOutcome.commandCapacityExceeded
            : timedOut
            ? VideoSourceSwitchSeekOutcome.commandTimedOut
            : VideoSourceSwitchSeekOutcome.commandFailed,
        target: target,
        elapsedMs: deadline.elapsedMs,
        evidenceCapability: evidenceCapability,
      );
      _completeSourceSwitchSeek(
        requestId: seekRequestId,
        generation: generation,
        result: result,
      );
      return result;
    }
    _seekCommandMaxMs = deadline.elapsedMs > _seekCommandMaxMs
        ? deadline.elapsedMs
        : _seekCommandMaxMs;
    _runtimeFailure = null;
    _lastSeekLifecycleEvent = VideoSeekLifecycleEvent(
      phase: VideoSeekLifecyclePhase.commandCompleted,
      target: target,
      generation: generation,
      elapsedMs: deadline.elapsedMs,
      hasNativeSettleEvidence: false,
    );
    _notify();

    if (evidenceCapability ==
        VideoSeekSettleEvidenceCapability.nativeRenderedFrame) {
      final settleWait = await _waitForSeekOperation(
        operation: completer.future.then<Object?>((value) => value),
        terminal: terminalCompleter.future,
        deadline: deadline,
      );
      if (settleWait.disposition == _VideoSeekWaitDisposition.completed) {
        return settleWait.value! as VideoSourceSwitchSeekResult;
      }
      if (settleWait.disposition == _VideoSeekWaitDisposition.terminal ||
          completer.isCompleted) {
        return completer.future;
      }
      if (!identical(controller, _controller) || generation != _generation) {
        final result = _sourceSwitchSupersededResult(
          target: target,
          elapsedMs: deadline.elapsedMs,
          evidenceCapability: evidenceCapability,
        );
        if (!completer.isCompleted) {
          completer.complete(result);
        }
        return result;
      }
      final result = VideoSourceSwitchSeekResult(
        outcome: VideoSourceSwitchSeekOutcome.nativeSettleTimedOut,
        target: target,
        observedPosition: controller.value.position,
        elapsedMs: deadline.elapsedMs,
        evidenceCapability: evidenceCapability,
      );
      _completeSourceSwitchSeek(
        requestId: seekRequestId,
        generation: generation,
        result: result,
      );
      return result;
    }

    final result = await _waitForSourceSwitchPositionReadback(
      controller: controller,
      generation: generation,
      target: target,
      tolerance: tolerance,
      deadline: deadline,
      terminal: terminalCompleter.future,
      evidenceCapability: evidenceCapability,
    );
    if (completer.isCompleted) {
      return completer.future;
    }
    if (result.outcome == VideoSourceSwitchSeekOutcome.superseded) {
      if (!completer.isCompleted) {
        completer.complete(result);
      }
      return result;
    }
    _completeSourceSwitchSeek(
      requestId: seekRequestId,
      generation: generation,
      result: result,
    );
    return result;
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

  /// 构造匿名 QoE 汇总并保持会话可继续使用；调用者可在 controller 释放前调用。
  VideoPlaybackQoeSummary takeQoeSummary({
    String result = 'success',
    String? failReasonCode,
  }) {
    // QoE 是 controller 释放前的最终快照。source-switch 必须在 report 前收口；
    // 普通 release seek 的 command 已完成后仍可等待更强 native frame 证据，不能
    // 因中途读取 QoE 就提前清除。controller 释放则统一由 detach/dispose supersede。
    if (_pendingSeekPurpose == _VideoSeekPurpose.sourceSwitch) {
      _supersedePendingSeek(notifyListeners: false);
    }
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

  @override
  void dispose() {
    _settleEffectivePlaybackInterval();
    _controlsTimer?.cancel();
    _detachListener();
    _supersedePendingSeek(notifyListeners: false);
    _advanceControllerEpoch(renew: false);
    _controller = null;
    super.dispose();
  }
}
