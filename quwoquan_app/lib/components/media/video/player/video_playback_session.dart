import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:video_player/video_player.dart';

/// 播放传输状态。页面只渲染该语义状态，不能自行从原生 controller 推导第二套状态。
enum VideoPlaybackTransport {
  initializing,
  ready,
  playing,
  paused,
  scrubbing,
  buffering,
  ended,
  failure,
}

/// 播放来源意图。用户暂停必须始终压过自动播放与生命周期恢复。
enum VideoPlaybackIntent {
  autoEligible,
  manualPlay,
  manualPause,
  interrupted,
  awaitingUserGesture,
}

/// 控制层的显示策略。
enum VideoPlaybackControlsVisibility { hidden, transient, pinned }

/// 暂停原因仅用于状态收敛、可观测和恢复判断，不直接展示给用户。
enum VideoPlaybackPauseReason {
  user,
  focusLost,
  offscreen,
  appLifecycle,
  audioInterruption,
  episodeChange,
  failure,
}

/// 一个原生播放 controller 生命周期内的匿名 QoE 汇总。
///
/// 该对象刻意不带内容、推荐或用户归因；这些字段属于行为链路，不得进入 Ops
/// 产品遥测。首期 Flutter 插件不提供可信首帧事件，因此不提供或伪造 TTFF。
@immutable
class VideoPlaybackQoeSummary {
  const VideoPlaybackQoeSummary({
    required this.readyMs,
    required this.rebufferCount,
    required this.rebufferMs,
    required this.seekCount,
    required this.playbackMode,
    required this.result,
    this.declaredDurationMs,
    this.observedDurationMs,
    this.durationMismatch,
    this.failReasonCode,
  });

  final int readyMs;
  final int rebufferCount;
  final int rebufferMs;
  final int seekCount;
  final String playbackMode;
  final String result;
  final int? declaredDurationMs;
  final int? observedDurationMs;
  final bool? durationMismatch;
  final String? failReasonCode;
}

/// 一个播放会话的唯一渲染输入。
@immutable
class VideoPlaybackSnapshot {
  const VideoPlaybackSnapshot({
    required this.transport,
    required this.intent,
    required this.controlsVisibility,
    required this.position,
    required this.duration,
    required this.isInitialized,
    required this.isPlaying,
    required this.isBuffering,
    required this.hasController,
    required this.generation,
    this.pauseReason,
    this.scrubTarget,
    this.verifiedDuration,
  });

  final VideoPlaybackTransport transport;
  final VideoPlaybackIntent intent;
  final VideoPlaybackControlsVisibility controlsVisibility;
  final Duration position;
  final Duration duration;
  final bool isInitialized;
  final bool isPlaying;
  final bool isBuffering;
  final bool hasController;
  final int generation;
  final VideoPlaybackPauseReason? pauseReason;
  final Duration? scrubTarget;
  final Duration? verifiedDuration;

  bool get isScrubbing => transport == VideoPlaybackTransport.scrubbing;

  bool get isEnded => transport == VideoPlaybackTransport.ended;

  bool get canSeek => duration > Duration.zero && isInitialized;

  double get progress {
    if (!canSeek) {
      return 0;
    }
    return position.inMilliseconds / duration.inMilliseconds;
  }

  Duration get effectivePosition => scrubTarget ?? position;
}

/// 播放控制的单一命令入口。
///
/// 原生 controller 由视频 surface 创建并在销毁时释放；任何页面、时间轴或浏览器
/// 控件只能通过本对象播放、暂停和 seek，从而避免 WorkBrowser 与播放器重复控制。
class VideoPlaybackSession extends ChangeNotifier {
  VideoPlaybackSession({
    this.transientControlsDuration = const Duration(seconds: 5),
  });

  final Duration transientControlsDuration;

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
  int _generation = 0;
  Timer? _controlsTimer;
  int? _readyMs;
  int _rebufferCount = 0;
  int _rebufferMs = 0;
  DateTime? _rebufferStartedAt;
  int _seekCount = 0;
  String _playbackMode = 'manual';

