// ignore_for_file: unnecessary_non_null_assertion
part of 'home_multi_form_feed.dart';

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
    required this.appendError,
    required this.staleDataError,
    required this.onRetryInitialLoad,
    required this.onReachBottom,
    required this.onResourceSample,
    this.moodCopy = '',
    this.headerSliver,
    this.segmentBuilder,
  });

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
  final Object? appendError;
  final Object? staleDataError;
  final VoidCallback onRetryInitialLoad;
  final VoidCallback onReachBottom;
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

class _HomeFeedScrollViewState extends State<_HomeFeedScrollView> {
  final ScrollController _controller = ScrollController();
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

  @override
  void initState() {
    super.initState();
    _controller.addListener(_onScroll);
    _syncStaleNotice(previous: null);
  }

  @override
  void didUpdateWidget(covariant _HomeFeedScrollView oldWidget) {
    super.didUpdateWidget(oldWidget);
    _syncStaleNotice(previous: oldWidget.staleDataError);
  }

  @override
  void dispose() {
    _staleNoticeTimer?.cancel();
    _videoScrollSettleTimer?.cancel();
    _videoScrollSignal.dispose();
    _videoFocus.dispose();
    _controller.removeListener(_onScroll);
    _controller.dispose();
    super.dispose();
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
    if (!widget.hasMore || widget.isLoadingMore) return;
    if (!_controller.hasClients) return;
    final position = _controller.position;
    // 剩余不足半屏即预取下一页（比例系数，非像素间距）。
    if (position.extentAfter < position.viewportDimension * 0.5) {
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
          child: CustomScrollView(
            controller: _controller,
            scrollCacheExtent: cacheExtent,
            slivers: _buildSlivers(),
          ),
        ),
      ),
    );
  }

  List<Widget> _buildSlivers() {
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
              child: Padding(
                padding: EdgeInsets.symmetric(horizontal: widget.horizontalPad),
                child: widget.fullSpanBuilder(start, _videoScrollSignal),
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
              padding: EdgeInsets.symmetric(horizontal: widget.horizontalPad),
              sliver: SliverMasonryGrid.count(
                crossAxisCount: widget.columns,
                mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                childCount: segCount,
                itemBuilder: (context, i) =>
                    widget.itemBuilder(segStart + i, _videoScrollSignal),
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
          delegate: SliverChildBuilderDelegate((context, index) {
            if (index.isOdd) {
              final dividerIndex = index ~/ 2;
              return Divider(
                key: ValueKey<String>('home-feed-divider-$dividerIndex'),
                height: AppSpacing.one,
                thickness: AppSpacing.hairline,
                color: widget.dividerColor,
              );
            }
            return widget.itemBuilder(index ~/ 2, _videoScrollSignal);
          }, childCount: widget.itemCount == 0 ? 0 : widget.itemCount * 2 - 1),
        ),
      );
    }

    slivers.add(
      SliverToBoxAdapter(
        child: Padding(
          padding: EdgeInsets.only(
            top: widget.isLoadingMore || widget.appendError != null
                ? AppSpacing.interGroupMd
                : AppSpacing.zero,
            bottom: widget.bottomPad,
          ),
          child: widget.isLoadingMore || widget.appendError != null
              ? _LoadMoreFooter(
                  moodCopy: widget.moodCopy,
                  isDark: widget.isDark,
                  appendError: widget.appendError,
                  onRetry: widget.onReachBottom,
                )
              : const SizedBox.shrink(),
        ),
      ),
    );
    return slivers;
  }

  UiErrorSemantic _homeCacheFallbackSemantic(
    BuildContext context,
    Object error,
  ) {
    final base = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.backgroundAction,
      scope: UiErrorScope.section,
      allowRetry: false,
      presentation: UiErrorPresentation.transientNotice,
    );
    return UiErrorSemantic(
      category: base.category,
      scope: base.scope,
      title: UITextConstants.pageLoadFailedTitle,
      message: UITextConstants.homeCacheFallback,
      secondaryMessage: base.secondaryMessage,
      primaryAction: base.primaryAction,
      secondaryAction: base.secondaryAction,
      dismissible: base.dismissible,
      sourceCode: base.sourceCode,
      failureKind: base.failureKind,
      copyKey: 'homeCacheFallback',
      recoveryAction: base.recoveryAction,
      presentation: base.presentation,
      tone: UiErrorTone.caution,
    );
  }
}

/// 触底加载 footer：加载指示 + 频道气质文案（只读，空文案不展示）。
class _LoadMoreFooter extends StatelessWidget {
  const _LoadMoreFooter({
    required this.moodCopy,
    required this.isDark,
    required this.appendError,
    required this.onRetry,
  });

  final String moodCopy;
  final bool isDark;
  final Object? appendError;
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
        else
          const CupertinoActivityIndicator(),
        if (!hasError && moodCopy.isNotEmpty) ...[
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
