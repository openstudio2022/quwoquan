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

/// Work Browser 顶部栏：极简，仅「返回」与「更多」。
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

/// 视频作品画布：全屏沉浸视频；作品内分集横滑切换（mediaItems 契约序列）；
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

  final ContentPostViewData post;
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

enum _WorksVideoEpisodeScrollDirection { forward, backward }

class _WorksVideoCanvasState extends State<_WorksVideoCanvas>
    with WidgetsBindingObserver {
  late final PageController _episodeController;
  late int _currentEpisodeIndex;
  bool _episodePlaybackSettled = true;
  bool _forwardPreheatAllowed = true;
  bool _appIsForeground = true;
  bool _preheatSuppressedByMemoryPressure = false;
  _WorksVideoEpisodeScrollDirection? _episodeScrollDirection;
  int _preheatReadinessGeneration = 0;
  Timer? _episodeSettleTimer;
  final Map<String, VideoPlaybackSession> _mountedSessionsByIdentity =
      <String, VideoPlaybackSession>{};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _currentEpisodeIndex = _safeEpisodeIndex(widget.initialEpisodeIndex);
    _episodeController = PageController(initialPage: _currentEpisodeIndex);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      final identity = _currentEpisodeIdentity;
      if (mounted && widget.isVisible && identity != null) {
        widget.onEpisodeChanged(_currentEpisodeIndex, identity);
        widget.onActiveSessionChanged(
          _currentEpisodeIndex,
          identity,
          _mountedSessionsByIdentity[identity],
        );
      }
    });
  }

  @override
  void didUpdateWidget(covariant _WorksVideoCanvas oldWidget) {
    super.didUpdateWidget(oldWidget);
    final episodeReconciled = _reconcileEpisodes(oldWidget);
    if (episodeReconciled) {
      _forwardPreheatAllowed = false;
      _scheduleEpisodePlaybackSettle();
    }
    if (episodeReconciled && widget.isVisible && oldWidget.isVisible) {
      final identity = _currentEpisodeIdentity;
      if (identity != null) {
        widget.onEpisodeChanged(_currentEpisodeIndex, identity);
        widget.onActiveSessionChanged(
          _currentEpisodeIndex,
          identity,
          _mountedSessionsByIdentity[identity],
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
            _mountedSessionsByIdentity[identity],
          );
        }
      }
      return;
    }
    if (widget.isVisible) {
      _forwardPreheatAllowed = !_preheatSuppressedByMemoryPressure;
      final identity = _currentEpisodeIdentity;
      if (identity == null) {
        return;
      }
      widget.onEpisodeChanged(_currentEpisodeIndex, identity);
      widget.onActiveSessionChanged(
        _currentEpisodeIndex,
        identity,
        _mountedSessionsByIdentity[identity],
      );
      return;
    }
    _forwardPreheatAllowed = false;
    _preheatReadinessGeneration += 1;
    final identity = _currentEpisodeIdentity;
    if (identity != null) {
      widget.onActiveSessionChanged(_currentEpisodeIndex, identity, null);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _preheatReadinessGeneration += 1;
    _episodeSettleTimer?.cancel();
    final identity = _currentEpisodeIdentity;
    if (identity != null) {
      widget.onActiveSessionChanged(_currentEpisodeIndex, identity, null);
    }
    // Session ownership belongs to each mounted episode stage. Clearing this
    // non-owning registry must not dispose a session before the stage's
    // VideoPlayerWidget and AnimatedBuilder have unmounted.
    _mountedSessionsByIdentity.clear();
    _episodeController.dispose();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    final foreground = state == AppLifecycleState.resumed;
    if (_appIsForeground == foreground) {
      return;
    }
    setState(() {
      _appIsForeground = foreground;
      _forwardPreheatAllowed =
          foreground && !_preheatSuppressedByMemoryPressure;
      _preheatReadinessGeneration += 1;
    });
  }

  @override
  void didHaveMemoryPressure() {
    if (_preheatSuppressedByMemoryPressure) {
      return;
    }
    setState(() {
      _preheatSuppressedByMemoryPressure = true;
      _forwardPreheatAllowed = false;
      _preheatReadinessGeneration += 1;
    });
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
    if (notification is ScrollStartNotification) {
      _episodeScrollDirection = null;
      _episodeSettleTimer?.cancel();
      if (_episodePlaybackSettled) {
        setState(() => _episodePlaybackSettled = false);
      }
      return false;
    }
    if (notification is ScrollUpdateNotification) {
      _episodeSettleTimer?.cancel();
      if (_episodePlaybackSettled) {
        setState(() => _episodePlaybackSettled = false);
      }
      final delta = notification.scrollDelta ?? 0;
      if (delta == 0) {
        return false;
      }
      final direction = delta > 0
          ? _WorksVideoEpisodeScrollDirection.forward
          : _WorksVideoEpisodeScrollDirection.backward;
      final directionChanged =
          _episodeScrollDirection != null &&
          _episodeScrollDirection != direction;
      _episodeScrollDirection = direction;
      if ((direction == _WorksVideoEpisodeScrollDirection.backward ||
              directionChanged) &&
          _forwardPreheatAllowed) {
        setState(() {
          _forwardPreheatAllowed = false;
          _preheatReadinessGeneration += 1;
        });
      }
      return false;
    }
    if (notification is ScrollEndNotification) {
      _episodeScrollDirection = null;
      _scheduleEpisodePlaybackSettle();
    }
    return false;
  }

  void _scheduleEpisodePlaybackSettle() {
    _episodeSettleTimer?.cancel();
    _episodeSettleTimer = Timer(homeFeedVideoAutoPlayScrollEndDebounce, () {
      if (!mounted) return;
      setState(() {
        _episodePlaybackSettled = true;
        _forwardPreheatAllowed =
            _appIsForeground && !_preheatSuppressedByMemoryPressure;
      });
    });
  }

  void _trackMountedSession(String identity, VideoPlaybackSession session) {
    _mountedSessionsByIdentity[identity] = session;
  }

  void _untrackMountedSession(String identity, VideoPlaybackSession session) {
    if (identical(_mountedSessionsByIdentity[identity], session)) {
      _mountedSessionsByIdentity.remove(identity);
    }
  }

  void _registerSession(
    int index,
    String identity,
    VideoPlaybackSession session,
  ) {
    _mountedSessionsByIdentity[identity] = session;
    if (widget.isVisible && index == _currentEpisodeIndex) {
      widget.onActiveSessionChanged(index, identity, session);
      final generation = ++_preheatReadinessGeneration;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted ||
            generation != _preheatReadinessGeneration ||
            !widget.isVisible ||
            identity != _currentEpisodeIdentity ||
            !identical(_mountedSessionsByIdentity[identity], session) ||
            !session.snapshot.isInitialized) {
          return;
        }
        setState(() {});
      });
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
              final identity = items[index].identity;
              setState(() {
                _currentEpisodeIndex = index;
                _episodePlaybackSettled = false;
                _forwardPreheatAllowed = false;
                _preheatReadinessGeneration += 1;
              });
              _scheduleEpisodePlaybackSettle();
              if (widget.isVisible) {
                widget.onEpisodeChanged(index, identity);
                widget.onActiveSessionChanged(
                  index,
                  identity,
                  _mountedSessionsByIdentity[identity],
                );
              }
            },
            itemBuilder: (context, index) {
              final item = items[index];
              final identity = item.identity;
              final isCurrent = index == _currentEpisodeIndex;
              final currentIdentity = _currentEpisodeIdentity;
              final currentSession = currentIdentity == null
                  ? null
                  : _mountedSessionsByIdentity[currentIdentity];
              final shouldPreheat =
                  widget.isVisible &&
                  _appIsForeground &&
                  !_preheatSuppressedByMemoryPressure &&
                  _forwardPreheatAllowed &&
                  currentSession?.snapshot.isInitialized == true &&
                  index == _currentEpisodeIndex + 1;
              final shouldInitialize =
                  widget.isVisible && (isCurrent || shouldPreheat);
              final keepAlive = shouldInitialize;
              return KeyedSubtree(
                key: ValueKey<String>(
                  'works-video-stage-${widget.post.id}-$index',
                ),
                child: _KeepAliveStage(
                  key: ValueKey<String>(
                    'works-video-stage-identity-${widget.post.id}-$identity',
                  ),
                  keepAlive: keepAlive,
                  child: _WorksVideoEpisodeStage(
                    postId: widget.post.id,
                    index: index,
                    identity: identity,
                    item: item,
                    initialize: shouldInitialize,
                    autoPlay:
                        widget.isVisible &&
                        isCurrent &&
                        _episodePlaybackSettled,
                    tapEnabled: widget.isVisible,
                    onSessionMounted: _trackMountedSession,
                    onSessionReady: _registerSession,
                    onSessionUnmounted: _untrackMountedSession,
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

/// Owns exactly one episode session for as long as that episode subtree is
/// mounted. Flutter unmounts the children before this State is disposed, so the
/// player detaches its controller and AnimatedBuilder removes its listener
/// before this owner disposes the session.
class _WorksVideoEpisodeStage extends StatefulWidget {
  const _WorksVideoEpisodeStage({
    required this.postId,
    required this.index,
    required this.identity,
    required this.item,
    required this.initialize,
    required this.autoPlay,
    required this.tapEnabled,
    required this.onSessionMounted,
    required this.onSessionReady,
    required this.onSessionUnmounted,
  });

  final String postId;
  final int index;
  final String identity;
  final _WorksVideoDeliveryItem item;
  final bool initialize;
  final bool autoPlay;
  final bool tapEnabled;
  final void Function(String identity, VideoPlaybackSession session)
  onSessionMounted;
  final void Function(int index, String identity, VideoPlaybackSession session)
  onSessionReady;
  final void Function(String identity, VideoPlaybackSession session)
  onSessionUnmounted;

  @override
  State<_WorksVideoEpisodeStage> createState() =>
      _WorksVideoEpisodeStageState();
}

class _WorksVideoEpisodeStageState extends State<_WorksVideoEpisodeStage> {
  late final VideoPlaybackSession _session;

  @override
  void initState() {
    super.initState();
    _session = VideoPlaybackSession();
    widget.onSessionMounted(widget.identity, _session);
  }

  @override
  void dispose() {
    widget.onSessionUnmounted(widget.identity, _session);
    _session.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    return Stack(
      fit: StackFit.expand,
      children: [
        KeyedSubtree(
          key: ValueKey<String>('works-video-${widget.postId}-${widget.index}'),
          child: VideoPlayerWidget(
            key: ValueKey<String>(
              'works-video-identity-${widget.postId}-${widget.identity}',
            ),
            deliveryReference: item.deliveryReference,
            adaptiveDeliveryReference: item.adaptiveDeliveryReference,
            adaptiveDescriptorVersion: item.adaptiveDescriptorVersion,
            thumbnailReference: item.coverReference,
            initialize: widget.initialize,
            autoPlay: widget.autoPlay,
            showControls: false,
            verifiedDuration: item.verifiedDuration,
            onTap: widget.tapEnabled
                ? () => unawaited(_session.toggle())
                : null,
            playbackSession: _session,
            onPlaybackSessionCreated: (registeredSession) =>
                widget.onSessionReady(
                  widget.index,
                  widget.identity,
                  registeredSession,
                ),
          ),
        ),
        _WorksPausedPlaybackOverlay(session: _session),
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

  final ContentPostViewData post;
  final ContentArticleRender article;
  final String timeLine;
  final ArticlePaperTexture paperTexture;
  final bool enablePageCurl;
  final ValueChanged<int> onPageChanged;
  final ValueChanged<int> onResolvedPageCountChanged;
  final double topChromeSafeInset;
  final bool reserveContentIntersection;
  final ValueChanged<String>? onFallbackResolved;
  final ValueChanged<WorksArticlePageFlipEvent>? onPageFlipCommitted;
  final ValueChanged<WorksArticlePageCurlAbortEvent>? onPageCurlAborted;
  final ValueChanged<ArticleInlineSpan>? onEntityTap;
  final ImmersiveGestureIntentController? gestureIntentController;
  final int initialPage;
  final VoidCallback? onOverflowPrevious;
  final VoidCallback? onOverflowNext;

  @override
  Widget build(BuildContext context) {
    return buildWorksViewerArticle(
      post: post,
      article: article,
      timeLine: timeLine,
      paperTexture: paperTexture,
      enablePageCurl: enablePageCurl,
      onPageChanged: onPageChanged,
      onResolvedPageCountChanged: onResolvedPageCountChanged,
      topChromeSafeInset: topChromeSafeInset,
      reserveContentIntersection: reserveContentIntersection,
      onFallbackResolved: onFallbackResolved,
      onPageFlipCommitted: onPageFlipCommitted,
      onPageCurlAborted: onPageCurlAborted,
      onEntityTap: onEntityTap,
      gestureIntentController: gestureIntentController,
      initialPage: initialPage,
      onOverflowPrevious: onOverflowPrevious,
      onOverflowNext: onOverflowNext,
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
    required this.identity,
    required this.deliveryReference,
    this.adaptiveDeliveryReference,
    this.adaptiveDescriptorVersion = 0,
    this.coverReference,
    this.verifiedDuration,
    this.previewTrackDescriptor,
  });

  final String identity;
  final MediaDeliveryReference deliveryReference;
  final MediaDeliveryReference? adaptiveDeliveryReference;
  final int adaptiveDescriptorVersion;
  final MediaDeliveryReference? coverReference;
  final Duration? verifiedDuration;
  final VideoPreviewTrackDescriptor? previewTrackDescriptor;
}
