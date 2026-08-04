// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

typedef _HomeFeedItemBuilder =
    Widget Function(
      int index,
      ValueListenable<_HomeFeedVideoScrollSignal> videoScrollSignal,
    );

/// 多列瀑布每段卡数：段尾由 sliver 边界天然两列齐平，段间可插入交集模块。
const int _kFeedSegmentSize = 10;

/// 变长列表无法直接 scroll-to-index；恢复过程每帧只做一次布局反馈寻址。
/// 12 次足以覆盖首个 index 比例粗定位及多轮可见 marker 几何校正，同时保持有界。
const int _kHomeFeedAnchorRestoreMaxAttempts = 12;

class _HomeFeedVideoScrollSignal {
  const _HomeFeedVideoScrollSignal({
    required this.isDragging,
    required this.isScrolling,
    required this.velocityPxPerSecond,
    required this.lastScrollEndAt,
    required this.lastHighVelocityAt,
    required this.revision,
  });

  factory _HomeFeedVideoScrollSignal.initial() {
    return const _HomeFeedVideoScrollSignal(
      isDragging: false,
      isScrolling: false,
      velocityPxPerSecond: AppSpacing.zero,
      lastScrollEndAt: null,
      lastHighVelocityAt: null,
      revision: 0,
    );
  }

  final bool isDragging;
  final bool isScrolling;
  final double velocityPxPerSecond;
  final DateTime? lastScrollEndAt;
  final DateTime? lastHighVelocityAt;
  final int revision;

  _HomeFeedVideoScrollSignal copyWith({
    required bool isDragging,
    required bool isScrolling,
    required double velocityPxPerSecond,
    DateTime? lastScrollEndAt,
    DateTime? lastHighVelocityAt,
  }) {
    return _HomeFeedVideoScrollSignal(
      isDragging: isDragging,
      isScrolling: isScrolling,
      velocityPxPerSecond: velocityPxPerSecond,
      lastScrollEndAt: lastScrollEndAt,
      lastHighVelocityAt: lastHighVelocityAt,
      revision: revision + 1,
    );
  }
}

/// 把 feed 范围内唯一的 [HomeFeedVideoFocusCoordinator] 暴露给子树中的视频卡片，
/// 保证整张瀑布流共享同一个单活跃仲裁器（任意时刻 ≤1 个视频解码器存活）。
class _HomeFeedVideoFocusScope extends InheritedWidget {
  const _HomeFeedVideoFocusScope({
    required this.coordinator,
    required super.child,
  });

  final HomeFeedVideoFocusCoordinator coordinator;

  static HomeFeedVideoFocusCoordinator? maybeOf(BuildContext context) {
    return context
        .dependOnInheritedWidgetOfExactType<_HomeFeedVideoFocusScope>()
        ?.coordinator;
  }

  @override
  bool updateShouldNotify(_HomeFeedVideoFocusScope oldWidget) =>
      !identical(coordinator, oldWidget.coordinator);
}

class _HomeFeedScrollView extends StatefulWidget {
  const _HomeFeedScrollView({
    super.key,
    required this.channelId,
    required this.anchorStore,
    required this.entryIdentities,
    required this.pageBackground,
    required this.isDark,
    required this.resourceProfile,
    required this.isMultiColumn,
    required this.columns,
    required this.horizontalPad,
    required this.topPad,
    required this.bottomPad,
    required this.itemCount,
    required this.itemBuilder,
    required this.isFullSpanItem,
    required this.fullSpanBuilder,
    required this.dividerColor,
    required this.isLoadingMore,
    required this.hasMore,
    required this.canRestorePreviousPage,
    required this.appendError,
    required this.staleDataError,
    required this.onRetryInitialLoad,
    required this.onReachBottom,
    required this.onReachTop,
    required this.onResourceSample,
    this.moodCopy = '',
    this.headerSliver,
    this.segmentBuilder,
  });

  final String channelId;
  final HomeFeedScrollAnchorStore anchorStore;
  final List<String> entryIdentities;
  final Color pageBackground;
  final bool isDark;
  final AppResourceCacheProfile resourceProfile;
  final bool isMultiColumn;
  final int columns;
  final double horizontalPad;
  final double topPad;
  final double bottomPad;
  final int itemCount;
  final _HomeFeedItemBuilder itemBuilder;
  final bool Function(int index) isFullSpanItem;
  final _HomeFeedItemBuilder fullSpanBuilder;
  final Color dividerColor;
  final bool isLoadingMore;
  final bool hasMore;
  final bool canRestorePreviousPage;
  final Object? appendError;
  final Object? staleDataError;
  final VoidCallback onRetryInitialLoad;
  final VoidCallback onReachBottom;
  final VoidCallback onReachTop;
  final VoidCallback onResourceSample;

