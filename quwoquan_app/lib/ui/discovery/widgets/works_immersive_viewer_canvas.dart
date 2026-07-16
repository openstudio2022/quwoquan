part of 'works_immersive_viewer.dart';

@immutable
class _WorksTopChromeTheme {
  const _WorksTopChromeTheme({
    required this.overlayStyle,
    required this.foregroundColor,
    required this.mutedForegroundColor,
  });

  final SystemUiOverlayStyle overlayStyle;
  final Color foregroundColor;
  final Color mutedForegroundColor;
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
    _controllersByIndex.removeWhere((index, _) => index != aroundIndex);
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
            allowImplicitScrolling: false,
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
              final keepAlive = isCurrent;
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
    required this.reserveContentIntersection,
    this.onFallbackResolved,
    this.onPageFlipCommitted,
    this.onPageCurlAborted,
    this.onEntityTap,
    this.gestureIntentController,
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
  final bool reserveContentIntersection;
  final ValueChanged<ArticleReaderFallbackReason>? onFallbackResolved;
  final ValueChanged<ArticleReaderPageFlipCommit>? onPageFlipCommitted;
  final ValueChanged<ArticleReaderPageCurlAbort>? onPageCurlAborted;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final ImmersiveGestureIntentController? gestureIntentController;
  final int initialPage;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  Widget build(BuildContext context) {
    final topPaperReservedHeight =
        topChromeSafeInset +
        AppSpacing.appChromeTopBarHeight(context) +
        AppSpacing.intraGroupSm;
    final palette = resolveArticlePaperPalette(context, paperTexture);
    // Work Browser V1.0 Dark Paper：文章默认延续深色沉浸背景，
    // 翻页正面、背面、底页都消费同一 paperTexture。
    return CupertinoTheme(
      data: CupertinoTheme.of(context).copyWith(brightness: Brightness.dark),
      child: Stack(
        fit: StackFit.expand,
        children: [
          ColoredBox(color: palette.paperColor),
          Positioned(
            left: 0,
            right: 0,
            top: 0,
            bottom: _worksContentOverlayBottomClearance(
              context,
              includeIntersection: reserveContentIntersection,
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
                final pageAspectRatio =
                    constraints.maxWidth > 0 && constraints.maxHeight > 0
                    ? constraints.maxWidth / constraints.maxHeight
                    : metrics.aspectRatio;
                final immersiveMetrics = ArticleCanvasMetrics(
                  aspectRatio: pageAspectRatio,
                  outerPadding: metrics.outerPadding,
                  contentPadding: metrics.contentPadding.copyWith(
                    top: metrics.contentPadding.top + topPaperReservedHeight,
                  ),
                  headerReservedHeight: metrics.headerReservedHeight,
                  footerReservedHeight: metrics.footerReservedHeight,
                  wrapImageGap: metrics.wrapImageGap,
                  wrapImageMaxWidth: metrics.wrapImageMaxWidth,
                  fullWidthImageAspectRatio: metrics.fullWidthImageAspectRatio,
                  journalImageAspectRatio: metrics.journalImageAspectRatio,
                  inlineImageSpacing: metrics.inlineImageSpacing,
                );
                return ArticleReaderFlipHost(
                  adapter: ImmersiveBrowserReaderAdapter(
                    ArticleReaderHostConfig(
                      pages: pages,
                      template: article.template,
                      fontPreset: article.fontPreset,
                      metrics: immersiveMetrics,
                      coverUrl: post.primaryImageUrl,
                      initialPage: safeInitialPage,
                      enablePageCurl: enablePageCurl,
                      pagePadding: EdgeInsets.zero,
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
                      gestureIntentController: gestureIntentController,
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
    required this.reserveContentIntersection,
    this.imageUrl,
  });

  final ImmersiveViewerStageLayoutSpec layoutSpec;
  final String title;
  final String body;
  final bool reserveContentIntersection;
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
              bottom: _worksContentOverlayBottomClearance(
                context,
                includeIntersection: reserveContentIntersection,
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
