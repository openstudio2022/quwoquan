part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerBuild on _WorksImmersiveViewerState {
  Widget _buildViewer(BuildContext context) {
    ref.listen<AuthSessionState>(authSessionControllerProvider, (
      AuthSessionState? previous,
      AuthSessionState next,
    ) {
      if (next.isAuthenticated &&
          (previous == null || !previous.isAuthenticated)) {
        _scheduleAuthContinuationResume();
      }
    });
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      _scheduleAuthContinuationResume();
    }
    ref.watch(postInteractionStateProvider);
    ref.watch(userRelationshipStateProvider);
    ref.watch(contentRuntimeConfigProvider);
    ref.watch(activePersonaContextProvider);
    final enableArticlePageCurl = _enableArticlePageCurl;
    final posts = _buildFeed();
    final showLoadMoreSentinel =
        !_usesExternalFeed &&
        posts.isNotEmpty &&
        (_trackedFeedsHaveMore() ||
            _trackedFeedsLoading() ||
            _trackedFeedsError() != null);
    final isOnLoadMoreSentinel =
        showLoadMoreSentinel && _currentPage >= posts.length;
    final currentPost = posts.isEmpty || isOnLoadMoreSentinel
        ? null
        : posts[_currentPage.clamp(0, posts.length - 1)];
    final loadMoreError = !_usesExternalFeed ? _trackedFeedsError() : null;
    final isLoadingMore = !_usesExternalFeed && _trackedFeedsLoading();
    if (posts.isNotEmpty) {
      _schedulePrefetch(
        visibleIndex: _currentPage.clamp(0, posts.length),
        postsLength: posts.length,
        force: isOnLoadMoreSentinel,
      );
    }
    if (_awaitingPrefetchedReveal && currentPost != null) {
      final revealedPost = currentPost;
      final revealedIndex = _currentPage;
      _awaitingPrefetchedReveal = false;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        widget.onPostIndexChanged?.call(revealedIndex);
        _trackImpressionForPost(revealedPost, position: revealedIndex);
      });
    }
    final commentSplitPost = _commentSplitPostId == null
        ? null
        : _postById(posts, _commentSplitPostId!);
    if (commentSplitPost != null) {
      final interaction = ref.watch(postInteractionStateProvider);
      final splitPostId = commentSplitPost.id;
      // 评论分屏复用沉浸式状态栏样式（透明 + 浅色图标），避免回落为白底。
      return AnnotatedRegion<SystemUiOverlayStyle>(
        value: const SystemUiOverlayStyle(
          statusBarColor: AppColors.transparent,
          statusBarIconBrightness: Brightness.light,
          statusBarBrightness: Brightness.dark,
        ),
        child: DefaultTextStyle.merge(
          style: const TextStyle(
            decoration: TextDecoration.none,
            decorationThickness: 0,
          ),
          child: HomeFeedCrossObjectComposition.immersiveCommentSplit(
            postId: splitPostId,
            content: _buildCommentSplitContent(commentSplitPost),
            entryObservedCommentCount: interaction.commentCountFor(
              splitPostId,
              fallback: commentSplitPost.commentCount,
            ),
            commentContext: widget.initialCommentContext,
            likeCount: interaction.likeCountFor(splitPostId),
            shareCount: effectivePostShareCount(
              ref,
              splitPostId,
              fallback: commentSplitPost.shareCount,
            ),
            isLiked: interaction.isLiked(splitPostId),
            onLikeTap: () => _onLike(commentSplitPost),
            onShareTap: () => _sharePost(
              context,
              commentSplitPost,
              enableIdentityTemplate: ref.read(
                contentFeatureFlagProvider('enable_identity_share_template'),
              ),
            ),
            onClose: () {
              _setMountedState(() {
                _commentSplitPostId = null;
                _invalidateVideoViewport(resetDurationWindow: false);
              });
            },
          ),
        ),
      );
    }
    final currentLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _layoutSpecForPost(currentPost);
    final currentEngagementLayoutSpec = currentPost == null
        ? ImmersiveViewerStageLayoutSpec.feedRail
        : _engagementLayoutSpecForPost(currentPost);
    final progress = _innerProgress(posts);
    final overlayTitle = currentPost == null
        ? ''
        : _overlayTitleForPost(currentPost);
    final overlayBody = currentPost == null
        ? ''
        : _overlayBodyForPost(currentPost);
    final topChromeTheme = _topChromeThemeForPost(context, currentPost);
    final intersectionReason = currentPost == null
        ? null
        : _primaryIntersectionReasonFor(currentPost);
    final showContentIntersection = intersectionReason != null;
    // caption header（内容下方、标题上方）：
    // - 图片多图：点指示器（● ● ○ ● ●，最多 6 点）
    // - 视频：由统一 bottom chrome 装配视频集进度、caption 与时间轴
    Widget? captionHeader;
    Widget? videoBottomChrome;
    Widget? videoIntersection;
    if (currentPost != null) {
      if (_isImageLikePost(currentPost) && progress.total > 1) {
        captionHeader = _WorksPageIndicator(
          total: progress.total,
          current: progress.current,
        );
      } else if (_isVideoLikePost(currentPost)) {
        final sharedTimelineEnabled = ref.watch(
          contentFeatureFlagProvider('enable_shared_video_timeline'),
        );
        final previewEnabled = ref.watch(
          contentFeatureFlagProvider('enable_video_timeline_preview'),
        );
        final videoItems = _videoItemsFor(currentPost);
        final activeVideoIndex = _videoIndexFor(currentPost.id, videoItems);
        final activeVideoItem =
            activeVideoIndex >= 0 && activeVideoIndex < videoItems.length
            ? videoItems[activeVideoIndex]
            : null;
        final activeVideoIdentity = activeVideoItem?.identity;
        final activeBinding = _activeVideoBinding;
        videoIntersection = intersectionReason == null
            ? null
            : HomeFeedCrossObjectComposition.immersiveIntersectionStatement(
                key: const ValueKey<String>(
                  'works-caption-intersection-reason',
                ),
                reason: intersectionReason,
                contextObjectName: currentPost.normalizedTitle.trim().isNotEmpty
                    ? currentPost.normalizedTitle.trim()
                    : currentPost.normalizedBody.trim(),
                contextObjectTarget: IntersectionTarget(
                  objectType: 'post',
                  objectId: currentPost.id,
                  objectKind: 'content',
                  routeId: 'workBrowser',
                ),
                onSpanTap: (span) => _openIntersectionSpan(
                  context,
                  currentPost,
                  intersectionReason,
                  span,
                ),
                onFallbackTap: () => _openIntersectionFallback(
                  context,
                  currentPost,
                  intersectionReason,
                ),
              );
        videoBottomChrome = _WorksVideoBottomChrome(
          key: ValueKey<String>(
            'works-video-chrome-${currentPost.id}-'
            '${activeVideoIdentity ?? 'unresolved'}-'
            '$_videoDurationWindowRevision',
          ),
          layoutSpec: currentLayoutSpec,
          intersection: videoIntersection,
          title: overlayTitle,
          caption: overlayBody,
          sourceAttribution: currentPost.sourceAttribution,
          isExpanded: _isCaptionExpanded(currentPost.id),
          onToggleCaption: () => _toggleCaptionExpanded(currentPost.id),
          session:
              activeVideoIdentity != null &&
                  activeBinding?.postId == currentPost.id &&
                  activeBinding?.episodeIdentity == activeVideoIdentity &&
                  activeBinding?.episodeIndex == activeVideoIndex &&
                  activeBinding?.viewportEpoch == _videoViewportEpoch
              ? activeBinding?.session
              : null,
          durationWindowActive: _videoDurationWindowActive,
          sharedTimelineEnabled: sharedTimelineEnabled,
          previewTrackDescriptor: previewEnabled
              ? activeVideoItem?.previewTrackDescriptor
              : null,
          previewTrackQuery: ref.watch(videoPreviewTrackQueryProvider),
          episodeCurrent: progress.current,
          episodeTotal: progress.total,
        );
      }
    }
    // 与 welcome_screen 一致：阻断 MaterialApp 默认 TextStyle 合并带来的误装饰（黄下划线等）。
    return DefaultTextStyle.merge(
      style: const TextStyle(
        decoration: TextDecoration.none,
        decorationThickness: 0,
      ),
      child: AnnotatedRegion<SystemUiOverlayStyle>(
        value: topChromeTheme.overlayStyle,
        child: GestureDetector(
          behavior: HitTestBehavior.deferToChild,
          onTap: () {
            if (!widget.showWorksToolbar) widget.onHideSystemNav?.call();
          },
          child: Stack(
            fit: StackFit.expand,
            children: [
              Positioned(
                top: 0,
                left: 0,
                right: 0,
                bottom: 0,
                child: Listener(
                  onPointerDown: _handleImmersivePointerDown,
                  onPointerMove: _handleImmersivePointerMove,
                  onPointerUp: (_) {
                    _handleImmersivePointerEnd();
                  },
                  onPointerCancel: (_) {
                    _gestureIntentController.cancel();
                  },
                  child: PageView.builder(
                    key: TestKeys.worksImmersivePager,
                    controller: _pageController,
                    scrollDirection: Axis.vertical,
                    physics: WorksImmersiveVerticalPagePhysics(
                      currentPage: () => _currentPage,
                      holdVerticalScroll: () =>
                          _gestureIntentController.shouldHoldVerticalScroll,
                    ),
                    itemCount: posts.isEmpty
                        ? 1
                        : posts.length + (showLoadMoreSentinel ? 1 : 0),
                    onPageChanged: (index) {
                      if (_currentPage != index) {
                        // Flush dwell time for the previous post
                        if (posts.isNotEmpty && _currentPage < posts.length) {
                          final prevPost =
                              posts[_currentPage.clamp(0, posts.length - 1)];
                          _flushDwell(prevPost, trackSkip: true);
                        }

                        final nextIsSentinel =
                            showLoadMoreSentinel && index >= posts.length;
                        _setMountedState(() {
                          _currentPage = index;
                          _awaitingPrefetchedReveal = nextIsSentinel;
                          _invalidateVideoViewport(resetDurationWindow: true);
                          _retainPostLocalStateAround(posts, index);
                        });
                        _feedPerformanceObservability
                            .recordActiveVideoControllerCount(
                              surfaceId: 'works_immersive_viewer',
                              activeCount: 0,
                            );
                        if (nextIsSentinel) {
                          _articleHydrationAdmission.retainOnly(null);
                          _pageEnterTime = null;
                          _schedulePrefetch(
                            visibleIndex: index,
                            postsLength: posts.length,
                            force: true,
                          );
                          return;
                        }
                        widget.onPostIndexChanged?.call(index);
                        final newPost = posts[index.clamp(0, posts.length - 1)];
                        _trackImpressionForPost(newPost, position: index);
                      }
                    },
                    itemBuilder: (context, index) {
                      if (posts.isEmpty) {
                        if (_usesExternalFeed && _externalEmptyTimedOut) {
                          return AppPageErrorState(
                            key: const ValueKey<String>(
                              'works-external-empty-exit',
                            ),
                            semantic: AppUserRecoveryContract.semanticFor(
                              group: AppUserRecoveryGroup.contentUnavailable,
                              category: UiErrorCategory.notFound,
                              scope: UiErrorScope.page,
                              presentation: UiErrorPresentation.emptyPage,
                              appearanceMode: UiErrorAppearanceMode.dark,
                            ),
                            onRecovery: (_) async {
                              _dismissViewer();
                              return UiRecoveryOutcome.handedOff;
                            },
                          );
                        }
                        return AppRequestFeedback.section();
                      }
                      if (showLoadMoreSentinel && index >= posts.length) {
                        return _buildLoadMoreSentinel(
                          isLoading: isLoadingMore,
                          error: loadMoreError,
                          onRetry: () => _schedulePrefetch(
                            visibleIndex: index,
                            postsLength: posts.length,
                            force: true,
                          ),
                        );
                      }
                      final post = posts[index];
                      return Padding(
                        padding: EdgeInsets.only(
                          top: _statusBarContentInsetFor(post),
                        ),
                        child: KeyedSubtree(
                          key: ValueKey<String>(
                            'works-status-content-canvas-${post.id}',
                          ),
                          child: _buildPostCanvas(
                            post,
                            enableArticlePageCurl: enableArticlePageCurl,
                            isVisible: index == _currentPage,
                            videoViewportEpoch: _videoViewportEpoch,
                          ),
                        ),
                      );
                    },
                  ),
                ),
              ),

              _buildEdgeDismissHotzone(TabSwipeDirection.previous),
              _buildEdgeDismissHotzone(TabSwipeDirection.next),

              if (currentPost != null &&
                  _isArticleLikePost(currentPost) &&
                  widget.topChromeSafeInset > AppSpacing.zero)
                Positioned(
                  key: const ValueKey<String>('works-article-status-bar-scrim'),
                  top: 0,
                  left: 0,
                  right: 0,
                  height: widget.topChromeSafeInset,
                  child: const ColoredBox(color: AppColors.black),
                ),

              Positioned(
                top: 0,
                left: 0,
                right: 0,
                child: Padding(
                  padding: EdgeInsets.only(top: widget.topChromeSafeInset),
                  child: _WorksPrimaryTopBar(
                    layoutSpec: currentLayoutSpec,
                    foregroundColor: topChromeTheme.foregroundColor,
                    onTapClose: _dismissViewer,
                    onTapMore: () => _showWorksMoreSheet(context),
                    onHorizontalDragEnd: _handlePrimaryTabSwipeDragEnd,
                  ),
                ),
              ),

              if (currentPost != null &&
                  videoBottomChrome == null &&
                  _showsCaptionOverlay(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: WorksImmersiveContentLayout.overlayBottomClearance(
                    context,
                    includeIntersection: showContentIntersection,
                    gap: AppSpacing.containerSm,
                  ),
                  child: MediaCaptionBlock(
                    layoutSpec: currentLayoutSpec,
                    railKey: const ValueKey<String>('works-caption-rail'),
                    header: captionHeader,
                    title: overlayTitle,
                    caption: overlayBody,
                    isExpanded: _isCaptionExpanded(currentPost.id),
                    onToggle: () => _toggleCaptionExpanded(currentPost.id),
                  ),
                ),

              if (currentPost != null && videoBottomChrome != null)
                Positioned.fill(child: videoBottomChrome),

              // 文章页码：正文下方、作者工具栏上方（`‹ 1 / 6 ›`，chevron 可点切页）。
              if (currentPost != null && _isArticleLikePost(currentPost))
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: WorksImmersiveContentLayout.overlayBottomClearance(
                    context,
                    includeIntersection: showContentIntersection,
                    gap: AppSpacing.intraGroupSm,
                  ),
                  child: Center(
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        _WorksArticlePageChevron(
                          key: const ValueKey<String>(
                            'works-article-page-prev',
                          ),
                          icon: CupertinoIcons.chevron_back,
                          enabled: progress.current > 1,
                          color: topChromeTheme.mutedForegroundColor,
                          onTap: () => _stepArticlePage(currentPost, -1),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        Text(
                          UITextConstants.workArticlePageProgress(
                            progress.current,
                            progress.total,
                          ),
                          key: const ValueKey<String>(
                            'works-article-page-progress',
                          ),
                          style: TextStyle(
                            color: topChromeTheme.mutedForegroundColor,
                            fontSize: AppTypography.xs,
                            fontWeight: AppTypography.medium,
                            fontFeatures: const [FontFeature.tabularFigures()],
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs),
                        _WorksArticlePageChevron(
                          key: const ValueKey<String>(
                            'works-article-page-next',
                          ),
                          icon: CupertinoIcons.chevron_forward,
                          enabled: progress.current < progress.total,
                          color: topChromeTheme.mutedForegroundColor,
                          onTap: () => _stepArticlePage(currentPost, 1),
                        ),
                      ],
                    ),
                  ),
                ),

              if (currentPost != null &&
                  intersectionReason != null &&
                  videoBottomChrome == null)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom:
                      WorksImmersiveContentLayout.intersectionBottomClearance(
                        context,
                      ),
                  child: ImmersiveViewerLayout.alignToRail(
                    context: context,
                    layoutSpec: currentEngagementLayoutSpec,
                    includeBottomSafeSideInset: true,
                    child: SizedBox(
                      key: const ValueKey<String>(
                        'works-caption-intersection-reason',
                      ),
                      width: double.infinity,
                      child:
                          HomeFeedCrossObjectComposition.immersiveIntersectionStatement(
                            reason: intersectionReason,
                            contextObjectName:
                                currentPost.normalizedTitle.trim().isNotEmpty
                                ? currentPost.normalizedTitle.trim()
                                : currentPost.normalizedBody.trim(),
                            contextObjectTarget: IntersectionTarget(
                              objectType: 'post',
                              objectId: currentPost.id,
                              objectKind: 'content',
                              routeId: 'workBrowser',
                            ),
                            onSpanTap: (span) => _openIntersectionSpan(
                              context,
                              currentPost,
                              intersectionReason,
                              span,
                            ),
                            onFallbackTap: () => _openIntersectionFallback(
                              context,
                              currentPost,
                              intersectionReason,
                            ),
                          ),
                    ),
                  ),
                ),

              if (currentPost != null && widget.showWorksToolbar)
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: 0,
                  child: Builder(
                    builder: (context) {
                      return ImmersiveEngagementBar(
                        layoutSpec: currentEngagementLayoutSpec,
                        avatarUrl: currentPost.avatarUrl,
                        displayName: currentPost.displayName,
                        authorBadge:
                            _workItemFor(currentPost).authorBadge ?? '',
                        likeCount: effectivePostLikeCount(
                          ref,
                          currentPost.id,
                          fallback: currentPost.likeCount,
                        ),
                        shareCount: effectivePostShareCount(
                          ref,
                          currentPost.id,
                          fallback: currentPost.shareCount,
                        ),
                        commentCount: effectivePostCommentCount(
                          ref,
                          currentPost.id,
                          fallback: currentPost.commentCount,
                        ),
                        isLiked: effectivePostLiked(ref, currentPost.id),
                        isFollowing: effectiveProfileFollowing(
                          ref,
                          currentPost.personaId,
                        ),
                        onUserTap: () {
                          // §7.3 旅程无断点：携该作品的最强证据组 kind 跳作者主页高亮。
                          ref
                              .read(
                                intersectionHighlightIntentProvider.notifier,
                              )
                              .primeFromReasons(
                                currentPost.personaId,
                                currentPost.intersectionReasons,
                              );
                          widget.onUserTap(
                            currentPost.personaId,
                            avatarUrl: currentPost.avatarUrl,
                            displayName: currentPost.displayName,
                            backgroundUrl: currentPost.authorBackgroundUrl,
                          );
                        },
                        onFollowTap: () => _onFollow(currentPost),
                        onLikeTap: () => _onLike(currentPost),
                        onCommentTap: () => _openCommentFor(currentPost.id),
                        onShareTap: () => _sharePost(
                          context,
                          currentPost,
                          enableIdentityTemplate: ref.read(
                            contentFeatureFlagProvider(
                              'enable_identity_share_template',
                            ),
                          ),
                        ),
                        onRevealSystemNav: widget.onRevealSystemNav,
                      );
                    },
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPostCanvas(
    ContentPostViewData post, {
    required bool enableArticlePageCurl,
    required bool isVisible,
    required int videoViewportEpoch,
  }) {
    return _buildTypedCanvas(
      post,
      enableArticlePageCurl: enableArticlePageCurl,
      isVisible: isVisible,
      videoViewportEpoch: videoViewportEpoch,
    );
  }

  Widget _buildLoadMoreSentinel({
    required bool isLoading,
    required Object? error,
    required VoidCallback onRetry,
  }) {
    final hasError = error != null;
    return ColoredBox(
      key: TestKeys.worksLoadMoreSentinel,
      color: AppColors.black,
      child: Center(
        child: Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (hasError)
                AppListAppendErrorFooter(
                  key: const ValueKey<String>('works-load-more-retry'),
                  semantic: runtime_error_display.runtimeErrorSemantic(
                    context,
                    error: error,
                    category: UiErrorCategory.listAppend,
                    scope: UiErrorScope.section,
                    presentation: UiErrorPresentation.appendFooter,
                  ),
                  onAction: isLoading
                      ? null
                      : (action) async {
                          if (action.type == UiErrorActionType.retry ||
                              action.type == UiErrorActionType.resubmit) {
                            onRetry();
                          }
                        },
                )
              else ...[
                AppRequestFeedback.inline(),
                SizedBox(height: AppSpacing.containerSm),
                Text(
                  DiscoveryText.worksVideoBookLoadingTitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.body,
                    fontWeight: AppTypography.semiBold,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupSm),
                Text(
                  DiscoveryText.worksVideoBookLoadingSubtitle,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: AppColors.white.withValues(alpha: 0.72),
                    fontSize: AppTypography.iosSubheadline,
                  ),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildTypedCanvas(
    ContentPostViewData post, {
    required bool enableArticlePageCurl,
    required bool isVisible,
    required int videoViewportEpoch,
  }) {
    if (_isImageLikePost(post)) {
      return ImageBookCanvas(
        imageUrls: _imageUrlsForPost(post),
        initialIndex: _photoInnerIndex[post.id] ?? _defaultImageIndexFor(post),
        gestureIntentController: _gestureIntentController,
        onImageChanged: (index) => _setMountedState(() {
          _rememberPostLocalState(post.id);
          _photoInnerIndex[post.id] = index;
        }),
        onPageflipMotion: (event) => _trackImagePageflipMotion(post, event),
        onMediaLoad: (event) {
          ref
              .read(pageLifecycleObservabilityProvider)
              .recordMediaLoad(
                mediaType: 'image',
                result: event.result,
                pageName: 'works_image_book',
                copyKey: event.result == 'failure' ? 'imageLoadFailed' : null,
                error: event.error,
                durationMs: event.durationMs,
                candidatesTried: event.candidatesTried,
              );
        },
        onOverflowPrevious: null,
        onOverflowNext: null,
      );
    }
    if (_isVideoLikePost(post)) {
      final videoItems = _videoItemsFor(post);
      return _WorksVideoCanvas(
        key: ValueKey<String>(
          'works-video-canvas-${post.id}-$videoViewportEpoch',
        ),
        post: post,
        items: videoItems,
        initialEpisodeIndex: _videoIndexFor(post.id, videoItems),
        isVisible: isVisible,
        onEpisodeChanged: (idx, episodeIdentity) => _handleVideoEpisodeChanged(
          postId: post.id,
          episodeIndex: idx,
          episodeIdentity: episodeIdentity,
          viewportEpoch: videoViewportEpoch,
        ),
        onActiveSessionChanged: (episodeIndex, episodeIdentity, session) {
          if (!isVisible) {
            return;
          }
          _handleActiveVideoSession(
            postId: post.id,
            episodeIndex: episodeIndex,
            episodeIdentity: episodeIdentity,
            session: session,
            viewportEpoch: videoViewportEpoch,
          );
        },
      );
    }
    if (_isArticleLikePost(post)) {
      final article = _articleViewFor(post);
      if (_shouldShowArticleHydrationError(post, article)) {
        return AppPageErrorState(
          key: ValueKey<String>('article-hydration-error-${post.id}'),
          semantic: _articleHydrationErrorSemantic(post),
          onRecovery: (action) async {
            if (action.type == UiErrorActionType.retry ||
                action.type == UiErrorActionType.resubmit) {
              await _maybeHydrateArticleDetail(post, force: true);
              final refreshed = _articleViewFor(post);
              return _shouldShowArticleHydrationError(post, refreshed)
                  ? UiRecoveryOutcome.stillBlocked
                  : UiRecoveryOutcome.recovered;
            }
            return UiRecoveryOutcome.cancelled;
          },
        );
      }
      final safeInitialPage = (_articleInnerIndex[post.id] ?? 0)
          .clamp(0, _articlePageCount(post) - 1)
          .toInt();
      return _WorksArticleCanvas(
        post: post,
        article: article,
        timeLine: ContentTimeLabel.readerLine(
          createdAt: post.createdAt,
          updatedAt: post.updatedAt,
        ),
        paperTexture: _resolveArticlePaperTexture(post),
        enablePageCurl: enableArticlePageCurl,
        initialPage: safeInitialPage,
        topChromeSafeInset: widget.topChromeSafeInset,
        reserveContentIntersection: _primaryIntersectionReasonFor(post) != null,
        onPageChanged: (index) => _handleArticleInnerPageChanged(post, index),
        onResolvedPageCountChanged: (pageCount) =>
            _handleResolvedArticlePageCount(post.id, pageCount),
        onFallbackResolved: (reason) =>
            _trackArticleReaderFallback(post, reason, bookReaderEnabled: true),
        onPageFlipCommitted: (event) =>
            _trackArticlePageFlipCommit(post, event),
        onPageCurlAborted: (event) => _trackArticlePageCurlAbort(post, event),
        onEntityTap: (span) => _handleArticleInlineMentionTap(post, span),
        gestureIntentController: _gestureIntentController,
        onOverflowPrevious: null,
        onOverflowNext: null,
      );
    }
    if (_isTextOnlyMomentPost(post)) {
      return TabSwipeSwitchRegion(
        enabled: _canSwipePrimaryTabs,
        onSwipe: _handlePrimaryTabSwipe,
        child: _WorksTextCanvas(
          layoutSpec: _layoutSpecForPost(post),
          title: _titleForPost(post),
          body: _bodyForPost(post),
          reserveContentIntersection:
              _primaryIntersectionReasonFor(post) != null,
          imageUrl: _rawPostById(
            post.id,
          )?[ContentMediaPostProjectionKeys.coverUrl]?.toString(),
        ),
      );
    }
    return Container(color: AppColors.worksBackground);
  }

  /// 页码 chevron 切页（`‹ n / m ›`）：更新 inner index 后由
  /// `_WorksArticleCanvas.initialPage` 驱动 deck `didUpdateWidget` 跳页，
  /// 不引入第二套翻页控制通路。
  void _stepArticlePage(ContentPostViewData post, int delta) {
    final total = _articlePageCount(post);
    final current = (_articleInnerIndex[post.id] ?? 0).clamp(0, total - 1);
    final next = (current + delta).clamp(0, total - 1).toInt();
    if (next == current) return;
    _setMountedState(() {
      _rememberPostLocalState(post.id);
      _articleInnerIndex[post.id] = next;
    });
  }

  void _handleArticleInnerPageChanged(ContentPostViewData post, int index) {
    final previousIndex = _articleInnerIndex[post.id] ?? 0;
    if (previousIndex != index) {
      _trackArticlePageFlipCommit(
        post,
        WorksArticlePageFlipEvent(
          fromPage: previousIndex,
          toPage: index,
          durationMs: 0,
          mechanism: 'page_curl',
        ),
      );
    }
    _setMountedState(() {
      _rememberPostLocalState(post.id);
      _articleInnerIndex[post.id] = index;
    });
  }
}