  /// 频道气质文案（来自 ContentUIConfig.homeChannels.moodCopyKey 解析，只读）；空则不展示。
  final String moodCopy;

  /// 顶部 sliver（发现交集横滑流）；null 不展示。
  final Widget? headerSliver;

  /// 多列段间插卡（交集 spotlight / 运营解释模块）；null 不展示。
  final Widget Function(int segmentIndex)? segmentBuilder;

  @override
  State<_HomeFeedScrollView> createState() => _HomeFeedScrollViewState();
}

class _HomeFeedScrollViewState extends State<_HomeFeedScrollView>
    with WidgetsBindingObserver {
  late final ScrollController _controller;
  final GlobalKey _scrollSurfaceKey = GlobalKey();
  final _HomeFeedAnchorMarkerRegistry _anchorMarkers =
      _HomeFeedAnchorMarkerRegistry();
  final ValueNotifier<_HomeFeedVideoScrollSignal> _videoScrollSignal =
      ValueNotifier<_HomeFeedVideoScrollSignal>(
        _HomeFeedVideoScrollSignal.initial(),
      );
  // 整张瀑布流共享的单活跃视频仲裁器：无论挂载多少卡片，至多一个视频初始化解码器。
  final HomeFeedVideoFocusCoordinator _videoFocus =
      HomeFeedVideoFocusCoordinator();
  Timer? _staleNoticeTimer;
  Timer? _videoScrollSettleTimer;
  Object? _visibleStaleDataError;
  double? _lastScrollPixels;
  DateTime? _lastScrollSampleAt;
  HomeFeedScrollAnchor? _pendingRestoredAnchor;
  int _restoreAttempt = 0;
  int _anchorRestoreGeneration = 0;
  int _anchorCaptureGeneration = 0;
  bool _leadingRestoreArmed = false;
  double? _lastLeadingRestorePixels;

  @override
  void initState() {
    super.initState();
    _pendingRestoredAnchor = widget.anchorStore.readRestorable(
      widget.channelId,
      residentEntryIdentities: widget.entryIdentities.toSet(),
    );
    _controller = ScrollController(
      initialScrollOffset: _initialRestoredScrollOffset(_pendingRestoredAnchor),
    );
    WidgetsBinding.instance.addObserver(this);
    _controller.addListener(_onScroll);
    _syncStaleNotice(previous: null);
    _beginAnchorRestore(resetToCoarseOffset: true);
  }

  @override
  void didUpdateWidget(covariant _HomeFeedScrollView oldWidget) {
    super.didUpdateWidget(oldWidget);
    final entriesChanged = !listEquals(
      oldWidget.entryIdentities,
      widget.entryIdentities,
    );
    if (oldWidget.channelId != widget.channelId) {
      _captureAnchor(
        channelId: oldWidget.channelId,
        anchorStore: oldWidget.anchorStore,
      );
      _pendingRestoredAnchor = widget.anchorStore.readRestorable(
        widget.channelId,
        residentEntryIdentities: widget.entryIdentities.toSet(),
      );
      _beginAnchorRestore(resetToCoarseOffset: true);
    } else if (entriesChanged) {
      final anchor = widget.anchorStore.readRestorable(
        widget.channelId,
        residentEntryIdentities: widget.entryIdentities.toSet(),
      );
      if (anchor != null) {
        _pendingRestoredAnchor = anchor;
        _beginAnchorRestore(resetToCoarseOffset: true);
      }
    }
    _syncStaleNotice(previous: oldWidget.staleDataError);
  }

  @override
  void deactivate() {
    // deactivate 发生在 RenderObject 子树仍可用于几何测量的阶段；dispose 时子树
    // 可能已经失活，届时 viewport reveal geometry 已不再可信。
    // 频道切换/路由离开应在这里保存最后一个真实可见条目锚点。
    _captureAnchor();
    super.deactivate();
  }

  @override
  void dispose() {
    _anchorRestoreGeneration += 1;
    _anchorCaptureGeneration += 1;
    WidgetsBinding.instance.removeObserver(this);
    _staleNoticeTimer?.cancel();
    _videoScrollSettleTimer?.cancel();
    _videoScrollSignal.dispose();
    _videoFocus.dispose();
    _controller.removeListener(_onScroll);
    _controller.dispose();
    super.dispose();
  }

  @override
  void didHaveMemoryPressure() {
    // 内存压力下先保存极小锚点元数据。当前 feed widget 离开树时会释放视频
    // coordinator/卡片媒体；Post 引用已由完整页 deque 约束为 6 页，此处不能
    // 再按 item sublist 裁剪，否则会破坏 opaque cursor 页界和本地回滑语义。
    _captureAnchor();
  }

  double _initialRestoredScrollOffset(HomeFeedScrollAnchor? anchor) {
    if (anchor == null) {
      return AppSpacing.zero;
    }
    final currentIndex = widget.entryIdentities.indexOf(
      anchor.stableEntryIdentity,
    );
    if (currentIndex < 0 || anchor.entryIndex <= 0) {
      return max(AppSpacing.zero, anchor.scrollOffset);
    }
    final savedAnchorOffset = anchor.scrollOffset + anchor.viewportOffset;
    if (!savedAnchorOffset.isFinite || savedAnchorOffset <= AppSpacing.zero) {
      return max(AppSpacing.zero, anchor.scrollOffset);
    }
    final estimatedExtentPerEntry = savedAnchorOffset / anchor.entryIndex;
    return max(
      AppSpacing.zero,
      estimatedExtentPerEntry * currentIndex - anchor.viewportOffset,
    );
  }

  void _beginAnchorRestore({required bool resetToCoarseOffset}) {
    _restoreAttempt = 0;
    final generation = ++_anchorRestoreGeneration;
    _scheduleAnchorRestore(
      generation: generation,
      resetToCoarseOffset: resetToCoarseOffset,
    );
  }

  void _scheduleAnchorRestore({
    required int generation,
    bool resetToCoarseOffset = false,
  }) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          generation != _anchorRestoreGeneration ||
          !_controller.hasClients) {
        return;
      }
      final anchor = _pendingRestoredAnchor;
      if (anchor == null) {
        if (resetToCoarseOffset) {
          _controller.jumpTo(_controller.position.minScrollExtent);
        }
        return;
      }
      if (!widget.entryIdentities.contains(anchor.stableEntryIdentity)) {
        _pendingRestoredAnchor = null;
        return;
      }
      if (resetToCoarseOffset) {
        _jumpToAnchorCoarseOffset(anchor);
        _restoreAttempt += 1;
        _scheduleAnchorRestore(generation: generation);
        return;
      }
      if (_restoreAnchorGeometry(anchor)) {
        _pendingRestoredAnchor = null;
        return;
      }
      _restoreAttempt += 1;
      if (_restoreAttempt < _kHomeFeedAnchorRestoreMaxAttempts) {
        _seekTowardAnchor(anchor);
        _scheduleAnchorRestore(generation: generation);
      }
    });
  }

  void _jumpToAnchorCoarseOffset(HomeFeedScrollAnchor anchor) {
    final currentIndex = widget.entryIdentities.indexOf(
      anchor.stableEntryIdentity,
    );
    var coarse = anchor.scrollOffset;
    final savedAnchorOffset = anchor.scrollOffset + anchor.viewportOffset;
    if (currentIndex >= 0 &&
        anchor.entryIndex > 0 &&
        savedAnchorOffset.isFinite &&
        savedAnchorOffset > AppSpacing.zero) {
      final estimatedExtentPerEntry = savedAnchorOffset / anchor.entryIndex;
      coarse = estimatedExtentPerEntry * currentIndex - anchor.viewportOffset;
    }
    _controller.jumpTo(
      coarse.clamp(
        _controller.position.minScrollExtent,
        _controller.position.maxScrollExtent,
      ),
    );
  }

  bool _seekTowardAnchor(HomeFeedScrollAnchor anchor) {
    final targetIndex = widget.entryIdentities.indexOf(
      anchor.stableEntryIdentity,
    );
    if (targetIndex < 0) {
      return false;
    }
    final surface = _scrollSurfaceKey.currentContext?.findRenderObject();
    if (surface is! RenderBox || !surface.attached || !surface.hasSize) {
      return false;
    }
    final currentOffset = _controller.position.pixels;
    final mounted = <_HomeFeedMountedAnchorGeometry>[];
    for (final marker in _anchorMarkers.mountedMarkers) {
      final geometry = marker.geometryInViewport(
        surface,
        scrollOffset: currentOffset,
      );
      if (geometry == null) {
        continue;
      }
      mounted.add(
        _HomeFeedMountedAnchorGeometry(
          marker: marker,
          itemScrollOffset: currentOffset + geometry.top,
          height: geometry.height,
        ),
      );
    }
    if (mounted.isEmpty) {
      return false;
    }
    mounted.sort(
      (left, right) =>
          left.marker.entryIndex.compareTo(right.marker.entryIndex),
    );
    var closest = mounted.first;
    for (final candidate in mounted.skip(1)) {
      if ((candidate.marker.entryIndex - targetIndex).abs() <
          (closest.marker.entryIndex - targetIndex).abs()) {
        closest = candidate;
      }
    }

    final first = mounted.first;
    final last = mounted.last;
    final mountedIndexSpan = last.marker.entryIndex - first.marker.entryIndex;
    final mountedOffsetSpan = (last.itemScrollOffset - first.itemScrollOffset)
        .abs();
    final averageMountedHeight =
        mounted.fold<double>(
          AppSpacing.zero,
          (total, entry) => total + entry.height,
        ) /
        mounted.length;
    final estimatedExtentPerEntry =
        mountedIndexSpan > 0 && mountedOffsetSpan > AppSpacing.hairline
        ? mountedOffsetSpan / mountedIndexSpan
        : averageMountedHeight /
              (widget.isMultiColumn ? max(1, widget.columns) : 1);
    var targetOffset =
        closest.itemScrollOffset +
        (targetIndex - closest.marker.entryIndex) * estimatedExtentPerEntry -
        anchor.viewportOffset;

    final firstIndex = first.marker.entryIndex;
    final lastIndex = last.marker.entryIndex;
    final minimumSeekStep = _controller.position.viewportDimension * 0.75;
    if (targetIndex < firstIndex &&
        targetOffset > currentOffset - minimumSeekStep) {
      targetOffset = currentOffset - minimumSeekStep;
    } else if (targetIndex > lastIndex &&
        targetOffset < currentOffset + minimumSeekStep) {
      targetOffset = currentOffset + minimumSeekStep;
    }
    final clamped = targetOffset.clamp(
      _controller.position.minScrollExtent,
      _controller.position.maxScrollExtent,
    );
    if ((clamped - currentOffset).abs() <= AppSpacing.hairline) {
      return false;
    }
    _controller.jumpTo(clamped);
    return true;
  }

  bool _restoreAnchorGeometry(HomeFeedScrollAnchor anchor) {
    final surface = _scrollSurfaceKey.currentContext?.findRenderObject();
    if (surface is! RenderBox || !surface.attached || !surface.hasSize) {
      return false;
    }
    final marker = _anchorMarkers[anchor.stableEntryIdentity];
    final geometry = marker?.geometryInViewport(
      surface,
      scrollOffset: _controller.position.pixels,
    );
    if (geometry == null) {
      return false;
    }
    final delta = geometry.top - anchor.viewportOffset;
    if (delta.abs() > AppSpacing.hairline) {
      final target = (_controller.offset + delta).clamp(
        _controller.position.minScrollExtent,
        _controller.position.maxScrollExtent,
      );
      _controller.jumpTo(target);
    }
    return true;
  }

  void _captureAnchor({
    String? channelId,
    HomeFeedScrollAnchorStore? anchorStore,
  }) {
    if (!_controller.hasClients) {
      return;
    }
    final surface = _scrollSurfaceKey.currentContext?.findRenderObject();
    if (surface is! RenderBox || !surface.attached || !surface.hasSize) {
      return;
    }
    _HomeFeedAnchorCandidate? best;
    _HomeFeedAnchorCandidate? nearestMountedPost;
    var nearestMountedPostDistance = double.infinity;
    for (final marker in _anchorMarkers.mountedMarkers) {
      // Object cards are an optional, refresh-volatile enhancement. Persisting
      // one as the only anchor makes a later card removal discard the entire
      // channel position. A feed always has Post entries, so capture the
      // nearest mounted Post even while an object card covers the viewport top.
      if (!homeFeedIsPostEntryIdentity(marker.stableEntryIdentity)) {
        continue;
      }
      final geometry = marker.geometryInViewport(
        surface,
        scrollOffset: _controller.position.pixels,
      );
      if (geometry == null) {
        continue;
      }
      final candidate = _HomeFeedAnchorCandidate(
        marker: marker,
        viewportOffset: geometry.top,
      );
      final bottom = geometry.top + geometry.height;
      final isVisible =
          bottom > AppSpacing.zero && geometry.top < surface.size.height;
      if (isVisible) {
        if (best == null || candidate.isPreferredTo(best)) {
          best = candidate;
        }
        continue;
      }
      final distance = bottom <= AppSpacing.zero
          ? -bottom
          : geometry.top - surface.size.height;
      if (distance < nearestMountedPostDistance) {
        nearestMountedPost = candidate;
        nearestMountedPostDistance = distance;
      }
    }
    best ??= nearestMountedPost;
    if (best == null) {
      return;
    }
    (anchorStore ?? widget.anchorStore).save(
      HomeFeedScrollAnchor(
        channelId: channelId ?? widget.channelId,
        stableEntryIdentity: best.marker.stableEntryIdentity,
        entryIndex: best.marker.entryIndex,
        scrollOffset: _controller.offset,
        viewportOffset: best.viewportOffset,
        capturedAt: DateTime.now(),
      ),
    );
  }

  void _scheduleAnchorCapture() {
    final generation = ++_anchorCaptureGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || generation != _anchorCaptureGeneration) {
        return;
      }
      // ScrollEndNotification 在本帧 sliver child 完成回收/挂载之前到达；立即
      // 读取 registry 会看到上一 viewport 的 marker。等布局完成后再保存真实
      // 可见条目，频道切换只消费这个已提交锚点。
      _captureAnchor();
    });
  }

  void _syncStaleNotice({required Object? previous}) {
    final next = widget.staleDataError;
    if (next == null || identical(next, previous)) {
      return;
    }
    _staleNoticeTimer?.cancel();
    _visibleStaleDataError = next;
    _staleNoticeTimer = Timer(const Duration(milliseconds: 2200), () {
      if (!mounted) return;
      setState(() => _visibleStaleDataError = null);
    });
  }

  void _onScroll() {
    if (_visibleStaleDataError != null) {
      setState(() => _visibleStaleDataError = null);
    }
    if (!_controller.hasClients) return;
    final position = _controller.position;
    final previousLeadingPixels = _lastLeadingRestorePixels;
    _lastLeadingRestorePixels = position.pixels;
    final leadingThreshold = position.viewportDimension * 0.5;
    if (position.extentBefore > position.viewportDimension) {
      _leadingRestoreArmed = true;
    } else if (widget.canRestorePreviousPage &&
        _leadingRestoreArmed &&
        previousLeadingPixels != null &&
        position.pixels < previousLeadingPixels &&
        position.extentBefore < leadingThreshold) {
      // prepend 会改变首端 sliver geometry；在状态更新前保存可见 Post，更新后
      // didUpdateWidget 以同 stable identity 恢复其 viewportOffset。
      _leadingRestoreArmed = false;
      _captureAnchor();
      widget.onReachTop();
    }
    if (!widget.hasMore || widget.isLoadingMore) return;
    // 剩余不足半屏即预取下一页（比例系数，非像素间距）。
    if (position.extentAfter < position.viewportDimension * 0.5) {
      // append 超过 resident 页预算时会按完整页裁掉 leading；提前保存底部
      // 可见 Post，避免状态替换后依赖旧 absolute offset。
      _captureAnchor();
      widget.onReachBottom();
    }
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    final now = DateTime.now();
    if (notification is ScrollStartNotification) {
      _videoScrollSettleTimer?.cancel();
      _lastScrollPixels = notification.metrics.pixels;
      _lastScrollSampleAt = now;
      _publishVideoScrollSignal(
        isDragging: notification.dragDetails != null,
        isScrolling: true,
        velocityPxPerSecond: AppSpacing.zero,
      );
      return false;
    }
    if (notification is ScrollUpdateNotification) {
      _videoScrollSettleTimer?.cancel();
      final previousPixels = _lastScrollPixels ?? notification.metrics.pixels;
      final previousSampleAt = _lastScrollSampleAt ?? now;
      final elapsedMs = now.difference(previousSampleAt).inMilliseconds;
      final delta =
          notification.scrollDelta ??
          (notification.metrics.pixels - previousPixels);
      final velocity = elapsedMs <= 0
          ? AppSpacing.zero
          : delta.abs() * Duration.millisecondsPerSecond / elapsedMs;
      _lastScrollPixels = notification.metrics.pixels;
      _lastScrollSampleAt = now;
      _publishVideoScrollSignal(
        isDragging: notification.dragDetails != null,
        isScrolling: true,
        velocityPxPerSecond: velocity,
        lastHighVelocityAt:
            velocity >= homeFeedVideoFastScrollVelocityPxPerSecond ? now : null,
      );
      return false;
    }
    if (notification is ScrollEndNotification) {
      _scheduleAnchorCapture();
      widget.onResourceSample();
      _lastScrollPixels = notification.metrics.pixels;
      _lastScrollSampleAt = now;
      _publishVideoScrollSignal(
        isDragging: false,
        isScrolling: true,
        velocityPxPerSecond: AppSpacing.zero,
        lastScrollEndAt: now,
      );
      _videoScrollSettleTimer?.cancel();
      _videoScrollSettleTimer = Timer(
        homeFeedVideoAutoPlayScrollEndDebounce,
        () {
          if (!mounted) return;
          _publishVideoScrollSignal(
            isDragging: false,
            isScrolling: false,
            velocityPxPerSecond: AppSpacing.zero,
            lastScrollEndAt: now,
          );
        },
      );
      return false;
    }
    return false;
  }

  void _publishVideoScrollSignal({
    required bool isDragging,
    required bool isScrolling,
    required double velocityPxPerSecond,
    DateTime? lastScrollEndAt,
    DateTime? lastHighVelocityAt,
  }) {
    final current = _videoScrollSignal.value;
    _videoScrollSignal.value = current.copyWith(
      isDragging: isDragging,
      isScrolling: isScrolling,
      velocityPxPerSecond: velocityPxPerSecond,
      lastScrollEndAt: lastScrollEndAt ?? current.lastScrollEndAt,
      lastHighVelocityAt: lastHighVelocityAt ?? current.lastHighVelocityAt,
    );
  }

  @override
  Widget build(BuildContext context) {
    final cacheExtent = ScrollCacheExtent.viewport(
      widget.resourceProfile.feedCacheExtentViewportMultiplier,
    );
    return ColoredBox(
      color: widget.pageBackground,
      child: NotificationListener<ScrollNotification>(
        onNotification: _handleScrollNotification,
        child: _HomeFeedVideoFocusScope(
          coordinator: _videoFocus,
          child: SizedBox.expand(
            key: _scrollSurfaceKey,
            child: CustomScrollView(
              controller: _controller,
              scrollCacheExtent: cacheExtent,
              slivers: _buildSlivers(),
            ),
          ),
        ),
      ),
    );
  }

  List<Widget> _buildSlivers() {
    assert(widget.entryIdentities.length == widget.itemCount);
    final entryIndexByKey = <Key, int>{
      for (var index = 0; index < widget.entryIdentities.length; index++)
        ValueKey<String>(
          homeFeedEntryElementKey(widget.entryIdentities[index]),
        ): index,
    };
    final slivers = <Widget>[];
    if (widget.headerSliver != null) {
      slivers.add(SliverToBoxAdapter(child: widget.headerSliver!));
    }
    if (widget.topPad > 0) {
      slivers.add(SliverToBoxAdapter(child: SizedBox(height: widget.topPad)));
    }
    final visibleStaleDataError = _visibleStaleDataError;
    if (visibleStaleDataError != null) {
      slivers.add(
        SliverToBoxAdapter(
          child: Padding(
            padding: EdgeInsets.fromLTRB(
              widget.horizontalPad,
              0,
              widget.horizontalPad,
              AppSpacing.containerSm,
            ),
            child: AppTransientErrorNotice(
              semantic: _homeCacheFallbackSemantic(
                context,
                visibleStaleDataError,
              ),
              margin: EdgeInsets.zero,
            ),
          ),
        ),
      );
    }

    if (widget.isMultiColumn) {
      var start = 0;
      var segmentIndex = 0;
      while (start < widget.itemCount) {
        if (widget.isFullSpanItem(start)) {
          slivers.add(
            SliverToBoxAdapter(
              key: ValueKey<String>(
                'home-feed-full-span-${widget.entryIdentities[start]}',
              ),
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: widget.horizontalPad),
                child: _buildAnchoredEntry(
                  start,
                  widget.fullSpanBuilder(start, _videoScrollSignal),
                ),
              ),
            ),
          );
          start += 1;
          continue;
        }

        var end = (start + _kFeedSegmentSize).clamp(0, widget.itemCount);
        for (var i = start + 1; i < end; i++) {
          if (widget.isFullSpanItem(i)) {
            end = i;
            break;
          }
        }
        final segStart = start;
        final segCount = end - segStart;
        if (segCount > 0) {
          slivers.add(
            SliverPadding(
              key: ValueKey<String>(
                'home-feed-masonry-${widget.entryIdentities[segStart]}',
              ),
              padding: EdgeInsets.symmetric(horizontal: widget.horizontalPad),
              sliver: SliverMasonryGrid(
                delegate: SliverChildBuilderDelegate(
                  (context, i) => _buildAnchoredEntry(
                    segStart + i,
                    widget.itemBuilder(segStart + i, _videoScrollSignal),
                  ),
                  childCount: segCount,
                  addAutomaticKeepAlives: false,
                  findChildIndexCallback: (key) {
                    final globalIndex = entryIndexByKey[key];
                    if (globalIndex == null ||
                        globalIndex < segStart ||
                        globalIndex >= segStart + segCount) {
                      return null;
                    }
                    return globalIndex - segStart;
                  },
                ),
                gridDelegate: SliverSimpleGridDelegateWithFixedCrossAxisCount(
                  crossAxisCount: widget.columns,
                ),
                mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
              ),
            ),
          );
        }
        start = end;
        final segment = widget.segmentBuilder?.call(segmentIndex);
        if (segment != null && start < widget.itemCount) {
          slivers.add(SliverToBoxAdapter(child: segment));
        }
        segmentIndex += 1;
        // 段间过渡留白：分段瀑布天然收齐后再进入下一组。
        if (start < widget.itemCount) {
          slivers.add(
            SliverToBoxAdapter(
              child: SizedBox(height: AppSpacing.interGroupMd),
            ),
          );
        }
      }
    } else {
      slivers.add(
        SliverList(
          delegate: SliverChildBuilderDelegate(
            (context, index) {
              if (index.isOdd) {
                final dividerIndex = index ~/ 2;
                return Divider(
                  key: ValueKey<String>('home-feed-divider-$dividerIndex'),
                  height: AppSpacing.one,
                  thickness: AppSpacing.hairline,
                  color: widget.dividerColor,
                );
              }
              final entryIndex = index ~/ 2;
              return _buildAnchoredEntry(
                entryIndex,
                widget.itemBuilder(entryIndex, _videoScrollSignal),
              );
            },
            childCount: widget.itemCount == 0 ? 0 : widget.itemCount * 2 - 1,
            addAutomaticKeepAlives: false,
            findChildIndexCallback: (key) {
              final entryIndex = entryIndexByKey[key];
              return entryIndex == null ? null : entryIndex * 2;
            },
          ),
        ),
      );
    }

    final showCompletedFooter =
        widget.itemCount > 0 && !widget.hasMore && widget.appendError == null;
    slivers.add(
      SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.only(
            top:
                widget.isLoadingMore ||
                    widget.appendError != null ||
                    showCompletedFooter
                ? AppSpacing.interGroupMd
                : AppSpacing.zero,
            bottom: widget.bottomPad,
          ),
          child:
              widget.isLoadingMore ||
                  widget.appendError != null ||
                  showCompletedFooter
              ? _LoadMoreFooter(
                  moodCopy: widget.moodCopy,
                  isDark: widget.isDark,
                  appendError: widget.appendError,
                  isComplete: showCompletedFooter,
                  onRetry: widget.onReachBottom,
                )
              : const SizedBox.shrink(),
        ),
      ),
    );
    return slivers;
  }

  Widget _buildAnchoredEntry(int index, Widget child) {
    final identity = widget.entryIdentities[index];
    return _HomeFeedAnchorMarker(
      key: ValueKey<String>(homeFeedEntryElementKey(identity)),
      registry: _anchorMarkers,
      stableEntryIdentity: identity,
      entryIndex: index,
      child: child,
    );
  }

  UiErrorSemantic _homeCacheFallbackSemantic(
    BuildContext context,
    Object error,
  ) {
    return runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
      allowRetry: false,
      presentation: UiErrorPresentation.transientNotice,
    );
  }
}

