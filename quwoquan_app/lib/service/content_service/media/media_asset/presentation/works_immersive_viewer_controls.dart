part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerLandscapeControls on _WorksImmersiveViewerState {
  static const _chromeIdleDuration = Duration(seconds: 5);

  void _showMediaCaptionSheet(ContentPostViewData post) {
    // 正文展开是覆盖层，收起态测量与媒体档位保持不动。
    unawaited(
      showAppBottomModal<void>(
        context: context,
        builder: (sheetContext) => Align(
          alignment: Alignment.bottomCenter,
          child: SafeArea(
            child: Container(
              color: AppColors.black,
              constraints: BoxConstraints(
                maxHeight:
                    MediaQuery.sizeOf(sheetContext).height *
                    AppSpacing.immersiveCommentSheetRatio,
              ),
              child: SingleChildScrollView(
                child: MediaCaptionBlock(
                  title: _overlayTitleForPost(post),
                  caption: _overlayBodyForPost(post),
                  isExpanded: true,
                  onToggle: () => Navigator.of(sheetContext).pop(),
                  layoutSpec: _layoutSpecForPost(post),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }

  void _closeLandscapeComment() {
    _setMountedState(() => _commentSplitPostId = null);
    _scheduleLandscapeHide();
  }

  Widget _buildLandscapeCommentPanel(
    BuildContext context,
    ContentPostViewData post,
  ) => Positioned.fill(
    child: Stack(
      key: TestKeys.immersiveCommentSplitSheet,
      children: [
        Positioned.fill(
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: _closeLandscapeComment,
            child: ColoredBox(color: AppColors.black.withValues(alpha: 0.38)),
          ),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: FractionallySizedBox(
            widthFactor: AppSpacing.immersiveCommentSheetRatio,
            child: SafeArea(
              child: HomeFeedCrossObjectComposition.immersiveCommentPanel(
                postId: post.id,
                scrollController: _landscapeCommentController,
                entryObservedCommentCount: effectivePostCommentCount(
                  ref,
                  post.id,
                  fallback: post.commentCount,
                ),
                commentContext: widget.initialCommentContext,
                likeCount: effectivePostLikeCount(
                  ref,
                  post.id,
                  fallback: post.likeCount,
                ),
                shareCount: effectivePostShareCount(
                  ref,
                  post.id,
                  fallback: post.shareCount,
                ),
                isLiked: effectivePostLiked(ref, post.id),
                onLikeTap: () => _onLike(post),
                onShareTap: () => _sharePost(
                  context,
                  post,
                  enableIdentityTemplate: ref.read(
                    contentFeatureFlagProvider(
                      'enable_identity_share_template',
                    ),
                  ),
                ),
                onClose: _closeLandscapeComment,
              ),
            ),
          ),
        ),
      ],
    ),
  );

  void _syncImmersiveNavigation() {
    if (widget.isActive) {
      _releasePureMediaNavigation ??=
          ContentViewerComposition.acquirePureMediaNavigation(ref);
    } else {
      _releasePureMediaNavigation?.call();
      _releasePureMediaNavigation = null;
    }
  }

  Future<void> _enterPureMediaLandscape() async {
    if (!mounted || _pureMediaLandscape || _landscapeTransitionInFlight) return;
    final posts = _buildFeed();
    if (posts.isEmpty) return;
    final post = posts[_currentPage.clamp(0, posts.length - 1)];
    final viewport = MediaQuery.sizeOf(context);
    if (viewport.width >= viewport.height) return;
    if (_isImageLikePost(post)) {
      final image = _imageReadiness[post.id];
      if (image?.isReady != true || (image?.aspectRatio ?? 0) <= 1) return;
    } else if (_isVideoLikePost(post)) {
      final session = _activeVideoBinding?.session;
      if (session?.snapshot.isInitialized != true) return;
      final items = _videoItemsFor(post);
      final itemRatio = items.isEmpty
          ? 0.0
          : items[_videoIndexFor(post.id, items)].aspectRatio;
      final ratio = itemRatio > 0
          ? itemRatio
          : (session?.snapshot.mediaAspectRatio ?? 0);
      if (ratio <= 1) return;
    } else {
      return;
    }
    final generation = ++_landscapeGeneration;
    _landscapeTransitionInFlight = true;
    try {
      _gestureIntentController.cancel();
      final session = _activeVideoBinding?.session;
      if (session?.snapshot.isScrubbing ?? false) {
        await session!.endScrub(commit: false);
      }
      if (!mounted || generation != _landscapeGeneration) return;
      _setMountedState(() {
        _portraitViewPadding = MediaQuery.viewPaddingOf(context);
        _pureMediaLandscape = true;
        _landscapeControlsVisible = true;
        _landscapeHeldPointers.clear();
        _landscapePointerDownAt.clear();
        _landscapeVisibilityAtPointerDown.clear();
        _landscapePendingTapVisibilityAtDown = null;
        _landscapeGestureEpoch++;
        _suppressLandscapeCanvasTap = false;
      });
      _observeLandscapeSession(session);
      _setLandscapeSystemChrome(true);
      _scheduleLandscapeHide();
    } finally {
      _landscapeTransitionInFlight = false;
    }
  }

  Future<void> _exitPureMediaLandscape() async {
    ++_landscapeGeneration;
    _invalidateLandscapeHide();
    if (!mounted || !_pureMediaLandscape) return;
    final session = _activeVideoBinding?.session;
    if (session?.snapshot.isScrubbing ?? false) {
      await session!.endScrub(commit: false);
    }
    if (!mounted) return;
    _observeLandscapeSession(null);
    _setLandscapeSystemChrome(false);
    _setMountedState(() {
      _pureMediaLandscape = false;
      _landscapeControlsVisible = true;
      _landscapeHeldPointers.clear();
      _landscapePointerDownAt.clear();
      _landscapeVisibilityAtPointerDown.clear();
      _landscapePendingTapVisibilityAtDown = null;
      _landscapeGestureEpoch++;
      _suppressLandscapeCanvasTap = false;
      _commentSplitPostId = null;
    });
    // 保留当前 session 和最新进度，整段沉浸导航租约不在收起时释放。
  }

  void _setLandscapeSystemChrome(bool hidden) {
    final generation = ++_systemChromeGeneration;
    _systemChromeQueue = _systemChromeQueue.then((_) async {
      if (generation != _systemChromeGeneration) return;
      try {
        await SystemChrome.setEnabledSystemUIMode(
          hidden ? SystemUiMode.immersiveSticky : SystemUiMode.edgeToEdge,
        );
      } catch (error, stack) {
        // 系统强制保留栏不阻断局部模式，也不冒充方向切换失败。
        await _reportSystemChromeFailure(error, stack);
      }
    });
  }

  void _observeLandscapeSession(VideoPlaybackSession? session) {
    if (identical(session, _landscapeObservedSession)) return;
    _landscapeObservedSession?.removeListener(_landscapeSessionChanged);
    _landscapeObservedSession = session;
    session?.addListener(_landscapeSessionChanged);
    _landscapeWaitingForMedia = _landscapeRevealRequiredBlocked;
  }

  void _scheduleLandscapeRouteVisibility(bool routeActive) {
    if (_landscapeRouteActive == routeActive) return;
    _landscapeRouteActive = routeActive;
    final generation = ++_landscapeRouteGeneration;
    _invalidateLandscapeHide();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          !_pureMediaLandscape ||
          generation != _landscapeRouteGeneration) {
        return;
      }
      // 自有菜单仍属于当前查看器，独立作者/登录路由才暂时移交系统栏。
      if (_landscapeModalDepth == 0) {
        _setLandscapeSystemChrome(routeActive);
        _activeVideoBinding?.session.setVisibility(
          routeActive && widget.isActive,
        );
      }
      if (routeActive) {
        _setMountedState(() => _landscapeControlsVisible = true);
        _scheduleLandscapeHide();
      }
    });
  }

  void _handleImageReadiness(String postId, ImageBookCurrentMediaState state) {
    if (!mounted || _imageReadiness[postId] == state) return;
    _setMountedState(() => _imageReadiness[postId] = state);
    final current = _activeTrackedPost;
    if (_pureMediaLandscape && current?.id == postId) {
      _invalidateLandscapeHide();
      if (!state.isReady) {
        _setMountedState(() => _landscapeControlsVisible = true);
      }
      _scheduleLandscapeHide();
    }
  }

  bool get _landscapeRevealRequiredBlocked {
    final snapshot = _landscapeObservedSession?.snapshot;
    final image = _activeTrackedPost == null
        ? null
        : _imageReadiness[_activeTrackedPost!.id];
    return (image != null && !image.isReady) ||
        !_landscapeForeground ||
        !_landscapeRouteActive ||
        _landscapeAccessibleNavigation ||
        !widget.isActive ||
        _landscapeModalDepth > 0 ||
        _commentSplitPostId != null ||
        (snapshot != null &&
            (!snapshot.isInitialized ||
                snapshot.isScrubbing ||
                snapshot.isBuffering ||
                snapshot.transport == VideoPlaybackTransport.failure));
  }

  void _landscapeSessionChanged() {
    if (!mounted || !_pureMediaLandscape || _landscapeControlRefreshScheduled) {
      return;
    }
    _landscapeControlRefreshScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _landscapeControlRefreshScheduled = false;
      if (!mounted || !_pureMediaLandscape) return;
      final blocked = _landscapeRevealRequiredBlocked;
      if (blocked) {
        _invalidateLandscapeHide();
        if (!_landscapeControlsVisible) {
          _setMountedState(() => _landscapeControlsVisible = true);
        }
      } else if (_landscapeWaitingForMedia) {
        _scheduleLandscapeHide();
      }
      _landscapeWaitingForMedia = blocked;
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  void _invalidateLandscapeHide() {
    _landscapeControlsTimer?.cancel();
    _landscapeControlsTimer = null;
    _landscapeChromeEpoch++;
  }

  String? get _landscapeMediaIdentity {
    final post = _activeTrackedPost;
    if (post == null) return null;
    final video = _activeVideoBinding;
    if (video != null && video.postId == post.id) {
      return '${post.id}|${video.episodeIdentity}|${video.episodeIndex}|${video.viewportEpoch}';
    }
    final image = _imageReadiness[post.id];
    return '${post.id}|image|${image?.index ?? -1}';
  }

  void _scheduleLandscapeHide() {
    _invalidateLandscapeHide();
    if (!_pureMediaLandscape ||
        !_landscapeControlsVisible ||
        _landscapeRevealRequiredBlocked ||
        _landscapeHeldPointers.isNotEmpty) {
      return;
    }
    final epoch = _landscapeChromeEpoch;
    final generation = _landscapeGeneration;
    final mediaIdentity = _landscapeMediaIdentity;
    final session = _landscapeObservedSession;
    _landscapeControlsTimer = Timer(_chromeIdleDuration, () {
      if (!mounted ||
          epoch != _landscapeChromeEpoch ||
          generation != _landscapeGeneration ||
          mediaIdentity != _landscapeMediaIdentity ||
          !identical(session, _landscapeObservedSession) ||
          !_pureMediaLandscape ||
          _landscapeRevealRequiredBlocked ||
          _landscapeHeldPointers.isNotEmpty) {
        return;
      }
      _landscapeControlsTimer = null;
      _setMountedState(() => _landscapeControlsVisible = false);
    });
  }

  bool get _landscapeCanvasTapAllowed {
    if (!_pureMediaLandscape || _commentSplitPostId != null) return false;
    final snapshot = _landscapeObservedSession?.snapshot;
    final image = _activeTrackedPost == null
        ? null
        : _imageReadiness[_activeTrackedPost!.id];
    return !((snapshot != null &&
            (!snapshot.isInitialized ||
                snapshot.isBuffering ||
                snapshot.transport == VideoPlaybackTransport.failure)) ||
        (image != null && !image.isReady));
  }

  void _revealLandscapeChrome() {
    if (!_landscapeCanvasTapAllowed) return;
    _invalidateLandscapeHide();
    if (!_landscapeControlsVisible) {
      _setMountedState(() => _landscapeControlsVisible = true);
    }
    _scheduleLandscapeHide();
  }

  void _hideLandscapeChrome() {
    if (!_landscapeCanvasTapAllowed) return;
    _invalidateLandscapeHide();
    if (_landscapeControlsVisible) {
      _setMountedState(() => _landscapeControlsVisible = false);
    }
  }

  void _handleLandscapeCanvasTap() {
    final visibilityAtDown =
        _landscapePendingTapVisibilityAtDown ?? _landscapeControlsVisible;
    _landscapePendingTapVisibilityAtDown = null;
    if (_suppressLandscapeCanvasTap) {
      _suppressLandscapeCanvasTap = false;
      return;
    }
    if (!visibilityAtDown) {
      _revealLandscapeChrome();
    } else {
      _hideLandscapeChrome();
    }
  }

  void _landscapePointerDown(PointerDownEvent event) {
    if (!_pureMediaLandscape) return;
    _landscapeHeldPointers.add(event.pointer);
    _landscapePointerDownAt[event.pointer] = event.timeStamp;
    _landscapeVisibilityAtPointerDown[event.pointer] =
        _landscapeControlsVisible;
    _landscapeGestureEpoch++;
    _invalidateLandscapeHide();
  }

  void _landscapePointerEnd(PointerEvent event) {
    if (!_pureMediaLandscape) return;
    final downAt = _landscapePointerDownAt.remove(event.pointer);
    final visibilityAtDown = _landscapeVisibilityAtPointerDown.remove(
      event.pointer,
    );
    _landscapeHeldPointers.remove(event.pointer);
    final isCancel = event is PointerCancelEvent;
    final isLongPress =
        downAt != null && event.timeStamp - downAt >= kLongPressTimeout;
    if (isCancel || isLongPress) {
      _suppressLandscapeCanvasTap = true;
    } else if (visibilityAtDown != null) {
      _landscapePendingTapVisibilityAtDown = visibilityAtDown;
    }
    final gestureEpoch = _landscapeGestureEpoch;
    scheduleMicrotask(() {
      if (gestureEpoch != _landscapeGestureEpoch) return;
      _suppressLandscapeCanvasTap = false;
      _landscapePendingTapVisibilityAtDown = null;
    });
    if (_landscapeControlsVisible) _scheduleLandscapeHide();
  }

  Future<void> _withLandscapeModal(Future<void> Function() action) async {
    _landscapeModalDepth++;
    _invalidateLandscapeHide();
    try {
      await action();
    } finally {
      _landscapeModalDepth--;
      if (mounted) _scheduleLandscapeHide();
    }
  }

  List<Widget> _landscapeShadeLayers(BuildContext context) => [
    Positioned(
      top: 0,
      left: 0,
      right: 0,
      height:
          MediaQuery.viewPaddingOf(context).top +
          AppSpacing.appChromeTopBarHeight(context),
      child: _landscapeChrome(_landscapeShade(top: true)),
    ),
    Positioned(
      bottom: 0,
      left: 0,
      right: 0,
      height:
          ImmersiveEngagementBar.reservedHeight(context) +
          AppSpacing.minInteractiveSize,
      child: _landscapeChrome(_landscapeShade(top: false)),
    ),
  ];

  Widget _landscapeShade({required bool top}) => IgnorePointer(
    child: DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: top ? Alignment.topCenter : Alignment.bottomCenter,
          end: top ? Alignment.bottomCenter : Alignment.topCenter,
          colors: [
            AppColors.black.withValues(alpha: 0.38),
            AppColors.transparent,
          ],
        ),
      ),
    ),
  );

  Widget _landscapeChrome(Widget child) => Visibility(
    visible: !_pureMediaLandscape || _landscapeControlsVisible,
    maintainState: true,
    maintainAnimation: true,
    child: child,
  );

  Widget _buildViewport(BuildContext context) => _WorksRotatedViewport(
    landscape: _pureMediaLandscape,
    safePadding: _pureMediaLandscape ? _portraitViewPadding : null,
    builder: (viewportContext) => _WorksModalOrientationTheme(
      landscape: _pureMediaLandscape,
      child: CallbackShortcuts(
        bindings: {
          const SingleActivator(LogicalKeyboardKey.escape): () {
            if (_commentSplitPostId != null) {
              _closeLandscapeComment();
            } else if (_pureMediaLandscape) {
              unawaited(_exitPureMediaLandscape());
            }
          },
        },
        child: Focus(autofocus: true, child: Builder(builder: _buildViewer)),
      ),
    ),
  );
}

/// 始终保留同一宿主结构，切换 quarterTurns 不卸载播放器/图片书。
class _WorksRotatedViewport extends StatelessWidget {
  const _WorksRotatedViewport({
    required this.landscape,
    required this.builder,
    this.safePadding,
  });
  final bool landscape;
  final EdgeInsets? safePadding;
  final WidgetBuilder builder;

  @override
  Widget build(BuildContext context) => LayoutBuilder(
    builder: (context, constraints) {
      final query = MediaQuery.of(context);
      final physical = constraints.biggest;
      EdgeInsets rotate(EdgeInsets value) => landscape
          ? EdgeInsets.fromLTRB(
              value.top,
              value.right,
              value.bottom,
              value.left,
            )
          : value;
      final logical = landscape
          ? Size(physical.height, physical.width)
          : physical;
      return RotatedBox(
        key: const ValueKey('works-media-viewport'),
        quarterTurns: landscape ? 1 : 0,
        child: MediaQuery(
          data: query.copyWith(
            size: logical,
            padding: rotate(safePadding ?? query.padding),
            viewPadding: rotate(safePadding ?? query.viewPadding),
            viewInsets: rotate(query.viewInsets),
            systemGestureInsets: rotate(query.systemGestureInsets),
          ),
          child: Builder(builder: builder),
        ),
      );
    },
  );
}

/// 现有 modal presenter 捕获主题时，把局部方向一并带到根弹层。
/// 只包裹查看器发起的 App 弹层，不旋转作者路由或系统原生面板。
class _WorksModalOrientationTheme extends InheritedTheme {
  const _WorksModalOrientationTheme({
    required this.landscape,
    required super.child,
  });
  final bool landscape;
  @override
  bool updateShouldNotify(_WorksModalOrientationTheme oldWidget) =>
      landscape != oldWidget.landscape;
  @override
  Widget wrap(BuildContext context, Widget child) =>
      _WorksRotatedViewport(landscape: landscape, builder: (_) => child);
}

class _MediaLandscapeButton extends StatelessWidget {
  const _MediaLandscapeButton({super.key, required this.onPressed});

  final VoidCallback? onPressed;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayForeground,
    );
    final background = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayScrim,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.mediaThumbnailOverlayBorder,
    );
    return Semantics(
      button: true,
      label: AppLocalizations.of(context).media_enterFullscreen,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: onPressed,
        child: ClipRRect(
          borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
          child: BackdropFilter(
            filter: ImageFilter.blur(
              sigmaX: AppSpacing.sm,
              sigmaY: AppSpacing.sm,
            ),
            child: DecoratedBox(
              key: const ValueKey('works-media-landscape-entry-glass'),
              decoration: BoxDecoration(
                color: background,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(color: border, width: AppSpacing.hairline),
              ),
              child: SizedBox(
                height: AppSpacing.buttonHeightSm,
                child: Padding(
                  padding: const EdgeInsets.symmetric(
                    horizontal: AppSpacing.interGroupSm,
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        CupertinoIcons.arrow_up_left_arrow_down_right,
                        color: foreground,
                        size: AppSpacing.iconSmall,
                      ),
                      const SizedBox(width: AppSpacing.interGroupXs),
                      Flexible(
                        child: Text(
                          AppLocalizations.of(context).media_enterFullscreen,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            color: foreground,
                            fontSize: AppTypography.sm,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _WorksPageIndicator extends StatelessWidget {
  const _WorksPageIndicator({required this.total, required this.current});

  final int total;
  final int current;
  static const int _maxVisibleDots = 6;

  @override
  Widget build(BuildContext context) {
    final currentIndex = (current - 1).clamp(0, total - 1).toInt();
    final visibleCount = total.clamp(1, _maxVisibleDots).toInt();
    final windowStart = total <= _maxVisibleDots
        ? 0
        : (currentIndex - 2).clamp(0, total - visibleCount).toInt();
    final indicator = Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(visibleCount, (visibleIndex) {
        final absoluteIndex = windowStart + visibleIndex;
        final selected = absoluteIndex == currentIndex;
        final hasLeadingOverflow = windowStart > 0 && visibleIndex == 0;
        final hasTrailingOverflow =
            windowStart + visibleCount < total &&
            visibleIndex == visibleCount - 1;
        final alpha = selected
            ? 0.94
            : (absoluteIndex < currentIndex && hasLeadingOverflow) ||
                  (absoluteIndex > currentIndex && hasTrailingOverflow)
            ? 0.18
            : 0.38;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 220),
          curve: Curves.easeOutCubic,
          margin: const EdgeInsets.symmetric(horizontal: 1.5),
          width: AppSpacing.xs + AppSpacing.hairline,
          height: AppSpacing.xs + AppSpacing.hairline,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.white.withValues(alpha: alpha),
          ),
        );
      }),
    );
    return IgnorePointer(
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 10, sigmaY: 10),
          child: DecoratedBox(
            key: const ValueKey<String>('works-page-indicator'),
            decoration: BoxDecoration(
              color: AppColors.black.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(
                AppSpacing.circularBorderRadius,
              ),
              border: Border.all(
                color: AppColors.white.withValues(alpha: 0.06),
                width: AppSpacing.hairline,
              ),
            ),
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.intraGroupSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              child: indicator,
            ),
          ),
        ),
      ),
    );
  }
}

