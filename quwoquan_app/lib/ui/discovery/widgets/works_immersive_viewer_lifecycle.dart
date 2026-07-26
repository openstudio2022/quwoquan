part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerLifecycle on _WorksImmersiveViewerState {
  void _invalidateVideoViewport({required bool resetDurationWindow}) {
    _videoViewportEpoch += 1;
    _videoEpisodeCallbackGeneration += 1;
    _activeVideoSessionCallbackGeneration += 1;
    _activeVideoBinding = null;
    if (!resetDurationWindow) {
      return;
    }
    _videoDurationWindowTimer?.cancel();
    _videoDurationWindowTimer = null;
    _videoDurationStageKey = null;
    _videoDurationWindowActive = false;
    _videoDurationWindowRevision += 1;
  }

  bool get _usesExternalFeed => widget.externalPosts != null;

  void _configureExternalEmptyDeadline() {
    final waitingForExternalContent =
        widget.externalPosts != null && widget.externalPosts!.isEmpty;
    if (!waitingForExternalContent) {
      _externalEmptyTimer?.cancel();
      _externalEmptyTimer = null;
      _externalEmptyTimedOut = false;
      return;
    }
    if (_externalEmptyTimer != null || _externalEmptyTimedOut) {
      return;
    }
    _externalEmptyTimer = Timer(
      _WorksImmersiveViewerState._externalEmptyExitDelay,
      () {
        _externalEmptyTimer = null;
        if (!mounted ||
            widget.externalPosts == null ||
            widget.externalPosts!.isNotEmpty) {
          return;
        }
        _setMountedState(() => _externalEmptyTimedOut = true);
      },
    );
  }

  void _handleGestureIntentChanged() {
    // 边界只保留轻量回弹，不弹出沉浸打断提示。
  }

  void _handleImmersivePointerDown(PointerDownEvent event) {
    final capabilities = _gestureCapabilitiesForCurrentPost();
    if (capabilities == null) {
      return;
    }
    _gestureIntentController.begin(
      position: event.position,
      capabilities: capabilities,
    );
  }

  void _handleImmersivePointerMove(PointerMoveEvent event) {
    final capabilities = _gestureCapabilitiesForCurrentPost();
    if (capabilities == null) {
      return;
    }
    if (!_gestureIntentController.isTracking) {
      _gestureIntentController.begin(
        position: event.position,
        capabilities: capabilities,
      );
      return;
    }
    _gestureIntentController.update(
      position: event.position,
      capabilities: capabilities,
    );
  }

  void _handleImmersivePointerEnd() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted || !_gestureIntentController.isTracking) {
        return;
      }
      _gestureIntentController.finish();
    });
  }

  ImmersiveGestureCapabilities? _gestureCapabilitiesForCurrentPost() {
    final posts = _buildFeed();
    if (posts.isEmpty) {
      return null;
    }
    final post = posts[_currentPage.clamp(0, posts.length - 1).toInt()];
    final allowVerticalSwitch = posts.length > 1;
    if (_isImageLikePost(post)) {
      final images = _imageUrlsForPost(post);
      final current = (_photoInnerIndex[post.id] ?? _defaultImageIndexFor(post))
          .clamp(0, max(0, images.length - 1))
          .toInt();
      return ImmersiveGestureCapabilities(
        pageCount: images.length,
        currentPageIndex: current,
        canFlipForward: current < images.length - 1,
        canFlipBack: current > 0,
        allowVerticalSwitch: allowVerticalSwitch,
        allowBoundaryRubberBand: true,
      );
    }
    if (_isArticleLikePost(post)) {
      final total = _articlePageCount(post);
      final current = (_articleInnerIndex[post.id] ?? 0)
          .clamp(0, total - 1)
          .toInt();
      return ImmersiveGestureCapabilities(
        pageCount: total,
        currentPageIndex: current,
        canFlipForward: current < total - 1,
        canFlipBack: current > 0,
        allowVerticalSwitch: allowVerticalSwitch,
        allowBoundaryRubberBand: true,
      );
    }
    return ImmersiveGestureCapabilities(
      pageCount: 1,
      currentPageIndex: 0,
      canFlipForward: false,
      canFlipBack: false,
      allowVerticalSwitch: allowVerticalSwitch,
      allowBoundaryRubberBand: false,
      startedInPageFlipHotzone: false,
    );
  }

  bool get _enableArticlePageCurl {
    final runtimeConfig = ref.read(contentRuntimeConfigProvider);
    return runtimeConfig.featureFlags.containsKey('enable_article_page_curl')
        ? runtimeConfig.isEnabled('enable_article_page_curl')
        : true;
  }

  /// 精品流语义源（B3 读路径闭环）：与埋点 channelId 归一
  /// （[WorksImmersiveViewerObservability.immersiveChannelId]）同口径。
  /// 命中时数据源为 premium 频道单路（服务端 premium_stream fail-closed 池），
  /// 池空即空态，禁止回退三路浏览流——保证归因 channelId 与真实数据源一致。
  bool get _isPremiumStreamSource {
    if (_usesExternalFeed) {
      return false;
    }
    return WorksImmersiveViewerObservability.immersiveChannelId(
          widget.source,
        ) ==
        'premium_stream';
  }

  List<String> get _trackedFeedTabIds {
    if (_usesExternalFeed) {
      return const <String>[];
    }
    if (_isPremiumStreamSource) {
      return const <String>['premium'];
    }
    final contentTypes = _effectiveFilterContentTypes;
    if (contentTypes.isEmpty) {
      return const <String>['photo', 'video', 'article'];
    }
    final tracked = <String>[];
    if (contentTypes.contains('image')) tracked.add('photo');
    if (contentTypes.contains('video')) tracked.add('video');
    if (contentTypes.contains('article')) tracked.add('article');
    return tracked;
  }

  DiscoveryFeedState? _readFeedState(String tabId) {
    return ref.read(discoveryFeedProvider(tabId)).value;
  }

  bool _trackedFeedsHaveMore() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.hasMore ?? false,
    );
  }

  bool _trackedFeedsLoading() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.isLoading ?? false,
    );
  }

  Object? _trackedFeedsError() {
    for (final tabId in _trackedFeedTabIds) {
      final error = _readFeedState(tabId)?.appendError;
      if (error != null) {
        return error;
      }
    }
    return null;
  }

  void _requestPrefetchNow({
    required int visibleIndex,
    required int postsLength,
    bool force = false,
  }) {
    if (_usesExternalFeed) {
      return;
    }
    final thresholdIndex = max(
      0,
      postsLength - 1 - _WorksImmersiveViewerState._tailPrefetchThreshold,
    );
    if (!force && visibleIndex < thresholdIndex) {
      return;
    }
    for (final tabId in _trackedFeedTabIds) {
      final feedState = _readFeedState(tabId);
      if (feedState == null || !feedState.hasMore || feedState.isLoading) {
        continue;
      }
      unawaited(
        ref.read(discoveryFeedMapProvider.notifier).appendNextPage(tabId),
      );
    }
  }

  void _schedulePrefetch({
    required int visibleIndex,
    required int postsLength,
    bool force = false,
  }) {
    if (_usesExternalFeed || _prefetchScheduled) {
      return;
    }
    _prefetchScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _prefetchScheduled = false;
      if (!mounted) {
        return;
      }
      _requestPrefetchNow(
        visibleIndex: visibleIndex,
        postsLength: postsLength,
        force: force,
      );
    });
  }

  int get _safeInitialPage {
    if (_usesExternalFeed) {
      if (widget.externalPosts!.isEmpty) {
        return 0;
      }
      return widget.initialPostIndex.clamp(0, widget.externalPosts!.length - 1);
    }
    return 0;
  }

  void _scheduleAuthContinuationResume({int remainingFrames = 30}) {
    if (_authContinuationResumeScheduled) {
      return;
    }
    _authContinuationResumeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _authContinuationResumeScheduled = false;
      if (!mounted ||
          !ref.read(authSessionControllerProvider).isAuthenticated) {
        return;
      }
      if (!(ModalRoute.of(context)?.isCurrent ?? true)) {
        if (remainingFrames > 0) {
          _scheduleAuthContinuationResume(remainingFrames: remainingFrames - 1);
        }
        return;
      }
      final controller = ref.read(authContinuationProvider.notifier);
      final report = controller.take<SubmitContentReportContinuation>();
      if (report != null) {
        if (report.surface != ContentReportContinuationSurface.workBrowser) {
          controller.set(report);
          return;
        }
        final post = _postById(_buildFeed(), report.postId);
        if (post != null) {
          unawaited(_submitPostReport(post, report.reason));
        } else {
          controller.set(report);
        }
        return;
      }
      final moderation = controller.take<ContentModerationContinuation>();
      if (moderation != null) {
        if (moderation.surface !=
            ContentModerationContinuationSurface.workBrowser) {
          controller.set(moderation);
          return;
        }
        final post = _postById(_buildFeed(), moderation.postId);
        if (post == null) {
          controller.set(moderation);
          return;
        }
        switch (moderation.action) {
          case ContentModerationContinuationAction.blockAuthor:
            unawaited(_applyBlockAuthor(post));
          case ContentModerationContinuationAction.blockKeyword:
            final keyword = moderation.keyword?.trim() ?? '';
            if (keyword.isNotEmpty) {
              unawaited(_applyBlockKeyword(post, keyword));
            }
        }
        return;
      }
      final original = controller
          .take<RequestOriginalImageAccessContinuation>();
      if (original == null) {
        return;
      }
      final post = _postById(_buildFeed(), original.postId);
      if (post != null) {
        unawaited(
          _loadOriginalImage(
            post: post,
            mediaId: original.mediaId,
            imageIndex: original.imageIndex,
          ),
        );
      } else {
        controller.set(original);
      }
    });
  }

  /// 视频画布上报当前可见帖子的分集索引。
  void _handleVideoEpisodeChanged({
    required String postId,
    required int episodeIndex,
    required String episodeIdentity,
    required int viewportEpoch,
  }) {
    if (!mounted || viewportEpoch != _videoViewportEpoch) {
      return;
    }
    final callbackGeneration = ++_videoEpisodeCallbackGeneration;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          callbackGeneration != _videoEpisodeCallbackGeneration ||
          viewportEpoch != _videoViewportEpoch) {
        return;
      }
      final stageKey = '$postId|$episodeIdentity';
      final episodeChanged =
          _videoInnerIndex[postId] != episodeIndex ||
          _videoInnerIdentity[postId] != episodeIdentity;
      final durationStageChanged = _videoDurationStageKey != stageKey;
      if (!episodeChanged && !durationStageChanged) {
        return;
      }
      if (durationStageChanged) {
        _videoDurationWindowTimer?.cancel();
      }
      _setMountedState(() {
        _videoInnerIndex[postId] = episodeIndex;
        _videoInnerIdentity[postId] = episodeIdentity;
        if (durationStageChanged) {
          _videoDurationStageKey = stageKey;
          _videoDurationWindowActive = true;
          _videoDurationWindowRevision += 1;
        }
      });
      if (durationStageChanged) {
        final revision = _videoDurationWindowRevision;
        _videoDurationWindowTimer = Timer(const Duration(seconds: 5), () {
          if (!mounted || revision != _videoDurationWindowRevision) {
            return;
          }
          _setMountedState(() => _videoDurationWindowActive = false);
        });
      }
    });
  }

  /// 视频画布上报当前可见帖子的播放会话。
  void _handleActiveVideoSession({
    required String postId,
    required int episodeIndex,
    required String episodeIdentity,
    required VideoPlaybackSession? session,
    required int viewportEpoch,
  }) {
    if (!mounted || viewportEpoch != _videoViewportEpoch) {
      return;
    }
    final callbackGeneration = ++_activeVideoSessionCallbackGeneration;
    final current = _activeVideoBinding;
    if (current?.postId == postId &&
        current?.episodeIdentity == episodeIdentity &&
        current?.episodeIndex == episodeIndex &&
        current?.viewportEpoch == viewportEpoch &&
        identical(current?.session, session)) {
      return;
    }
    // Video canvas callbacks can originate from didUpdateWidget while this
    // parent is rebuilding. State changes must therefore be deferred to the
    // next frame; the generation keeps an earlier callback from winning over a
    // newer viewport/session update.
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          callbackGeneration != _activeVideoSessionCallbackGeneration ||
          viewportEpoch != _videoViewportEpoch) {
        return;
      }
      _setMountedState(
        () => _activeVideoBinding = session == null
            ? null
            : (
                postId: postId,
                episodeIdentity: episodeIdentity,
                episodeIndex: episodeIndex,
                viewportEpoch: viewportEpoch,
                session: session,
              ),
      );
    });
    _feedPerformanceObservability.recordActiveVideoControllerCount(
      surfaceId: 'works_immersive_viewer',
      activeCount: session == null ? 0 : 1,
    );
  }

  // ── 行为追踪辅助 ──────────────────────────────────────────────

  String _immersiveChannelId() =>
      WorksImmersiveViewerObservability.immersiveChannelId(widget.source);

  String? _effectiveFeedRequestId() {
    final explicit = widget.feedRequestId?.trim() ?? '';
    if (explicit.isNotEmpty) {
      return explicit;
    }
    return ref.read(feedSessionProvider.notifier).currentFeedRequestId;
  }

  int _attributedPosition(int viewerIndex) {
    final initialFeedPosition = widget.initialFeedPosition;
    if (!_usesExternalFeed || initialFeedPosition == null) {
      return viewerIndex;
    }
    return max(0, initialFeedPosition + viewerIndex - _safeInitialPage);
  }

  void _trackImpressionForPost(PostBaseDto post, {int? position}) {
    final feedSession = ref.read(feedSessionProvider.notifier);
    final viewerPosition = position ?? _currentPage;
    final attributedPosition = _attributedPosition(viewerPosition);
    final attribution = _WorksTrackingAttribution(
      referralSource: widget.referralSource,
      feedRequestId: _effectiveFeedRequestId(),
      position: attributedPosition,
      channelId: _immersiveChannelId(),
      rankingVersion: feedSession.currentRankingVersion,
      reasonVersion: feedSession.currentReasonVersion,
    );
    _activeTrackedPost = post;
    _activeTrackingAttribution = attribution;
    _pageEnterTime = DateTime.now();
    _contentBehaviorTracker.trackImpression(
      post.id,
      contentType: post.type,
      referralSource: attribution.referralSource,
      feedRequestId: attribution.feedRequestId,
      // 沉浸流逐条曝光携带页序位（B7）：与首页 feed 同口径的 position 归因。
      position: attribution.position,
      channelId: attribution.channelId,
      rankingVersion: attribution.rankingVersion,
      reasonVersion: attribution.reasonVersion,
      recallPath: post.recallPath,
      contentVertical: post.contentVertical,
      supplySource: post.supplySource,
    );

    _contentEngagementTracker.trackContentEnter(
      post.id,
      contentType: _mapPostContentType(post),
      referralSource: attribution.referralSource,
      totalImages: _imageUrlsForPost(post).length,
      totalDurationMs: post.durationMs,
      authorId: post.authorId,
      feedRequestId: attribution.feedRequestId,
      position: attribution.position,
    );

    if (!_isArticleLikePost(post)) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    final article = _articleViewFor(post);
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderOpen(
          postId: post.id,
          durationMs: DateTime.now().difference(_viewerOpenedAt).inMilliseconds,
          source: widget.source,
          template: article.template.name,
          fontPreset: article.fontPreset.name,
          pageCount: article.pages.length.clamp(1, 99),
          bookReaderEnabled: bookReaderEnabled,
        );
    if (!bookReaderEnabled) {
      ref
          .read(articleReaderObservabilityProvider)
          .trackReaderFallback(
            postId: post.id,
            reason: 'feature_flag_disabled',
            bookReaderEnabled: false,
          );
    }
    _trackDocumentStructureFallback(
      post: post,
      article: article,
      hydrated: _hydratedRawPostsById.containsKey(post.id),
    );
    unawaited(_maybeHydrateArticleDetail(post));
  }

  void _trackDocumentStructureFallback({
    required PostBaseDto post,
    required ContentArticleRender article,
    required bool hydrated,
  }) {
    if (article.documentSource == ArticleDetailDocumentSource.markdown) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderFallback(
          postId: post.id,
          reason:
              'document_structure:${WorksImmersiveViewerObservability.documentSourceName(article.documentSource)}:hydrated=$hydrated',
          bookReaderEnabled: bookReaderEnabled,
        );
  }

  Future<void> _maybeHydrateArticleDetail(
    PostBaseDto post, {
    bool force = false,
  }) async {
    final raw = _effectiveRawPostById(post.id);
    if (_hasStructuredArticlePayload(raw) ||
        _hydratingArticleIds.contains(post.id) ||
        (!force && _failedArticleHydrationIds.contains(post.id))) {
      return;
    }
    if (force) {
      _failedArticleHydrationIds.remove(post.id);
      _failedArticleHydrationErrorsById.remove(post.id);
    }
    _hydratingArticleIds.add(post.id);
    final startedAt = DateTime.now();
    try {
      final detail = await ref
          .read(workBrowserContentPostDetailReaderProvider)
          .getPost(postId: post.id);
      applyConfirmedInteractionPost(ref, detail.post);
      if (!mounted) {
        return;
      }
      _setMountedState(() {
        _hydratedRawPostsById[post.id] = <String, Object?>{
          ...?raw,
          ...Map<String, Object?>.from(detail.mergedArticleWireMap),
        };
        _failedArticleHydrationIds.remove(post.id);
        _failedArticleHydrationErrorsById.remove(post.id);
        _workItemCache.remove(post.id);
      });
      final hydratedArticle = _articleViewFor(post);
      _trackDocumentStructureFallback(
        post: post,
        article: hydratedArticle,
        hydrated: true,
      );
      ref
          .read(articleReaderObservabilityProvider)
          .trackHydration(
            postId: post.id,
            durationMs: DateTime.now().difference(startedAt).inMilliseconds,
            result: 'success',
            trigger: 'get_post',
            hadStructuredPayload: false,
          );
    } catch (error) {
      if (mounted) {
        _setMountedState(() {
          _failedArticleHydrationIds.add(post.id);
          _failedArticleHydrationErrorsById[post.id] = error;
        });
      } else {
        _failedArticleHydrationIds.add(post.id);
        _failedArticleHydrationErrorsById[post.id] = error;
      }
      ref
          .read(articleReaderObservabilityProvider)
          .trackHydration(
            postId: post.id,
            durationMs: DateTime.now().difference(startedAt).inMilliseconds,
            result: 'error',
            trigger: 'get_post',
            hadStructuredPayload: false,
          );
    } finally {
      _hydratingArticleIds.remove(post.id);
    }
  }

  bool _shouldShowArticleHydrationError(
    PostBaseDto post,
    ContentArticleRender article,
  ) {
    return article.documentSource == ArticleDetailDocumentSource.empty &&
        _failedArticleHydrationIds.contains(post.id);
  }

  UiErrorSemantic _articleHydrationErrorSemantic(PostBaseDto post) {
    return runtime_error_display.runtimeErrorSemantic(
      context,
      error:
          _failedArticleHydrationErrorsById[post.id] ??
          Exception('article hydration failed'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  String _fallbackReasonName(ArticleReaderFallbackReason reason) =>
      WorksImmersiveViewerObservability.fallbackReasonName(reason);

  void _trackArticleReaderFallback(
    PostBaseDto post,
    ArticleReaderFallbackReason reason, {
    required bool bookReaderEnabled,
  }) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackReaderFallback(
          postId: post.id,
          reason: _fallbackReasonName(reason),
          bookReaderEnabled: bookReaderEnabled,
        );
  }

  void _trackArticlePageFlipCommit(
    PostBaseDto post,
    ArticleReaderPageFlipCommit event,
  ) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackPageFlipCommit(
          postId: post.id,
          durationMs: event.durationMs,
          mechanism: event.mechanism,
          direction: event.direction,
          fromPage: event.fromPage,
          toPage: event.toPage,
        );
  }

  void _trackImagePageflipMotion(
    PostBaseDto post,
    MediaPageFlipMotionEvent event,
  ) {
    final feedSession = ref.read(feedSessionProvider.notifier);
    final explicitFeedRequestId = widget.feedRequestId?.trim() ?? '';
    ref
        .read(contentBehaviorTrackerProvider)
        .trackWorksImagePageflipMotion(
          post.id,
          direction: event.directionName,
          motionProfile: event.motionProfile,
          settleMs: event.settleDuration.inMilliseconds,
          reducedMotion: event.reducedMotion,
          committed: event.committed,
          contentType: post.type,
          referralSource: widget.referralSource,
          feedRequestId: explicitFeedRequestId.isNotEmpty
              ? explicitFeedRequestId
              : feedSession.currentFeedRequestId,
          position: _attributedPosition(_currentPage),
          channelId: _immersiveChannelId(),
          rankingVersion: feedSession.currentRankingVersion,
          reasonVersion: feedSession.currentReasonVersion,
          recallPath: post.recallPath,
          contentVertical: post.contentVertical,
          supplySource: post.supplySource,
        );
  }

  void _trackArticlePageCurlAbort(
    PostBaseDto post,
    ArticleReaderPageCurlAbort event,
  ) {
    ref
        .read(articleReaderObservabilityProvider)
        .trackPageCurlAbort(
          postId: post.id,
          corner: event.corner,
          progress: event.progress,
          direction: event.direction,
        );
  }

  void _flushDwell(PostBaseDto post, {bool trackSkip = false}) {
    final enterTime = _pageEnterTime;
    final attribution = _activeTrackingAttribution;
    if (enterTime == null ||
        attribution == null ||
        _activeTrackedPost?.id != post.id) {
      return;
    }
    final durationSec =
        DateTime.now().difference(enterTime).inMilliseconds / 1000.0;
    _contentBehaviorTracker.trackDwell(
      post.id,
      durationSeconds: durationSec,
      contentType: post.type,
      referralSource: attribution.referralSource,
      feedRequestId: attribution.feedRequestId,
      position: attribution.position,
      channelId: attribution.channelId,
      rankingVersion: attribution.rankingVersion,
      reasonVersion: attribution.reasonVersion,
      recallPath: post.recallPath,
      contentVertical: post.contentVertical,
      supplySource: post.supplySource,
    );
    if (trackSkip) {
      _contentBehaviorTracker.trackSkip(
        post.id,
        dwellSeconds: durationSec,
        contentType: post.type,
        referralSource: attribution.referralSource,
        feedRequestId: attribution.feedRequestId,
        position: attribution.position,
        channelId: attribution.channelId,
        rankingVersion: attribution.rankingVersion,
        reasonVersion: attribution.reasonVersion,
        recallPath: post.recallPath,
        contentVertical: post.contentVertical,
        supplySource: post.supplySource,
      );
    }
    _pageEnterTime = null;
    _activeTrackedPost = null;
    _activeTrackingAttribution = null;

    if (_mapPostContentType(post) == ContentType.video) {
      final evidence = _activeVideoBinding?.session
          .takeEffectivePlaybackEvidence();
      if (evidence != null && evidence.qualifies) {
        _contentEngagementTracker.trackEffectivePlayback(
          post.id,
          playbackSessionId: evidence.playbackSessionId,
          effectivePlayMs: evidence.effectivePlayMs,
          consumedRatio: evidence.consumedRatio,
          totalUnits: evidence.totalUnits,
        );
      }
    }
    unawaited(
      _contentEngagementTracker.trackContentExit(post.id, emitDwell: false),
    );
  }

  ContentType _mapPostContentType(PostBaseDto post) =>
      WorksImmersiveViewerObservability.contentTypeForPost(post);
}