class _HomeFeedAnchorMarkerRegistry {
  final Map<String, _RenderHomeFeedAnchorMarker> _markers =
      <String, _RenderHomeFeedAnchorMarker>{};

  _RenderHomeFeedAnchorMarker? operator [](String stableEntryIdentity) {
    return _markers[stableEntryIdentity];
  }

  Iterable<_RenderHomeFeedAnchorMarker> get mountedMarkers => _markers.values;

  void attach(_RenderHomeFeedAnchorMarker marker) {
    _markers[marker.stableEntryIdentity] = marker;
  }

  void detach(_RenderHomeFeedAnchorMarker marker) {
    if (identical(_markers[marker.stableEntryIdentity], marker)) {
      _markers.remove(marker.stableEntryIdentity);
    }
  }
}

class _HomeFeedAnchorMarker extends SingleChildRenderObjectWidget {
  const _HomeFeedAnchorMarker({
    super.key,
    required this.registry,
    required this.stableEntryIdentity,
    required this.entryIndex,
    required super.child,
  });

  final _HomeFeedAnchorMarkerRegistry registry;
  final String stableEntryIdentity;
  final int entryIndex;

  @override
  _RenderHomeFeedAnchorMarker createRenderObject(BuildContext context) {
    return _RenderHomeFeedAnchorMarker(
      registry: registry,
      stableEntryIdentity: stableEntryIdentity,
      entryIndex: entryIndex,
    );
  }