class _WorksVideoSeriesBadge extends StatelessWidget {
  const _WorksVideoSeriesBadge({
    required this.episodeCurrent,
    required this.episodeTotal,
  });

  final int episodeCurrent;
  final int episodeTotal;

  @override
  Widget build(BuildContext context) {
    return Container(
      key: const ValueKey<String>('works-video-series-badge'),
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.intraGroupSm,
        vertical: AppSpacing.intraGroupXs / 2,
      ),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.28),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        border: Border.all(color: AppColors.white.withValues(alpha: 0.14)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            UITextConstants.videoSeriesProgress(episodeCurrent, episodeTotal),
            style: TextStyle(
              color: AppColors.white.withValues(alpha: 0.88),
              fontSize: AppTypography.xxs,
              fontWeight: AppTypography.medium,
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupXs),
          Icon(
            CupertinoIcons.arrow_right_arrow_left,
            size: AppTypography.xxs,
            color: AppColors.white.withValues(alpha: 0.66),
          ),
        ],
      ),
    );
  }
}

class _WorksArticlePageChevron extends StatelessWidget {
  const _WorksArticlePageChevron({
    super.key,
    required this.icon,
    required this.enabled,
    required this.color,
    required this.onTap,
  });

  final IconData icon;
  final bool enabled;
  final Color color;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: enabled ? onTap : null,
      child: SizedBox(
        width: AppSpacing.minInteractiveSize / 2,
        height: AppSpacing.minInteractiveSize / 2,
        child: Center(
          child: Icon(
            icon,
            size: AppTypography.sm,
            color: color.withValues(alpha: enabled ? 1 : 0.32),
          ),
        ),
      ),
    );
  }
}
