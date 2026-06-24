part of 'home_multi_form_feed.dart';

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

  @override
  void initState() {
    super.initState();
    widget.scrollSignal.addListener(_handleSignalChanged);
    WidgetsBinding.instance.addPostFrameCallback((_) => _evaluate());
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    final coordinator = _HomeFeedVideoFocusScope.maybeOf(context);
    if (!identical(coordinator, _focusCoordinator)) {
      _focusCoordinator?.removeListener(_handleFocusChanged);
      _focusCoordinator = coordinator;
      _focusCoordinator?.addListener(_handleFocusChanged);
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _evaluate();
      });
    }
  }

  @override
  void didUpdateWidget(covariant _HomeFeedVideoAutoPlayGate oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!identical(widget.scrollSignal, oldWidget.scrollSignal)) {
      oldWidget.scrollSignal.removeListener(_handleSignalChanged);
      widget.scrollSignal.addListener(_handleSignalChanged);
    }
    if (widget.videoId != oldWidget.videoId) {
      _focusCoordinator?.withdraw(oldWidget.videoId);
    }
    if (widget.hasPlayableSource != oldWidget.hasPlayableSource ||
        widget.videoId != oldWidget.videoId) {
      WidgetsBinding.instance.addPostFrameCallback((_) => _evaluate());
    }
  }

  @override
  void dispose() {
    _recheckTimer?.cancel();
    widget.scrollSignal.removeListener(_handleSignalChanged);
    _focusCoordinator?.removeListener(_handleFocusChanged);
    _focusCoordinator?.withdraw(widget.videoId);
    super.dispose();
  }

  void _handleSignalChanged() {
    _evaluate();
  }

  void _handleFocusChanged() {
    // 协调器活跃卡片变化：仅据缓存的本地意愿 + 是否活跃刷新播放态，不重新申报，
    // 避免 report -> notify -> report 的反馈环。
    _applyFocus();
  }

  void _evaluate() {
    if (!mounted) return;
    _recheckTimer?.cancel();
    final now = DateTime.now();
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
      if (wait > Duration.zero) {
        _recheckTimer = Timer(wait, _evaluate);
      }
    }
  }

  void _recordFastScrollSuppressed({
    required double visibleFraction,
    required double velocityPxPerSecond,
    required Duration cooldownRemaining,
  }) {
    final now = DateTime.now();
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
    if (!mounted) return;
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
    if (renderObject is! RenderBox || !renderObject.hasSize) {
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