  @override
  void updateRenderObject(
    BuildContext context,
    _RenderHomeFeedAnchorMarker renderObject,
  ) {
    renderObject
      ..registry = registry
      ..stableEntryIdentity = stableEntryIdentity
      ..entryIndex = entryIndex;
  }
}

class _RenderHomeFeedAnchorMarker extends RenderProxyBox {
  _RenderHomeFeedAnchorMarker({
    required this._registry,
    required this._stableEntryIdentity,
    required this.entryIndex,
  });

  _HomeFeedAnchorMarkerRegistry _registry;
  String _stableEntryIdentity;
  int entryIndex;

  _HomeFeedAnchorMarkerRegistry get registry => _registry;
  set registry(_HomeFeedAnchorMarkerRegistry value) {
    if (identical(value, _registry)) {
      return;
    }
    if (attached) {
      _registry.detach(this);
    }
    _registry = value;
    if (attached) {
      _registry.attach(this);
    }
  }

  String get stableEntryIdentity => _stableEntryIdentity;
  set stableEntryIdentity(String value) {
    if (value == _stableEntryIdentity) {
      return;
    }
    if (attached) {
      _registry.detach(this);
    }
    _stableEntryIdentity = value;
    if (attached) {
      _registry.attach(this);
    }
  }

  @override
  void attach(PipelineOwner owner) {
    super.attach(owner);
    _registry.attach(this);
  }

