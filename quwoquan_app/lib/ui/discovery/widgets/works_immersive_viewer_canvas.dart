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
    super.key,
    required this.post,
    required this.items,
    required this.initialEpisodeIndex,
    required this.isVisible,
    required this.onEpisodeChanged,
    required this.onActiveSessionChanged,
  });

  final PostBaseDto post;
  final List<_WorksVideoDeliveryItem> items;
  final int initialEpisodeIndex;
  final bool isVisible;
  final void Function(int episodeIndex, String episodeIdentity)
  onEpisodeChanged;
  final void Function(
    int episodeIndex,
    String episodeIdentity,
    VideoPlaybackSession? session,
  )
  onActiveSessionChanged;

  @override
  State<_WorksVideoCanvas> createState() => _WorksVideoCanvasState();
}

class _WorksVideoCanvasState extends State<_WorksVideoCanvas> {
  late final PageController _episodeController;
  late int _currentEpisodeIndex;
  bool _episodePlaybackSettled = true;
  Timer? _episodeSettleTimer;
  final Map<String, VideoPlaybackSession> _sessionsByIdentity =
      <String, VideoPlaybackSession>{};

  @override
  void initState() {
    super.initState();
    _currentEpisodeIndex = _safeEpisodeIndex(widget.initialEpisodeIndex);
    _episodeController = PageController(initialPage: _currentEpisodeIndex);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final identity = _currentEpisodeIdentity;
      if (mounted && widget.isVisible && identity != null) {
        widget.onEpisodeChanged(_currentEpisodeIndex, identity);
        widget.onActiveSessionChanged(
          _currentEpisodeIndex,
          identity,
          _sessionsByIdentity[identity],
        );
      }
    });
  }

  @override
  void didUpdateWidget(covariant _WorksVideoCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    final episodeReconciled = _reconcileEpisodes(oldWidget);
    if (episodeReconciled && widget.isVisible && oldWidget.isVisible) {
      final identity = _currentEpisodeIdentity;
      if (identity != null) {
        widget.onEpisodeChanged(_currentEpisodeIndex, identity);
        widget.onActiveSessionChanged(
          _currentEpisodeIndex,
          identity,
          _sessionsByIdentity[identity],
        );
      }
    }
    if (oldWidget.isVisible == widget.isVisible) {
      if (widget.isVisible && !episodeReconciled) {
        final identity = _currentEpisodeIdentity;
        if (identity != null) {
          // 父级 viewport epoch 失效后可能保留同一个视频 child；即使分集与
          // 可见性未变，也要把同源 session 重新绑定到新的父级回调。
          widget.onEpisodeChanged(_currentEpisodeIndex, identity);
          widget.onActiveSessionChanged(
            _currentEpisodeIndex,
            identity,
            _sessionsByIdentity[identity],
          );
        }
      }
      return;
    }
    if (widget.isVisible) {
      final identity = _currentEpisodeIdentity;
      if (identity == null) {
        return;
      }
      widget.onEpisodeChanged(_currentEpisodeIndex, identity);
      widget.onActiveSessionChanged(
        _currentEpisodeIndex,
        identity,
        _sessionsByIdentity[identity],
      );
      return;
    }
    final identity = _currentEpisodeIdentity;
    if (identity != null) {
      widget.onActiveSessionChanged(_currentEpisodeIndex, identity, null);
    }
  }

  @override
  void dispose() {
    _episodeSettleTimer?.cancel();
    final identity = _currentEpisodeIdentity;
    if (identity != null) {
      widget.onActiveSessionChanged(_currentEpisodeIndex, identity, null);
    }
    for (final session in _sessionsByIdentity.values) {
      session.dispose();
    }
    _sessionsByIdentity.clear();
    _episodeController.dispose();
    super.dispose();
  }

  int _safeEpisodeIndex(int index) {
    if (widget.items.isEmpty) {
      return 0;
    }
    return index.clamp(0, widget.items.length - 1);
  }

  String? get _currentEpisodeIdentity {
    if (_currentEpisodeIndex < 0 ||
        _currentEpisodeIndex >= widget.items.length) {
      return null;
    }
    return widget.items[_currentEpisodeIndex].identity;
  }

  bool _reconcileEpisodes(_WorksVideoCanvas oldWidget) {
    final validIdentities = widget.items.map((item) => item.identity).toSet();
    final removedIdentities = _sessionsByIdentity.keys
        .where((identity) => !validIdentities.contains(identity))
        .toList(growable: false);
    final removedSessions = <VideoPlaybackSession>[];
    for (final identity in removedIdentities) {
      final session = _sessionsByIdentity.remove(identity);
      if (session != null) {
        removedSessions.add(session);
      }
    }
    if (removedSessions.isNotEmpty) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        // 旧 VideoPlayerWidget 必须先完成 detach；在父 didUpdateWidget 中同步
        // dispose session 会让仍挂载的子节点命中 disposed ChangeNotifier。
        for (final session in removedSessions) {
          session.dispose();
        }
      });
    }
    if (widget.items.isEmpty) {
      final changed = _currentEpisodeIndex != 0;
      _currentEpisodeIndex = 0;
      return changed;
    }
    final previousIdentity =
        _currentEpisodeIndex >= 0 &&
            _currentEpisodeIndex < oldWidget.items.length
        ? oldWidget.items[_currentEpisodeIndex].identity
        : null;
    final preservedIndex = previousIdentity == null
        ? -1
        : widget.items.indexWhere((item) => item.identity == previousIdentity);
    final nextIndex = preservedIndex >= 0
        ? preservedIndex
        : _safeEpisodeIndex(widget.initialEpisodeIndex);
    final nextIdentity = widget.items[nextIndex].identity;
    final identityChanged = previousIdentity != nextIdentity;
    if (nextIndex == _currentEpisodeIndex && !identityChanged) {
      return false;
    }
    final indexChanged = nextIndex != _currentEpisodeIndex;
    _currentEpisodeIndex = nextIndex;
    if (indexChanged) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted || !_episodeController.hasClients) {
          return;
        }
        _episodeController.jumpToPage(_currentEpisodeIndex);
      });
    }
    return true;
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

  VideoPlaybackSession _sessionFor(String identity) {
    return _sessionsByIdentity.putIfAbsent(identity, VideoPlaybackSession.new);
  }

  void _registerSession(
    int index,
    String identity,
    VideoPlaybackSession session,
  ) {
    _sessionsByIdentity[identity] = session;
    if (widget.isVisible && index == _currentEpisodeIndex) {
      widget.onActiveSessionChanged(index, identity, session);
    }
  }

  void _togglePlayback(String identity) {
    unawaited(_sessionFor(identity).toggle());
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
              final identity = items[index].identity;
              setState(() {
                _currentEpisodeIndex = index;
                _episodePlaybackSettled = false;
              });
              _scheduleEpisodePlaybackSettle();
              if (widget.isVisible) {
                widget.onEpisodeChanged(index, identity);
                widget.onActiveSessionChanged(
                  index,
                  identity,
                  _sessionsByIdentity[identity],
                );
              }
            },
            itemBuilder: (context, index) {
              final item = items[index];
              final identity = item.identity;
              final isCurrent = index == _currentEpisodeIndex;
              final keepAlive = widget.isVisible && isCurrent;
              final session = _sessionFor(identity);
              return KeyedSubtree(
                key: ValueKey<String>(
                  'works-video-stage-${widget.post.id}-$index',
                ),
                child: _KeepAliveStage(
                  key: ValueKey<String>(
                    'works-video-stage-identity-${widget.post.id}-$identity',
                  ),
                  keepAlive: keepAlive,
                  child: Stack(
                    fit: StackFit.expand,
                    children: [
                      KeyedSubtree(
                        key: ValueKey<String>(
                          'works-video-${widget.post.id}-$index',
                        ),
                        child: VideoPlayerWidget(
                          key: ValueKey<String>(
                            'works-video-identity-${widget.post.id}-$identity',
                          ),
                          deliveryReference: item.deliveryReference,
                          thumbnailReference: item.coverReference,
                          initialize: widget.isVisible && isCurrent,
                          autoPlay:
                              widget.isVisible &&
                              isCurrent &&
                              _episodePlaybackSettled,
                          showControls: false,
                          verifiedDuration: item.verifiedDuration,
                          onTap: widget.isVisible
                              ? () => _togglePlayback(identity)
                              : null,
                          playbackSession: session,
                          onPlaybackSessionCreated: (registeredSession) =>
                              _registerSession(
                                index,
                                identity,
                                registeredSession,
                              ),
                        ),
                      ),
                      _WorksPausedPlaybackOverlay(session: session),
                    ],
                  ),
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

class _WorksPausedPlaybackOverlay extends StatelessWidget {
  const _WorksPausedPlaybackOverlay({required this.session});

  final VideoPlaybackSession session;

  @override
  Widget build(BuildContext context) {
    return IgnorePointer(
      child: AnimatedBuilder(
        animation: session,
        builder: (context, _) {
          final snapshot = session.snapshot;
          final show =
              snapshot.isInitialized &&
              !snapshot.isPlaying &&
              !snapshot.isScrubbing &&
              snapshot.transport != VideoPlaybackTransport.buffering &&
              snapshot.transport != VideoPlaybackTransport.failure;
          return AnimatedOpacity(
            duration: const Duration(milliseconds: 160),
            opacity: show ? 1 : 0,
            child: Center(
              child: const KeyedSubtree(
                key: ValueKey<String>('works-video-paused-play-overlay'),
                child: VideoPlaybackCenterPlayGlyph(),
              ),
            ),
          );
        },
      ),
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
            bottom: WorksImmersiveContentLayout.overlayBottomClearance(
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
              bottom: WorksImmersiveContentLayout.overlayBottomClearance(
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

@immutable
class _WorksVideoDeliveryItem {
  const _WorksVideoDeliveryItem({
    required this.deliveryReference,
    this.coverReference,
    this.verifiedDuration,
    this.previewTrackDescriptor,
  });

  final MediaDeliveryReference deliveryReference;
  final MediaDeliveryReference? coverReference;
  final Duration? verifiedDuration;
  final VideoPreviewTrackDescriptor? previewTrackDescriptor;

  String get identity => deliveryReference.cacheIdentity;
}
