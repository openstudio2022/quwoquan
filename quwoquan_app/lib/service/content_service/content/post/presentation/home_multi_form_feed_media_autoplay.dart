part of 'home_multi_form_feed.dart';

@visibleForTesting
typedef HomeFeedVideoScrollSignalForTesting = _HomeFeedVideoScrollSignal;

/// 只暴露真实 gate 的输入与播放意图，不创建媒体、数据源或环境 fixture。
@visibleForTesting
Widget homeFeedVideoAutoPlayGateForTesting({
  required GlobalKey key,
  required String videoId,
  required ValueListenable<HomeFeedVideoScrollSignalForTesting> scrollSignal,
  required HomeFeedVideoFocusCoordinator coordinator,
  required DateTime Function() now,
  required Widget Function(bool initialize, bool autoPlay) builder,
  bool hasPlayableSource = true,
}) => _HomeFeedVideoFocusScope(
  coordinator: coordinator,
  child: _HomeFeedVideoAutoPlayGate(
    key: key,
    videoId: videoId,
    scrollSignal: scrollSignal,
    hasPlayableSource: hasPlayableSource,
    now: now,
    onFastScrollSuppressed: (_) {},
    builder: (playback) => builder(playback.initialize, playback.autoPlay),
  ),
);

class _HomeFeedVideoAutoPlayGateState
    extends State<_HomeFeedVideoAutoPlayGate> {
  final GlobalKey _measureKey = GlobalKey();
  Timer? _recheckTimer;
  DateTime? _prewarmVisibleSince;
  DateTime? _visibleSince;
  _HomeFeedVideoPlaybackState _playback =
      const _HomeFeedVideoPlaybackState.idle();
  // 单活跃视频协调器（feed 范围共享）；本地「想初始化/想播放」的意愿缓存，
  // 仅在协调器授予活跃资格时才真正生效，保证任意时刻 ≤1 个视频解码器存活。
  HomeFeedVideoFocusCoordinator? _focusCoordinator;
  bool _localWantsInitialize = false;
  bool _localWantsAutoPlay = false;
  DateTime? _lastFastScrollSuppressionLoggedAt;

  bool _isActive = true;
  int _generation = 0;
  bool _evaluationScheduled = false;
  bool _focusUpdateScheduled = false;

  @override
  void initState() {
    super.initState();
    widget.scrollSignal.addListener(_handleSignalChanged);
    _scheduleEvaluation();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final coordinator = _HomeFeedVideoFocusScope.maybeOf(context);
    if (!identical(coordinator, _focusCoordinator)) {
      _resetQualification();
      _releaseFocus();
      _focusCoordinator = coordinator;
      _focusCoordinator?.addListener(_handleFocusChanged);
    }
    _scheduleEvaluation();
  }

  @override
  void didUpdateWidget(covariant _HomeFeedVideoAutoPlayGate oldWidget) {
    super.didUpdateWidget(oldWidget);
    final signalChanged = !identical(
      widget.scrollSignal,
      oldWidget.scrollSignal,
    );
    if (signalChanged && _isActive) {
      oldWidget.scrollSignal.removeListener(_handleSignalChanged);
      widget.scrollSignal.addListener(_handleSignalChanged);
    }
    if (signalChanged ||
        widget.videoId != oldWidget.videoId ||
        widget.hasPlayableSource != oldWidget.hasPlayableSource) {
      _resetQualification();
      _focusCoordinator?.withdraw(oldWidget.videoId);
    }
    _scheduleEvaluation();
  }

  @override
  void deactivate() {
    // mounted 在离树后、dispose 前仍为 true，必须先封住回调再同步撤回焦点。
    _isActive = false;
    widget.scrollSignal.removeListener(_handleSignalChanged);
    _resetQualification();
    _releaseFocus();
    super.deactivate();
  }

  @override
  void activate() {
    super.activate();
    _isActive = true;
    widget.scrollSignal.addListener(_handleSignalChanged);
    // inherited scope 由随后的 didChangeDependencies 重新绑定，不沿用旧父树。
    _scheduleEvaluation();
  }

  @override
  void dispose() {
    if (_isActive) {
      widget.scrollSignal.removeListener(_handleSignalChanged);
    }
    _isActive = false;
    _resetQualification();
    _releaseFocus();
    super.dispose();
  }

  void _resetQualification() {
    _generation++;
    _evaluationScheduled = false;
    _focusUpdateScheduled = false;
    _recheckTimer?.cancel();
    _recheckTimer = null;
    _prewarmVisibleSince = null;
    _visibleSince = null;
    _localWantsInitialize = false;
    _localWantsAutoPlay = false;
    _playback = const _HomeFeedVideoPlaybackState.idle();
  }

  void _releaseFocus() {
    final coordinator = _focusCoordinator;
    _focusCoordinator = null;
    coordinator?.removeListener(_handleFocusChanged);
    coordinator?.withdraw(widget.videoId);
  }

  void _scheduleEvaluation() {
    if (!_isActive || !mounted || _evaluationScheduled) return;
    _evaluationScheduled = true;
    final generation = _generation;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_isActive || !mounted || generation != _generation) return;
      _evaluationScheduled = false;
      _evaluate();
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _handleSignalChanged() {
    if (!_isActive || !mounted) return;
    _recheckTimer?.cancel();
    _recheckTimer = null;
    final signal = widget.scrollSignal.value;
    if (signal.isDragging ||
        signal.isScrolling ||
        signal.velocityPxPerSecond.abs() >
            homeFeedVideoAutoPlayMaxVelocityPxPerSecond) {
      // 暂停意图同步生效，几何可以合帧，但不得等帧后测量才请求暂停。
      _localWantsAutoPlay = false;
      _applyFocus();
    }
    _scheduleEvaluation();
  }

  void _handleFocusChanged() {
    // 只消费缓存意图，不重新 report，避免焦点通知反馈环。
    _applyFocus();
  }

  void _evaluate() {
    if (!_isActive || !mounted) return;
    _recheckTimer?.cancel();
    _recheckTimer = null;
    final now = widget.now();
    final visibleFraction = _visibleFraction();
    final isPrewarmVisible =
        visibleFraction >= homeFeedVideoPrewarmMinVisibleFraction;
    final isVisibleEnough =
        visibleFraction >= homeFeedVideoAutoPlayMinVisibleFraction;
    if (!isPrewarmVisible) {
      _prewarmVisibleSince = null;
    } else {
      _prewarmVisibleSince ??= now;
    }
    if (!isVisibleEnough) {
      _visibleSince = null;
    } else {
      _visibleSince ??= now;
    }
    final prewarmStableDuration = _prewarmVisibleSince == null
        ? Duration.zero
        : now.difference(_prewarmVisibleSince!);
    final stableDuration = _visibleSince == null
        ? Duration.zero
        : now.difference(_visibleSince!);
    final signal = widget.scrollSignal.value;
    final timeSinceScrollEnd = signal.lastScrollEndAt == null
        ? homeFeedVideoAutoPlayScrollEndDebounce
        : now.difference(signal.lastScrollEndAt!);
    final timeSinceHighVelocity = signal.lastHighVelocityAt == null
        ? homeFeedVideoFastScrollCooldown
        : now.difference(signal.lastHighVelocityAt!);
    final nextAutoPlay = shouldAutoPlayHomeFeedVideo(
      HomeFeedVideoAutoPlayInput(
        hasPlayableSource: widget.hasPlayableSource,
        visibleFraction: visibleFraction,
        stableVisibleDuration: stableDuration,
        scrollVelocityPxPerSecond: signal.velocityPxPerSecond,
        isUserDragging: signal.isDragging,
        isScrolling: signal.isScrolling,
        timeSinceScrollEnd: timeSinceScrollEnd,
        timeSinceHighVelocity: timeSinceHighVelocity,
      ),
    );
    final canStartInitialize =
        widget.hasPlayableSource &&
        isPrewarmVisible &&
        prewarmStableDuration >=
            homeFeedVideoAutoPlayMinStableVisibleDuration &&
        !signal.isDragging &&
        !signal.isScrolling &&
        timeSinceScrollEnd >= homeFeedVideoAutoPlayScrollEndDebounce &&
        timeSinceHighVelocity >= homeFeedVideoFastScrollCooldown &&
        signal.velocityPxPerSecond.abs() <=
            homeFeedVideoFastScrollVelocityPxPerSecond;
    final fastScrollSuppressed = shouldSuppressHomeFeedVideoFastScroll(
      HomeFeedVideoFastScrollSuppressionInput(
        hasPlayableSource: widget.hasPlayableSource,
        visibleFraction: visibleFraction,
        prewarmStableVisibleDuration: prewarmStableDuration,
        scrollVelocityPxPerSecond: signal.velocityPxPerSecond,
        timeSinceHighVelocity: timeSinceHighVelocity,
      ),
    );
    if (!canStartInitialize && fastScrollSuppressed) {
      _recordFastScrollSuppressed(
        visibleFraction: visibleFraction,
        velocityPxPerSecond: signal.velocityPxPerSecond,
        cooldownRemaining:
            homeFeedVideoFastScrollCooldown - timeSinceHighVelocity,
      );
    }
    final shouldRetainInitialized =
        _playback.initialize &&
        widget.hasPlayableSource &&
        visibleFraction >= homeFeedVideoRetainInitializedMinVisibleFraction;
    // 本地是否「想初始化/想播放」——最终是否真正初始化/播放，由协调器单活跃仲裁决定。
    _localWantsInitialize =
        nextAutoPlay || canStartInitialize || shouldRetainInitialized;
    _localWantsAutoPlay = nextAutoPlay;
    final coordinator = _focusCoordinator;
    if (coordinator != null) {
      if (_localWantsInitialize) {
        coordinator.report(widget.videoId, visibleFraction);
      } else {
        coordinator.withdraw(widget.videoId);
      }
    }
    _applyFocus();
    if (!nextAutoPlay && isPrewarmVisible && widget.hasPlayableSource) {
      final stableRemaining =
          homeFeedVideoAutoPlayMinStableVisibleDuration - stableDuration;
      final prewarmStableRemaining =
          homeFeedVideoAutoPlayMinStableVisibleDuration - prewarmStableDuration;
      final scrollRemaining =
          homeFeedVideoAutoPlayScrollEndDebounce - timeSinceScrollEnd;
      final fastScrollRemaining =
          homeFeedVideoFastScrollCooldown - timeSinceHighVelocity;
      final wait = _positiveMaxDuration(
        stableRemaining,
        prewarmStableRemaining,
        scrollRemaining,
        fastScrollRemaining,
      );
      if (wait > Duration.zero) _scheduleRecheck(wait);
    }
  }

  void _scheduleRecheck(Duration wait) {
    final generation = _generation;
    _recheckTimer = Timer(wait, () {
      if (!_isActive || !mounted || generation != _generation) return;
      _recheckTimer = null;
      _scheduleEvaluation();
    });
  }

  void _recordFastScrollSuppressed({
    required double visibleFraction,
    required double velocityPxPerSecond,
    required Duration cooldownRemaining,
  }) {
    final now = widget.now();
    final last = _lastFastScrollSuppressionLoggedAt;
    if (last != null && now.difference(last) < const Duration(seconds: 1)) {
      return;
    }
    _lastFastScrollSuppressionLoggedAt = now;
    widget.onFastScrollSuppressed(
      homeFeedVideoFastScrollSuppressedTelemetryAttributes(
        videoId: widget.videoId,
        visibleFraction: visibleFraction,
        velocityPxPerSecond: velocityPxPerSecond,
        cooldownRemaining: cooldownRemaining,
      ),
    );
  }

  void _applyFocus() {
    if (!_isActive || !mounted) return;
    // withdraw 可发生于兄弟的 deactivate/build/layout；安全帧后再消费最新意图，
    // 不捕获旧播放状态，也不在框架树锁定时 setState。
    if (WidgetsBinding.instance.schedulerPhase == .persistentCallbacks) {
      if (_focusUpdateScheduled) return;
      _focusUpdateScheduled = true;
      final generation = _generation;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!_isActive || !mounted || generation != _generation) return;
        _focusUpdateScheduled = false;
        _applyFocus();
      });
      return;
    }
    final coordinator = _focusCoordinator;
    // 协调器缺失时（理论上不出现于首页 feed）退化为本地判定，保持组件可用。
    final isActive =
        coordinator == null || coordinator.isActive(widget.videoId);
    final nextPlayback = _HomeFeedVideoPlaybackState(
      initialize: _localWantsInitialize && isActive,
      autoPlay: _localWantsAutoPlay && isActive,
    );
    if (nextPlayback.initialize != _playback.initialize ||
        nextPlayback.autoPlay != _playback.autoPlay) {
      setState(() => _playback = nextPlayback);
    }
  }

  Duration _positiveMaxDuration(
    Duration a,
    Duration b,
    Duration c,
    Duration d,
  ) {
    final candidates = <Duration>[
      if (a > Duration.zero) a,
      if (b > Duration.zero) b,
      if (c > Duration.zero) c,
      if (d > Duration.zero) d,
    ];
    if (candidates.isEmpty) return Duration.zero;
    return candidates.reduce(
      (value, element) => value > element ? value : element,
    );
  }

  double _visibleFraction() {
    final context = _measureKey.currentContext;
    if (context == null) return AppSpacing.zero;
    final renderObject = context.findRenderObject();
    if (renderObject is! RenderBox ||
        !renderObject.attached ||
        !renderObject.hasSize) {
      return AppSpacing.zero;
    }
    final height = renderObject.size.height;
    if (height <= AppSpacing.zero) return AppSpacing.zero;
    final top = renderObject.localToGlobal(Offset.zero).dy;
    final bottom = top + height;
    final viewportHeight = MediaQuery.sizeOf(context).height;
    final visibleHeight =
        (min(bottom, viewportHeight) - max(top, AppSpacing.zero)).clamp(
          AppSpacing.zero,
          height,
        );
    return visibleHeight / height;
  }

  @override
  Widget build(BuildContext context) {
    return KeyedSubtree(key: _measureKey, child: widget.builder(_playback));
  }
}
