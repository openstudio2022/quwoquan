part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerBuild on _WorksImmersiveViewerState {
  Widget _buildViewer(BuildContext context) {
    if (ref.watch(authSessionControllerProvider).isAuthenticated) {
      _scheduleAuthContinuationResume();
    }
    ref.watch(postInteractionStateProvider);
    ref.watch(userRelationshipStateProvider);
    ref.watch(activePersonaContextProvider);
    final enableArticlePageCurl = ref.watch(articlePageCurlFeatureFlagProvider);
    final internalFeed = _usesExternalFeed
        ? null
        : _buildInternalFeedAggregate();
    final posts = internalFeed?.posts ?? _buildFeed();
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
    if (widget.isActive && _awaitingPrefetchedReveal && currentPost != null) {
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
    if (commentSplitPost != null && !_pureMediaLandscape) {
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
            content: _buildCommentSplitContent(
              commentSplitPost,
              enableArticlePageCurl: enableArticlePageCurl,
            ),
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
                _invalidateVideoViewport();
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
    final landscapeAspectRatio = currentPost == null
        ? 0.0
        : _landscapeAspectRatioForPost(currentPost);
    final landscapeGeometry = _pureMediaLandscape
        ? ImmersiveLandscapeGeometry(
            size: MediaQuery.sizeOf(context),
            safeInsets: MediaQuery.viewPaddingOf(context),
            aspectRatio: landscapeAspectRatio,
          )
        : null;
    // - 图片多图：点指示器（● ● ○ ● ●，最多 6 点）
    // - 视频：由统一 bottom chrome 装配视频集进度、caption 与时间轴
    Widget? captionHeader;
    Widget? videoBottomChrome;
    if (currentPost != null) {
      if (_isImageLikePost(currentPost) && progress.total > 1) {
        captionHeader = _WorksPageIndicator(
          total: progress.total,
          current: progress.current,
        );
      } else if (_isVideoLikePost(currentPost)) {
        // 视频的媒体与 chrome 在分集内同一次布局完成，不再覆盖第二层。
        videoBottomChrome = const SizedBox.shrink();
      }
    }
    // BACK 在查看器内只关闭一层；物理页面方向不参与导航状态。
    return PopScope(
      canPop:
          !_pureMediaLandscape &&
          !_landscapeTransitionInFlight &&
          widget.onTapBack == null &&
          widget.onDismissed == null,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) {
          if (_commentSplitPostId != null) {
            _closeLandscapeComment();
          } else if (_pureMediaLandscape || _landscapeTransitionInFlight) {
            unawaited(_exitPureMediaLandscape());
          } else {
            _dismissViewer();
          }
        }
      },
      child: DefaultTextStyle.merge(
        style: const TextStyle(
          decoration: TextDecoration.none,
          decorationThickness: 0,
        ),
        child: AnnotatedRegion<SystemUiOverlayStyle>(
          value: topChromeTheme.overlayStyle,
          child: GestureDetector(
            behavior: HitTestBehavior.deferToChild,
            onTap: _pureMediaLandscape ? _handleLandscapeCanvasTap : null,
            onLongPress: _pureMediaLandscape ? () {} : null,
            child: Listener(
              onPointerDown: _landscapePointerDown,
              onPointerUp: _landscapePointerEnd,
              onPointerCancel: _landscapePointerEnd,
              child: Stack(
                fit: StackFit.expand,
                children: [
                  const Positioned.fill(
                    child: ColoredBox(color: AppColors.black),
                  ),
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
                        physics: _pureMediaLandscape
                            ? const NeverScrollableScrollPhysics()
                            : WorksImmersiveVerticalPagePhysics(
                                currentPage: () => _currentPage,
                                holdVerticalScroll: () =>
                                    _gestureIntentController
                                        .shouldHoldVerticalScroll,
                              ),
                        itemCount: posts.isEmpty
                            ? 1
                            : posts.length + (showLoadMoreSentinel ? 1 : 0),
                        onPageChanged: (index) {
                          if (_currentPage != index) {
                            // Flush dwell time for the previous post
                            if (posts.isNotEmpty &&
                                _currentPage < posts.length) {
                              final prevPost =
                                  posts[_currentPage.clamp(
                                    0,
                                    posts.length - 1,
                                  )];
                              _flushDwell(prevPost, trackSkip: true);
                            }

                            final nextIsSentinel =
                                showLoadMoreSentinel && index >= posts.length;
                            _setMountedState(() {
                              _currentPage = index;
                              _awaitingPrefetchedReveal = nextIsSentinel;
                              _invalidateVideoViewport();
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
                            final newPost =
                                posts[index.clamp(0, posts.length - 1)];
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
                                  group:
                                      AppUserRecoveryGroup.contentUnavailable,
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
                            if (internalFeed != null) {
                              return _buildInternalFeedTerminal(
                                context,
                                internalFeed,
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
                              top: _pureMediaLandscape
                                  ? AppSpacing.zero
                                  : _statusBarContentInsetFor(post),
                            ),
                            child: KeyedSubtree(
                              key: ValueKey<String>(
                                'works-status-content-canvas-${post.id}',
                              ),
                              child: _buildPostCanvas(
                                post,
                                viewportContext: context,
                                enableArticlePageCurl: enableArticlePageCurl,
                                isVisible:
                                    widget.isActive && index == _currentPage,
                                videoViewportEpoch: _videoViewportEpoch,
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                  ),

                  if (_pureMediaLandscape) ..._landscapeShadeLayers(context),
                  if (!_pureMediaLandscape) ...<Widget>[
                    _buildEdgeDismissHotzone(TabSwipeDirection.previous),
                    _buildEdgeDismissHotzone(TabSwipeDirection.next),
                  ],

                  if (!_pureMediaLandscape &&
                      currentPost != null &&
                      _isArticleLikePost(currentPost) &&
                      widget.topChromeSafeInset > AppSpacing.zero)
                    Positioned(
                      key: const ValueKey<String>(
                        'works-article-status-bar-scrim',
                      ),
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
                    child: _landscapeChrome(
                      Padding(
                        padding: EdgeInsets.only(
                          top: _pureMediaLandscape
                              ? MediaQuery.viewPaddingOf(context).top
                              : widget.topChromeSafeInset,
                        ),
                        child: _WorksPrimaryTopBar(
                          layoutSpec: currentLayoutSpec,
                          title: _pureMediaLandscape && currentPost != null
                              ? _titleForPost(currentPost)
                              : '',
                          landscape: _pureMediaLandscape,
                          landscapeGeometry: landscapeGeometry,
                          foregroundColor: topChromeTheme.foregroundColor,
                          onTapClose: _pureMediaLandscape
                              ? _exitPureMediaLandscape
                              : _dismissViewer,
                          onTapMore: () => _withLandscapeModal(
                            () => _showWorksMoreSheet(context),
                          ),
                          onHorizontalDragEnd: _pureMediaLandscape
                              ? (_) {}
                              : _handlePrimaryTabSwipeDragEnd,
                        ),
                      ),
                    ),
                  ),

                  if (!_pureMediaLandscape &&
                      currentPost != null &&
                      videoBottomChrome == null &&
                      !_isImageLikePost(currentPost) &&
                      _showsCaptionOverlay(currentPost))
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom:
                          WorksImmersiveContentLayout.overlayBottomClearance(
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

                  if (!_pureMediaLandscape &&
                      currentPost != null &&
                      videoBottomChrome != null)
                    Positioned.fill(child: videoBottomChrome),

                  // 文章页码：正文下方、作者工具栏上方（`‹ 1 / 6 ›`，chevron 可点切页）。
                  if (!_pureMediaLandscape &&
                      currentPost != null &&
                      _isArticleLikePost(currentPost))
                    Positioned(
                      left: 0,
                      right: 0,
                      bottom:
                          WorksImmersiveContentLayout.overlayBottomClearance(
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
                                fontFeatures: const [
                                  FontFeature.tabularFigures(),
                                ],
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

                  // 经历溯源轻标（L0）：与交集陈述互斥占位（同屏最多一处交集类模块）。
                  if (!_pureMediaLandscape &&
                      currentPost != null &&
                      intersectionReason == null &&
                      videoBottomChrome == null &&
                      widget.showWorksToolbar)
                    _buildProvenanceBadgeLayer(
                      context,
                      currentPost,
                      currentEngagementLayoutSpec,
                    ),

                  if (!_pureMediaLandscape &&
                      currentPost != null &&
                      intersectionReason != null &&
                      videoBottomChrome == null &&
                      !_isImageLikePost(currentPost))
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
                        child: SizedBox(
                          key: const ValueKey<String>(
                            'works-caption-intersection-reason',
                          ),
                          width: double.infinity,
                          child:
                              HomeFeedCrossObjectComposition.immersiveIntersectionStatement(
                                reason: intersectionReason,
                                contextObjectName:
                                    currentPost.normalizedTitle
                                        .trim()
                                        .isNotEmpty
                                    ? currentPost.normalizedTitle.trim()
                                    : currentPost.normalizedBody.trim(),
                                contextObjectTarget:
                                    _postIntersectionContextTarget(currentPost),
                                onSpanTap: (_) => _showIntersectionDetail(
                                  context,
                                  currentPost,
                                ),
                                onFallbackTap: () => _showIntersectionDetail(
                                  context,
                                  currentPost,
                                ),
                              ),
                        ),
                      ),
                    ),

                  if (currentPost != null && widget.showWorksToolbar)
                    Positioned(
                      left: _pureMediaLandscape
                          ? landscapeGeometry?.visibleMediaRect.left ?? 0
                          : 0,
                      right: _pureMediaLandscape
                          ? MediaQuery.sizeOf(context).width -
                                (landscapeGeometry?.visibleMediaRect.right ??
                                    MediaQuery.sizeOf(context).width)
                          : 0,
                      bottom: 0,
                      child: _landscapeChrome(
                        Builder(
                          builder: (context) {
                            final wishlistAnchor = _wishlistAnchorForPost(
                              currentPost,
                            );
                            if (wishlistAnchor != null) {
                              _ensureWishlistStateLoaded(
                                wishlistAnchor.homepageId,
                              );
                            }
                            return ImmersiveEngagementBar(
                              layoutSpec: currentEngagementLayoutSpec,
                              avatarUrl: currentPost.avatarUrl,
                              avatarBinding: contentPostAuthorAvatarBinding(
                                currentPost,
                              ),
                              displayName: currentPost.displayName,
                              isSelfPost:
                                  currentPost.personaId ==
                                  ref
                                      .read(authSessionControllerProvider)
                                      .activePersonaId,
                              authorBadge:
                                  _workItemFor(currentPost).authorBadge ?? '',
                              showWishlistButton: wishlistAnchor != null,
                              isWishlisted:
                                  wishlistAnchor != null &&
                                  (_wishlistStateByHomepageId[wishlistAnchor
                                          .homepageId] ??
                                      false),
                              onWishlistTap: wishlistAnchor == null
                                  ? null
                                  : () => _toggleWishlistForPost(currentPost),
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
                                      intersectionHighlightIntentProvider
                                          .notifier,
                                    )
                                    .primeFromReasons(
                                      currentPost.personaId,
                                      currentPost.intersectionReasons,
                                    );
                                widget.onUserTap(
                                  currentPost.personaId,
                                  avatarUrl: currentPost.avatarUrl,
                                  avatarAssetId:
                                      currentPost.authorAvatarAssetId,
                                  avatarAccessMode:
                                      currentPost.authorAvatarAccessMode,
                                  displayName: currentPost.displayName,
                                  backgroundUrl:
                                      currentPost.authorBackgroundUrl,
                                );
                              },
                              onFollowTap: () => _onFollow(currentPost),
                              onLikeTap: () => _onLike(currentPost),
                              onCommentTap: () =>
                                  _openCommentFor(currentPost.id),
                              onShareTap: () => _sharePost(
                                context,
                                currentPost,
                                enableIdentityTemplate: ref.read(
                                  contentFeatureFlagProvider(
                                    'enable_identity_share_template',
                                  ),
                                ),
                              ),
                              onRevealSystemNav: null,
                              transparentBackground: true,
                              horizontalInsetOverride: _pureMediaLandscape
                                  ? AppSpacing.zero
                                  : null,
                            );
                          },
                        ),
                      ),
                    ),

                  if (_pureMediaLandscape) ...[
                    if (!_landscapeControlsVisible)
                      Positioned.fill(
                        child: Semantics(
                          button: true,
                          label: AppLocalizations.of(context)
                              .media_showControls,
                          onTap: _revealLandscapeChrome,
                          onDismiss: _exitPureMediaLandscape,
                          child: GestureDetector(
                            key: const ValueKey('works-landscape-reveal'),
                            behavior: HitTestBehavior.opaque,
                            onTap: _handleLandscapeCanvasTap,
                            onLongPress: () {},
                          ),
                        ),
                      ),
                    Positioned(
                      bottom:
                          MediaQuery.viewPaddingOf(context).bottom +
                          AppSpacing.immersiveBottomChromeLift,
                      left: landscapeGeometry?.rightControlSlot.left,
                      child: _landscapeChrome(
                        Semantics(
                          label: AppLocalizations.of(context)
                              .media_exitFullscreen,
                          child: ImmersiveToolbarIconButton(
                            key: const ValueKey(
                              'works-media-landscape-collapse',
                            ),
                            icon: CupertinoIcons.arrow_down_right_arrow_up_left,
                            onPressed: _exitPureMediaLandscape,
                          ),
                        ),
                      ),
                    ),
                    if (commentSplitPost != null)
                      _buildLandscapeCommentPanel(context, commentSplitPost),
                  ],
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildPostCanvas(
    ContentPostViewData post, {
    BuildContext? viewportContext,
    required bool enableArticlePageCurl,
    required bool isVisible,
    required int videoViewportEpoch,
  }) {
    return _buildTypedCanvas(
      viewportContext ?? context,
      post,
      enableArticlePageCurl: enableArticlePageCurl,
      isVisible: isVisible,
      videoViewportEpoch: videoViewportEpoch,
    );
  }

  Widget _buildTypedCanvas(
    BuildContext context,
    ContentPostViewData post, {
    required bool enableArticlePageCurl,
    required bool isVisible,
    required int videoViewportEpoch,
  }) {
    if (_isImageLikePost(post)) {
      return _buildImageStage(context, post);
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
        landscape: _pureMediaLandscape,
        onMediaTap: _handleLandscapeCanvasTap,
        composeStage: (item, session, media, isActive) => _WorksVideoBottomChrome(
          isActive: isActive,
          association: widget.videoAssociationBuilder?.call(context, post),
          key: ValueKey(
            'works-video-chrome-${post.id}-${item.identity}-$videoViewportEpoch',
          ),
          layoutSpec: _layoutSpecForPost(post),
          media: media,
          aspectRatio: item.aspectRatio,
          topInset:
              widget.topChromeSafeInset +
              AppSpacing.appChromeTopBarHeight(context),
          toolbarHeight: widget.showWorksToolbar
              ? ImmersiveEngagementBar.reservedHeight(context)
              : 0,
          intersection: _primaryIntersectionReasonFor(post) != null
              ? HomeFeedCrossObjectComposition.immersiveIntersectionStatement(
                  key: const ValueKey('works-caption-intersection-reason'),
                  reason: _primaryIntersectionReasonFor(post)!,
                  contextObjectName: post.normalizedTitle.trim().isNotEmpty
                      ? post.normalizedTitle.trim()
                      : post.normalizedBody.trim(),
                  contextObjectTarget: _postIntersectionContextTarget(post),
                  onSpanTap: (_) => _showIntersectionDetail(context, post),
                  onFallbackTap: () => _showIntersectionDetail(context, post),
                )
              : null,
          title: _overlayTitleForPost(post),
          caption: _overlayBodyForPost(post),
          sourceAttribution: post.sourceAttribution,
          isExpanded: _isCaptionExpanded(post.id),
          onToggleCaption: () => _toggleCaptionExpanded(post.id),
          session: session,
          sharedTimelineEnabled: ref.watch(
            contentFeatureFlagProvider('enable_shared_video_timeline'),
          ),
          previewTrackDescriptor:
              ref.watch(
                contentFeatureFlagProvider('enable_video_timeline_preview'),
              )
              ? item.previewTrackDescriptor
              : null,
          previewTrackQuery: ref.watch(videoPreviewTrackQueryProvider),
          episodeCurrent: videoItems.indexOf(item) + 1,
          episodeTotal: videoItems.length,
          onEnterLandscape:
              !_pureMediaLandscape &&
                  MediaQuery.sizeOf(context).height >
                      MediaQuery.sizeOf(context).width
              ? _enterPureMediaLandscape
              : null,
          pureMediaMode: _pureMediaLandscape,
          controlsVisible: _landscapeControlsVisible,
        ),
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
              final result = await _maybeHydrateArticleDetail(
                post,
                force: true,
              );
              return switch (result.terminal) {
                WorksViewerArticleHydrationTerminal.recovered =>
                  UiRecoveryOutcome.recovered,
                WorksViewerArticleHydrationTerminal.stillBlocked =>
                  UiRecoveryOutcome.stillBlocked,
                WorksViewerArticleHydrationTerminal.superseded =>
                  UiRecoveryOutcome.superseded,
              };
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
        onImageTap: (asset) {
          unawaited(
            presentWorksArticleImageViewer(
              context: context,
              document: article.document,
              initialAsset: asset,
              onOpened: (assetId) => _articleReaderObservability
                  .trackImageViewerOpen(postId: post.id, assetId: assetId),
              onClosed: (assetId) => _articleReaderObservability
                  .trackImageViewerClose(postId: post.id, assetId: assetId),
              onMediaLoad: (event) {
                ref
                    .read(pageLifecycleObservabilityProvider)
                    .recordMediaLoad(
                      mediaType: 'image',
                      result: event.result,
                      pageName: PageNames.workBrowser,
                      surfaceId: AppUiSurfaces.workBrowser.id,
                      objectType: 'contentPost',
                      objectId: post.id,
                      copyKey: event.result == 'failure'
                          ? 'imageLoadFailed'
                          : null,
                      error: event.error,
                      durationMs: event.durationMs,
                      candidatesTried: event.candidatesTried,
                    );
              },
            ),
          );
        },
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
          backgroundBinding: _textMomentBackgroundBinding(post),
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
