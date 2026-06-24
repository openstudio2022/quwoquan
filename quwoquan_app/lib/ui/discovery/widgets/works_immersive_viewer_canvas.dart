part of 'works_immersive_viewer.dart';

class _PostCircleTarget {
  const _PostCircleTarget({required this.id, required this.name});

  final String id;
  final String name;
}

@immutable
class _WorksTopChromeTheme {
  const _WorksTopChromeTheme({
    required this.overlayStyle,
    required this.foregroundColor,
    required this.mutedForegroundColor,
    this.surfaceColor,
    this.surfaceBorderColor,
  });

  final SystemUiOverlayStyle overlayStyle;
  final Color foregroundColor;
  final Color mutedForegroundColor;
  final Color? surfaceColor;
  final Color? surfaceBorderColor;

  bool get hasSurfaceDecoration =>
      surfaceColor != null && surfaceBorderColor != null;
}

/// Work Browser 顶部栏（V1.0）：极简，仅「返回」与「更多」。
/// 禁止媒体类型指示、页码、形态 tab；媒体筛选入口收敛到「更多」菜单。
/// 顶栏空白区保留横滑手势用于宿主一级 tab 切换（首页嵌入态）。
class _WorksPrimaryTopBar extends StatelessWidget {
  const _WorksPrimaryTopBar({
    required this.layoutSpec,
    required this.onHorizontalDragEnd,
    required this.foregroundColor,
    this.onTapClose,
    this.onTapMore,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final GestureDragEndCallback onHorizontalDragEnd;
  final Color foregroundColor;
  final VoidCallback? onTapClose;
  final VoidCallback? onTapMore;

  @override
  Widget build(BuildContext context) {
    return ImmersiveViewerLayout.alignToRail(
      context: context,
      layoutSpec: layoutSpec,
      child: SizedBox(
        key: const ValueKey<String>('works-top-rail'),
        width: double.infinity,
        height: AppSpacing.appChromeTopBarHeight(context),
        child: Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onHorizontalDragEnd: onHorizontalDragEnd,
                child: const SizedBox.expand(),
              ),
            ),

            Positioned(
              left: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: Opacity(
                  opacity: onTapClose == null ? 0 : 1,
                  child: KeyedSubtree(
                    key: const ValueKey<String>('works-top-back'),
                    child: ImmersiveToolbarIconButton(
                      icon: CupertinoIcons.back,
                      onPressed: onTapClose,
                      foregroundColor: foregroundColor,
                    ),
                  ),
                ),
              ),
            ),

            Positioned(
              right: 0,
              top: 0,
              bottom: 0,
              child: Center(
                child: KeyedSubtree(
                  key: const ValueKey<String>('works-top-more'),
                  child: ImmersiveToolbarIconButton(
                    icon: CupertinoIcons.ellipsis,
                    onPressed: onTapMore,
                    foregroundColor: foregroundColor,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _WorksPhotoCanvas extends StatefulWidget {
  const _WorksPhotoCanvas({
    required this.post,
    required this.onImageChanged,
    this.initialIndex = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final PostBaseDto post;
  final void Function(int index) onImageChanged;
  final int initialIndex;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  State<_WorksPhotoCanvas> createState() => _WorksPhotoCanvasState();
}

class _WorksPhotoCanvasState extends State<_WorksPhotoCanvas> {
  static const double _overflowSwitchVelocity = 320;
  static const double _overflowSwitchDistance = AppSpacing.buttonHeight;
  static const double _overflowEdgeStartInset =
      AppSpacing.minInteractiveSize / 2;
  static const double _photoBoundaryRubberBandMaxOffset =
      AppSpacing.buttonHeight;
  static const Duration _photoBoundaryResetDuration = Duration(
    milliseconds: 220,
  );

  late final PageController _imgController;
  double _edgeOverflowDistance = 0;
  double _boundaryRubberBandRawOffset = 0;
  double _boundaryRubberBandOffset = 0;
  TabSwipeDirection? _pendingOverflowDirection;
  bool _overflowTriggered = false;
  bool _shouldAnimateBoundaryReset = false;
  Offset? _dragStartLocalPosition;

  @override
  void initState() {
    super.initState();
    _imgController = PageController(initialPage: _safeInitialIndex);
    WidgetsBinding.instance.addPostFrameCallback((timeStamp) {
      widget.onImageChanged(_safeInitialIndex);
    });
  }

  @override
  void dispose() {
    _imgController.dispose();
    super.dispose();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _precacheNeighborImages(_safeInitialIndex);
  }

  @override
  void didUpdateWidget(covariant _WorksPhotoCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.post != oldWidget.post ||
        widget.initialIndex != oldWidget.initialIndex) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _precacheNeighborImages(_safeInitialIndex);
      });
    }
  }

  int get _safeInitialIndex {
    final length = _images.length;
    if (length <= 1) return 0;
    return widget.initialIndex.clamp(0, length - 1);
  }

  List<String> get _images {
    return widget.post.hasImages
        ? widget.post.mediaImageUrls
        : (widget.post.primaryImageUrl.isNotEmpty
              ? <String>[widget.post.primaryImageUrl]
              : const <String>[]);
  }

  double _pageWidthForConstraints(BoxConstraints constraints) {
    if (constraints.maxWidth.isFinite && constraints.maxWidth > 0) {
      return constraints.maxWidth;
    }
    return MediaQuery.of(context).size.width;
  }

  void _precacheNeighborImages(int centerIndex) {
    final images = _images;
    for (final index in <int>[centerIndex - 1, centerIndex, centerIndex + 1]) {
      if (index < 0 || index >= images.length) {
        continue;
      }
      final url = images[index];
      if (url.isEmpty) {
        continue;
      }
      final candidates = resolveContentMediaUrlCandidates(url);
      if (_shouldSkipLocalPrecache(candidates)) {
        continue;
      }
      unawaited(_precacheImageCandidates(candidates));
    }
  }

  bool _shouldSkipLocalPrecache(List<String> candidates) {
    return candidates.isNotEmpty &&
        candidates.every(isPrivateDevContentMediaUrl);
  }

  Future<void> _precacheImageCandidates(List<String> candidates) async {
    for (final candidate in candidates) {
      try {
        final url = candidate;
        await precacheImage(CachedNetworkImageProvider(url), context);
        return;
      } catch (_) {
        continue;
      }
    }
  }

  void _triggerOverflow(TabSwipeDirection direction) {
    final callback = direction == TabSwipeDirection.previous
        ? widget.onOverflowPrevious
        : widget.onOverflowNext;
    if (callback == null || _overflowTriggered) {
      return;
    }
    _overflowTriggered = true;
    callback();
  }

  void _resetOverflowTracking() {
    _edgeOverflowDistance = 0;
    _pendingOverflowDirection = null;
    _overflowTriggered = false;
  }

  double _springDampedOffset(double raw, double maxPull) {
    if (raw <= 0 || maxPull <= 0) {
      return 0;
    }
    final damping = maxPull / 1.2;
    return (maxPull * (1 - exp(-raw / damping))).clamp(0.0, maxPull);
  }

  void _setBoundaryRubberBandOffset(
    double visualOffset, {
    required bool animate,
    double? rawOffset,
  }) {
    final safeVisualOffset = visualOffset.abs() < 0.1 ? 0.0 : visualOffset;
    final safeRawOffset =
        rawOffset ??
        (safeVisualOffset == 0.0 ? 0.0 : _boundaryRubberBandRawOffset);
    if ((_boundaryRubberBandOffset - safeVisualOffset).abs() < 0.1 &&
        (_boundaryRubberBandRawOffset - safeRawOffset).abs() < 0.1 &&
        _shouldAnimateBoundaryReset == animate) {
      return;
    }
    setState(() {
      _boundaryRubberBandOffset = safeVisualOffset;
      _boundaryRubberBandRawOffset = safeRawOffset;
      _shouldAnimateBoundaryReset = animate;
    });
  }

  void _applyBoundaryRubberBand(
    DragUpdateDetails details,
    TabSwipeDirection direction,
  ) {
    final nextRaw = direction == TabSwipeDirection.previous
        ? (_boundaryRubberBandRawOffset + details.delta.dx).clamp(
            0.0,
            double.infinity,
          )
        : (_boundaryRubberBandRawOffset + details.delta.dx).clamp(
            double.negativeInfinity,
            0.0,
          );
    final magnitude = _springDampedOffset(
      nextRaw.abs(),
      _photoBoundaryRubberBandMaxOffset,
    );
    final visualOffset = direction == TabSwipeDirection.previous
        ? magnitude
        : -magnitude;
    _setBoundaryRubberBandOffset(
      visualOffset,
      animate: false,
      rawOffset: nextRaw.toDouble(),
    );
  }

  void _resetBoundaryRubberBand({required bool animate}) {
    _setBoundaryRubberBandOffset(0, animate: animate, rawOffset: 0);
  }

  void _trackEdgeOverflow(
    DragUpdateDetails details,
    List<String> images,
    double pageWidth,
  ) {
    if (!_imgController.hasClients) {
      return;
    }
    final maxOffset = images.length <= 1
        ? 0.0
        : (images.length - 1) * pageWidth;
    final atLeadingEdge = _imgController.offset <= AppSpacing.hairline;
    final atTrailingEdge =
        _imgController.offset >= maxOffset - AppSpacing.hairline;
    final swipingToPrevious = details.delta.dx > 0;
    final swipingToNext = details.delta.dx < 0;
    final direction = atLeadingEdge && swipingToPrevious
        ? TabSwipeDirection.previous
        : atTrailingEdge && swipingToNext
        ? TabSwipeDirection.next
        : null;
    if (direction == null) {
      _resetBoundaryRubberBand(animate: false);
      _edgeOverflowDistance = 0;
      _pendingOverflowDirection = null;
      return;
    }
    _applyBoundaryRubberBand(details, direction);
    if (!_isEdgeOverflowStart(direction, pageWidth)) {
      _edgeOverflowDistance = 0;
      _pendingOverflowDirection = null;
      return;
    }
    if (_pendingOverflowDirection != direction) {
      _pendingOverflowDirection = direction;
      _edgeOverflowDistance = 0;
    }
    _edgeOverflowDistance += details.delta.dx.abs();
    if (_edgeOverflowDistance >= _overflowSwitchDistance) {
      _triggerOverflow(direction);
    }
  }

  // ── Horizontal gesture handlers ───────────────────────────────────────────
  // The photo canvas lives inside an outer *vertical* PageView. Flutter's
  // gesture arena separates vertical vs. horizontal recognisers, but the
  // overlay DecoratedBox (full-screen, no child) can still introduce hit-test
  // timing ambiguity in some runtime conditions. To guarantee reliable swipe:
  //   1. Outer GestureDetector (opaque) explicitly owns horizontal drags.
  //   2. It drives _imgController directly so the page follows the finger.
  //   3. Inner PageView uses NeverScrollableScrollPhysics — no gesture
  //      competition from a second HorizontalDragGestureRecognizer.
  //   4. The gradient overlay is wrapped in IgnorePointer so it is fully
  //      removed from hit-test consideration.

  bool _isEdgeOverflowStart(TabSwipeDirection direction, double width) {
    final startPosition = _dragStartLocalPosition;
    if (startPosition == null) {
      return false;
    }
    return switch (direction) {
      TabSwipeDirection.previous =>
        widget.onOverflowPrevious != null &&
            startPosition.dx <= _overflowEdgeStartInset,
      TabSwipeDirection.next =>
        widget.onOverflowNext != null &&
            startPosition.dx >= width - _overflowEdgeStartInset,
    };
  }

  void _onHorizontalDragDown(DragDownDetails details) {
    _dragStartLocalPosition = details.localPosition;
    if (_imgController.hasClients) {
      _imgController.jumpTo(_imgController.offset);
    }
    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: false);
  }

  void _onHorizontalDragUpdate(DragUpdateDetails details, double pageWidth) {
    final images = _images;
    if (images.length > 1 && _imgController.hasClients) {
      final maxOffset = (images.length - 1) * pageWidth;
      _imgController.jumpTo(
        (_imgController.offset - details.delta.dx).clamp(0.0, maxOffset),
      );
    }
    _trackEdgeOverflow(details, images, pageWidth);
  }

  Duration _settleDuration({
    required int targetPage,
    required double pageWidth,
    required double velocity,
  }) {
    if (!_imgController.hasClients || pageWidth <= 0) {
      return const Duration(milliseconds: 180);
    }
    final targetOffset = targetPage * pageWidth;
    final distance = (targetOffset - _imgController.offset).abs();
    final distanceRatio = (distance / pageWidth).clamp(0.0, 1.0).toDouble();
    final fastFling = velocity.abs() >= 700;
    final milliseconds = fastFling
        ? 140 + distanceRatio * 80
        : 160 + distanceRatio * 100;
    return Duration(milliseconds: milliseconds.clamp(140, 260).round().toInt());
  }

  void _onHorizontalDragEnd(DragEndDetails details, double pageWidth) {
    final images = _images;
    final maxOffset = images.length <= 1
        ? 0.0
        : (images.length - 1) * pageWidth;
    final currentOffset = _imgController.hasClients ? _imgController.offset : 0;
    final atLeadingEdge = currentOffset <= AppSpacing.hairline;
    final atTrailingEdge = currentOffset >= maxOffset - AppSpacing.hairline;
    final velocity = details.primaryVelocity ?? 0;

    if (!_overflowTriggered && velocity.abs() >= _overflowSwitchVelocity) {
      if (velocity > 0 &&
          atLeadingEdge &&
          _isEdgeOverflowStart(TabSwipeDirection.previous, pageWidth)) {
        _triggerOverflow(TabSwipeDirection.previous);
      } else if (velocity < 0 &&
          atTrailingEdge &&
          _isEdgeOverflowStart(TabSwipeDirection.next, pageWidth)) {
        _triggerOverflow(TabSwipeDirection.next);
      }
    }

    if (!_overflowTriggered && images.length > 1 && _imgController.hasClients) {
      final currentPage = pageWidth <= 0 ? 0.0 : currentOffset / pageWidth;
      final int targetPage;
      if (velocity < -500) {
        targetPage = (currentPage.round() + 1).clamp(0, images.length - 1);
      } else if (velocity > 500) {
        targetPage = (currentPage.round() - 1).clamp(0, images.length - 1);
      } else {
        targetPage = currentPage.round().clamp(0, images.length - 1);
      }
      _precacheNeighborImages(targetPage);
      _imgController.animateToPage(
        targetPage,
        duration: _settleDuration(
          targetPage: targetPage,
          pageWidth: pageWidth,
          velocity: velocity,
        ),
        curve: Curves.easeOutCubic,
      );
    }

    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: true);
    _dragStartLocalPosition = null;
  }

  void _onHorizontalDragCancel() {
    _resetOverflowTracking();
    _resetBoundaryRubberBand(animate: true);
    _dragStartLocalPosition = null;
  }

  @override
  Widget build(BuildContext context) {
    final images = _images;
    final handlesHorizontalOverflow =
        images.length > 1 ||
        widget.onOverflowPrevious != null ||
        widget.onOverflowNext != null;
    return LayoutBuilder(
      builder: (context, constraints) {
        final pageWidth = _pageWidthForConstraints(constraints);
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onHorizontalDragDown: handlesHorizontalOverflow
              ? _onHorizontalDragDown
              : null,
          onHorizontalDragUpdate: handlesHorizontalOverflow
              ? (details) => _onHorizontalDragUpdate(details, pageWidth)
              : null,
          onHorizontalDragEnd: handlesHorizontalOverflow
              ? (details) => _onHorizontalDragEnd(details, pageWidth)
              : null,
          onHorizontalDragCancel: handlesHorizontalOverflow
              ? _onHorizontalDragCancel
              : null,
          child: AnimatedContainer(
            key: const ValueKey<String>('works-photo-stage'),
            duration: _shouldAnimateBoundaryReset
                ? _photoBoundaryResetDuration
                : Duration.zero,
            curve: Curves.easeOutCubic,
            transform: Matrix4.translationValues(
              _boundaryRubberBandOffset,
              0,
              0,
            ),
            child: Stack(
              fit: StackFit.expand,
              children: [
                PageView.builder(
                  controller: _imgController,
                  // NeverScrollableScrollPhysics — gestures handled by the outer
                  // GestureDetector above; this removes the second competing
                  // HorizontalDragGestureRecognizer from the arena entirely.
                  physics: const NeverScrollableScrollPhysics(),
                  itemCount: images.isEmpty ? 1 : images.length,
                  onPageChanged: (i) {
                    _precacheNeighborImages(i);
                    widget.onImageChanged(i);
                  },
                  itemBuilder: (context, i) {
                    if (images.isEmpty) {
                      return Container(color: AppColors.worksBackground);
                    }
                    return AppCachedNetworkImage(
                      imageUrl: images[i],
                      imageUrlCandidates: resolveContentMediaUrlCandidates(
                        images[i],
                      ),
                      cdnPreset: CdnImagePreset.cover,
                      fit: BoxFit.cover,
                      placeholder: Container(color: AppColors.worksBackground),
                      errorWidget: Container(color: AppColors.worksBackground),
                    );
                  },
                ),
                Positioned.fill(
                  // IgnorePointer removes the gradient box from hit testing entirely,
                  // so it can never compete with the GestureDetector above.
                  child: IgnorePointer(
                    child: DecoratedBox(
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          begin: Alignment.topCenter,
                          end: Alignment.bottomCenter,
                          colors: [
                            AppColors.black.withValues(alpha: 0.06),
                            AppColors.black.withValues(alpha: 0.58),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }
}

/// 视频作品画布（V1.0）：全屏沉浸视频；作品内分集横滑切换（mediaItems 契约序列）；
/// 默认控件被禁用，播放控制由 caption header 的极简控制条承载；
/// 点击视频区域切换播放/暂停。
class _WorksVideoCanvas extends StatefulWidget {
  const _WorksVideoCanvas({
    required this.post,
    required this.items,
    required this.onEpisodeChanged,
    required this.onActiveControllerChanged,
  });

  final PostBaseDto post;
  final List<WorkBrowserMediaItemDto> items;
  final ValueChanged<int> onEpisodeChanged;
  final void Function(int episodeIndex, VideoPlayerController? controller)
  onActiveControllerChanged;

  @override
  State<_WorksVideoCanvas> createState() => _WorksVideoCanvasState();
}

class _WorksVideoCanvasState extends State<_WorksVideoCanvas> {
  late final PageController _episodeController;
  int _currentEpisodeIndex = 0;
  bool _episodePlaybackSettled = true;
  Timer? _episodeSettleTimer;
  final Map<int, VideoPlayerController> _controllersByIndex =
      <int, VideoPlayerController>{};

  @override
  void initState() {
    super.initState();
    _episodeController = PageController();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      widget.onEpisodeChanged(0);
    });
  }

  @override
  void dispose() {
    _episodeSettleTimer?.cancel();
    _controllersByIndex.clear();
    widget.onActiveControllerChanged(_currentEpisodeIndex, null);
    _episodeController.dispose();
    super.dispose();
  }

  bool _handleEpisodeScrollNotification(ScrollNotification notification) {
    if (notification is ScrollStartNotification ||
        notification is ScrollUpdateNotification) {
      _episodeSettleTimer?.cancel();
      if (_episodePlaybackSettled) {
        setState(() => _episodePlaybackSettled = false);
      }
      return false;
    }
    if (notification is ScrollEndNotification) {
      _scheduleEpisodePlaybackSettle();
    }
    return false;
  }

  void _scheduleEpisodePlaybackSettle() {
    _episodeSettleTimer?.cancel();
    _episodeSettleTimer = Timer(homeFeedVideoAutoPlayScrollEndDebounce, () {
      if (!mounted) return;
      setState(() => _episodePlaybackSettled = true);
    });
  }

  void _registerController(int index, VideoPlayerController controller) {
    _pruneControllerRegistry(aroundIndex: _currentEpisodeIndex);
    _controllersByIndex[index] = controller;
    if (index == _currentEpisodeIndex) {
      widget.onActiveControllerChanged(index, controller);
    }
  }

  void _pruneControllerRegistry({required int aroundIndex}) {
    _controllersByIndex.removeWhere(
      (index, _) => (index - aroundIndex).abs() > 1,
    );
  }

  void _togglePlayback(int index) {
    final controller = _controllersByIndex[index];
    if (controller == null || !controller.value.isInitialized) return;
    if (controller.value.isPlaying) {
      controller.pause();
    } else {
      controller.play();
    }
  }

  @override
  Widget build(BuildContext context) {
    final items = widget.items;
    if (items.isEmpty) {
      return Container(color: AppColors.worksBackground);
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        NotificationListener<ScrollNotification>(
          onNotification: _handleEpisodeScrollNotification,
          child: PageView.builder(
            controller: _episodeController,
            scrollDirection: Axis.horizontal,
            allowImplicitScrolling: true,
            itemCount: items.length,
            onPageChanged: (index) {
              setState(() {
                _currentEpisodeIndex = index;
                _episodePlaybackSettled = false;
              });
              _pruneControllerRegistry(aroundIndex: index);
              _scheduleEpisodePlaybackSettle();
              widget.onEpisodeChanged(index);
              widget.onActiveControllerChanged(
                index,
                _controllersByIndex[index],
              );
            },
            itemBuilder: (context, index) {
              final item = items[index];
              if (item.url.isEmpty) {
                return Container(color: AppColors.worksBackground);
              }
              final isCurrent = index == _currentEpisodeIndex;
              final keepAlive = (index - _currentEpisodeIndex).abs() <= 1;
              return _KeepAliveStage(
                key: ValueKey<String>(
                  'works-video-stage-${widget.post.id}-$index',
                ),
                keepAlive: keepAlive,
                child: VideoPlayerWidget(
                  key: ValueKey<String>('works-video-${widget.post.id}-$index'),
                  videoUrl: item.url,
                  thumbnailUrl: item.coverUrl,
                  initialize: isCurrent,
                  autoPlay: isCurrent && _episodePlaybackSettled,
                  showControls: false,
                  onTap: () => _togglePlayback(index),
                  onControllerCreated: (controller) =>
                      _registerController(index, controller),
                ),
              );
            },
          ),
        ),
        Positioned.fill(
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: [
                    AppColors.black.withValues(alpha: 0.08),
                    AppColors.black.withValues(alpha: 0.62),
                  ],
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _KeepAliveStage extends StatefulWidget {
  const _KeepAliveStage({
    super.key,
    required this.child,
    required this.keepAlive,
  });

  final Widget child;
  final bool keepAlive;

  @override
  State<_KeepAliveStage> createState() => _KeepAliveStageState();
}

class _KeepAliveStageState extends State<_KeepAliveStage>
    with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => widget.keepAlive;

  @override
  void didUpdateWidget(covariant _KeepAliveStage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.keepAlive != widget.keepAlive) {
      updateKeepAlive();
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return widget.child;
  }
}

class _WorksArticleCanvas extends StatelessWidget {
  const _WorksArticleCanvas({
    required this.post,
    required this.article,
    required this.timeLine,
    required this.paperTexture,
    required this.enablePageCurl,
    required this.onPageChanged,
    required this.onResolvedPageCountChanged,
    required this.topChromeSafeInset,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onEntityTap,
    this.initialPage = 0,
    this.onOverflowPrevious,
    this.onOverflowNext,
  });

  final PostBaseDto post;
  final ContentArticleRender article;
  final String timeLine;
  final ArticlePaperTexture paperTexture;
  final bool enablePageCurl;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onResolvedPageCountChanged;
  final double topChromeSafeInset;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final int initialPage;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  Widget build(BuildContext context) {
    final topPaperReservedHeight =
        topChromeSafeInset +
        AppSpacing.appChromeTopBarHeight(context) +
        AppSpacing.intraGroupSm;
    final stagePadding = EdgeInsets.only(top: topPaperReservedHeight);
    final palette = resolveArticlePaperPalette(context, paperTexture);
    // Work Browser V1.0 Dark Paper：文章默认延续深色沉浸背景，
    // 翻页正面、背面、底页都消费同一 paperTexture。
    return CupertinoTheme(
      data: CupertinoTheme.of(context).copyWith(brightness: Brightness.dark),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ColoredBox(color: palette.stageBackground),
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            bottom: ImmersiveEngagementBar.overlayClearance(
              context,
              gap: AppSpacing.containerMd,
            ),
            child: LayoutBuilder(
              builder: (context, constraints) {
                final pages = resolvePaginatedArticlePages(
                  context: context,
                  constraints: constraints,
                  document: article.document,
                  template: article.template,
                  fontPreset: article.fontPreset,
                  fallbackPages: article.pages,
                  variant: ArticleCanvasVariant.immersive,
                  paperTexture: paperTexture,
                );
                onResolvedPageCountChanged(pages.length.clamp(1, 99).toInt());
                final maxIndex = pages.isEmpty ? 0 : pages.length - 1;
                final safeInitialPage = pages.isEmpty
                    ? 0
                    : initialPage.clamp(0, maxIndex).toInt();
                final metrics = resolveArticleCanvasMetrics(
                  context,
                  constraints,
                  variant: ArticleCanvasVariant.immersive,
                );
                return ArticleReaderFlipHost(
                  adapter: ImmersiveBrowserReaderAdapter(
                    ArticleReaderHostConfig(
                      pages: pages,
                      template: article.template,
                      fontPreset: article.fontPreset,
                      metrics: metrics,
                      coverUrl: post.primaryImageUrl,
                      initialPage: safeInitialPage,
                      enablePageCurl: enablePageCurl,
                      pagePadding: stagePadding,
                      headerLabel: timeLine,
                      showFooterPageLabel: false,
                      paperTexture: paperTexture,
                      presentationStyle:
                          ArticleReadOnlyBookDeckPresentationStyle.immersive,
                      onPageChanged: onPageChanged,
                      onOverflowPrevious: onOverflowPrevious,
                      onOverflowNext: onOverflowNext,
                      onFallbackResolved: onFallbackResolved,
                      onPageFlipCommitted: onPageFlipCommitted,
                      onPageCurlAborted: onPageCurlAborted,
                      onEntityTap: onEntityTap,
                    ),
                  ),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _WorksTextCanvas extends StatelessWidget {
  const _WorksTextCanvas({
    required this.layoutSpec,
    required this.title,
    required this.body,
    this.imageUrl,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final String title;
  final String body;
  final String? imageUrl;

  @override
  Widget build(BuildContext context) {
    return Stack(
      fit: StackFit.expand,
      children: [
        Container(color: AppColors.worksBackground),
        if ((imageUrl ?? '').isNotEmpty)
          Positioned.fill(
            child: Opacity(
              opacity: 0.08,
              child: AppCachedNetworkImage(
                imageUrl: imageUrl!,
                imageUrlCandidates: resolveContentMediaUrlCandidates(imageUrl!),
                cdnPreset: CdnImagePreset.thumbnail,
                fit: BoxFit.cover,
                placeholder: Container(color: AppColors.worksBackground),
                errorWidget: Container(color: AppColors.worksBackground),
              ),
            ),
          ),
        Positioned.fill(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: [
                  AppColors.black.withValues(alpha: 0.08),
                  AppColors.worksBackground.withValues(alpha: 0.92),
                ],
              ),
            ),
          ),
        ),
        SafeArea(
          child: Padding(
            padding: EdgeInsets.only(
              top: AppSpacing.containerLg,
              bottom: ImmersiveEngagementBar.overlayClearance(
                context,
                gap: AppSpacing.containerMd,
              ),
            ),
            child: ImmersiveViewerLayout.alignToRail(
              context: context,
              layoutSpec: layoutSpec,
              child: Container(
                key: const ValueKey<String>('works-text-stage-rail'),
                width: double.infinity,
                padding: EdgeInsets.all(AppSpacing.containerLg),
                decoration: BoxDecoration(
                  color: AppColors.worksDrawerBg.withValues(alpha: 0.74),
                  borderRadius: BorderRadius.circular(
                    AppSpacing.borderRadius + 4,
                  ),
                  border: Border.all(
                    color: AppColors.worksBodyText.withValues(alpha: 0.16),
                  ),
                ),
                child: SingleChildScrollView(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if (title.isNotEmpty) ...[
                        Text(
                          title,
                          style: TextStyle(
                            fontSize: AppTypography.xl + 2,
                            fontWeight: AppTypography.bold,
                            color: AppColors.worksTitle,
                            height: AppTypography.bodyLineHeight,
                          ),
                        ),
                        SizedBox(height: AppSpacing.intraGroupSm),
                      ],
                      Text(
                        body,
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          color: AppColors.worksBodyText,
                          height: AppTypography.lineHeightRelaxed,
                          letterSpacing: 0.4,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }
}