  @override
  void detach() {
    _registry.detach(this);
    super.detach();
  }

  ({double top, double height})? geometryInViewport(
    RenderBox ancestor, {
    required double scrollOffset,
  }) {
    if (!attached || !hasSize || !ancestor.attached || !ancestor.hasSize) {
      return null;
    }
    final viewport = RenderAbstractViewport.maybeOf(this);
    if (viewport == null) {
      return null;
    }
    final itemScrollOffset = viewport.getOffsetToReveal(this, 0).offset;
    if (!itemScrollOffset.isFinite) {
      return null;
    }
    // 可见性由调用方以 reveal offset 与真实 viewport 高度裁剪。不能沿
    // RenderObject.parent 寻找 [ancestor] 来判断 offstage：ScrollView 中间的
    // viewport/semantics 组合并不保证该人工遍历能命中外层 RenderBox，会把
    // 所有真实挂载的 sliver child 错判为不可见，导致频道卸载时完全没有锚点。
    final top = itemScrollOffset - scrollOffset;
    return (top: top, height: size.height);
  }
}

class _HomeFeedAnchorCandidate {
  const _HomeFeedAnchorCandidate({
    required this.marker,
    required this.viewportOffset,
  });

  final _RenderHomeFeedAnchorMarker marker;
  final double viewportOffset;