  VideoPlaybackSnapshot get snapshot {
    final value = _controller?.value;
    final initialized = value?.isInitialized ?? false;
    final nativeDuration = initialized ? value!.duration : Duration.zero;
    final duration = nativeDuration > Duration.zero
        ? nativeDuration
        : (_verifiedDuration ?? Duration.zero);
    final position = initialized ? value!.position : Duration.zero;
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
    );
  }

  void attach(
    VideoPlayerController controller, {
    Duration? verifiedDuration,
    int? readyMs,
  }) {
    if (identical(_controller, controller)) {
      _verifiedDuration = verifiedDuration ?? _verifiedDuration;
      _readyMs = readyMs ?? _readyMs;
      _notify();
      return;
    }
    _detachListener();
    _controller = controller;
    _lastKnownPlaying = controller.value.isPlaying;
    _verifiedDuration = verifiedDuration ?? _verifiedDuration;
    _hasFailure = false;
    _readyMs = readyMs;
    _rebufferCount = 0;
    _rebufferMs = 0;
    _rebufferStartedAt = controller.value.isBuffering ? DateTime.now() : null;
    _seekCount = 0;
    _playbackMode = _autoEligible ? 'autoplay' : 'manual';
    _generation += 1;
    controller.addListener(_handleControllerValueChanged);
    _syncAutomaticPlayback();
    _notify();
  }

  void detach(VideoPlayerController controller) {
    if (!identical(_controller, controller)) {
      return;
    }
    _detachListener();
    _stopRebuffering();
    _controller = null;
    _lastKnownPlaying = false;
    _scrubTarget = null;
    _wasPlayingBeforeScrub = false;
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
    _isVisible = visible;
    if (!visible) {
      _pauseFor(VideoPlaybackPauseReason.offscreen);
    } else {
      _syncAutomaticPlayback();
    }
    _notify();
  }

  void setForeground(bool foreground) {
    if (_isForeground == foreground) {
      return;
    }
    _isForeground = foreground;
    if (!foreground) {
      _pauseFor(VideoPlaybackPauseReason.appLifecycle);
    } else {
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
    _wasPlayingBeforeScrub = current.isPlaying;
    _scrubTarget = current.position;
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

  Future<void> endScrub({bool commit = true}) async {
    final target = _scrubTarget;
    final shouldResume =
        _wasPlayingBeforeScrub && _intent != VideoPlaybackIntent.manualPause;
    _scrubTarget = null;
    _wasPlayingBeforeScrub = false;
    if (commit && target != null) {
      _seekCount += 1;
      await _controller?.seekTo(target);
    }
    if (shouldResume &&
        _isForeground &&
        _isVisible &&
        (_autoEligible || _intent == VideoPlaybackIntent.manualPlay)) {
      await _controller?.play();
    }
    if (snapshot.isPlaying) {
      showTransientControls();
    } else {
      _controlsVisibility = VideoPlaybackControlsVisibility.pinned;
    }
    _notify();
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
    final value = _controller?.value;
    final isPlaying = value?.isPlaying ?? false;
    if (value?.isBuffering ?? false) {
      _startRebuffering();
    } else {
      _stopRebuffering();
    }
    final startedPlaying = isPlaying && !_lastKnownPlaying;
    _lastKnownPlaying = isPlaying;
    if (startedPlaying &&
        _controlsVisibility == VideoPlaybackControlsVisibility.hidden) {
      showTransientControls();
      return;
    }
    _notify();
  }

  void _detachListener() {
    _controller?.removeListener(_handleControllerValueChanged);
  }

  /// 构造匿名 QoE 汇总并保持会话可继续使用；调用者可在 controller 释放前调用。
  VideoPlaybackQoeSummary takeQoeSummary({
    String result = 'success',
    String? failReasonCode,
  }) {
    _stopRebuffering();
    final observedDuration = _controller?.value.isInitialized ?? false
        ? _controller!.value.duration
        : null;
    final declaredDuration = _verifiedDuration;
    return VideoPlaybackQoeSummary(
      readyMs: _readyMs ?? 0,
      rebufferCount: _rebufferCount,
      rebufferMs: _rebufferMs,
      seekCount: _seekCount,
      playbackMode: _playbackMode,
      result: result,
      declaredDurationMs: _toPositiveMilliseconds(declaredDuration),
      observedDurationMs: _toPositiveMilliseconds(observedDuration),
      durationMismatch: _durationMismatch(declaredDuration, observedDuration),
      failReasonCode: failReasonCode,
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
    _controlsTimer?.cancel();
    _detachListener();
    _controller = null;
    super.dispose();
  }
}