  bool isPreferredTo(_HomeFeedAnchorCandidate other) {
    final isPost = marker.stableEntryIdentity.startsWith('post:');
    final otherIsPost = other.marker.stableEntryIdentity.startsWith('post:');
    if (isPost != otherIsPost) {
      return isPost;
    }
    final overlapsTop = viewportOffset <= AppSpacing.zero;
    final otherOverlapsTop = other.viewportOffset <= AppSpacing.zero;
    if (overlapsTop != otherOverlapsTop) {
      return overlapsTop;
    }
    final distance = viewportOffset.abs();
    final otherDistance = other.viewportOffset.abs();
    if (distance != otherDistance) {
      return distance < otherDistance;
    }
    return marker.entryIndex < other.marker.entryIndex;
  }
}

class _HomeFeedMountedAnchorGeometry {
  const _HomeFeedMountedAnchorGeometry({
    required this.marker,
    required this.itemScrollOffset,
    required this.height,
  });

  final _RenderHomeFeedAnchorMarker marker;
  final double itemScrollOffset;
  final double height;
}

/// 触底加载 footer：加载指示 + 频道气质文案（只读，空文案不展示）。
class _LoadMoreFooter extends StatelessWidget {
  const _LoadMoreFooter({
    required this.moodCopy,
    required this.isDark,
    required this.appendError,
    required this.isComplete,
    required this.onRetry,
  });

  final String moodCopy;
  final bool isDark;
  final Object? appendError;
  final bool isComplete;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final hasError = appendError != null;
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        if (hasError)
          AppListAppendErrorFooter(
            semantic: runtimeErrorSemantic(
              context,
              error: appendError!,
              category: UiErrorCategory.listAppend,
              scope: UiErrorScope.section,
              presentation: UiErrorPresentation.appendFooter,
            ),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                onRetry();
              }
            },
          )
        else if (isComplete)
          Text(
            DiscoveryFeedText.contentLoadingCompleted,
            key: const ValueKey<String>('home-feed-completed-footer'),
            textAlign: TextAlign.center,
            style: TextStyle(fontSize: AppTypography.iosCaption1, color: muted),
          )
        else
          AppRequestFeedback.inline(),
        if (!hasError && !isComplete && moodCopy.isNotEmpty) ...[
          SizedBox(height: AppSpacing.intraGroupSm),
          Text(
            moodCopy,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: muted,
              letterSpacing: -0.04,
            ),
          ),
        ],
      ],
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 首页关系流卡片（社交图文风格）
// ─────────────────────────────────────────────────────────────────────────────
