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

  WorksViewerFeedSnapshot? _readFeedState(String tabId) {
    return ref.read(worksViewerFeedProvider(tabId)).value;
  }

  AsyncValue<WorksViewerFeedSnapshot> _readFeedAsync(String tabId) {
    return ref.read(worksViewerFeedProvider(tabId));
  }

  bool _trackedFeedsHaveMore() {
    return _trackedFeedTabIds.any(
      (tabId) => _readFeedState(tabId)?.hasMore ?? false,
    );
  }

  bool _trackedFeedsLoading() {
    return _trackedFeedTabIds.any((tabId) {
      final state = _readFeedAsync(tabId);
      return state.isLoading || (state.value?.isLoading ?? false);
    });
  }

  Object? _trackedFeedsError() {
    for (final tabId in _trackedFeedTabIds) {
      final state = _readFeedAsync(tabId);
      final snapshot = state.value;
      final error = state.hasError
          ? state.error
          : snapshot?.blockingError ?? snapshot?.appendError;
      if (error != null) {
        return error;
      }
    }
    return null;
  }

  Future<UiRecoveryOutcome> _retryTrackedFeeds() async {
    final commands = ref.read(worksViewerFeedCommandsProvider);
    final recoveryGeneration = ++_feedRecoveryGeneration;
    final trackedTabIds = List<String>.unmodifiable(_trackedFeedTabIds);
    final results = await Future.wait<DiscoveryFeedLoadResult>([
      for (final tabId in trackedTabIds) commands.load(tabId, force: true),
    ]);
    if (!mounted ||
        recoveryGeneration != _feedRecoveryGeneration ||
        trackedTabIds.join('\u001f') != _trackedFeedTabIds.join('\u001f')) {
      return UiRecoveryOutcome.superseded;
    }
    if (results.any(
      (result) =>
          result.terminal == DiscoveryFeedLoadTerminal.content ||
          result.terminal == DiscoveryFeedLoadTerminal.retainedContent,
    )) {
      return UiRecoveryOutcome.recovered;
    }
    if (results.any(
      (result) => result.terminal == DiscoveryFeedLoadTerminal.stillBlocked,
    )) {
      return UiRecoveryOutcome.stillBlocked;
    }
    if (results.isNotEmpty &&
        results.every(
          (result) =>
              result.terminal == DiscoveryFeedLoadTerminal.canonicalEmpty,
        )) {
      return UiRecoveryOutcome.recovered;
    }
    return UiRecoveryOutcome.superseded;
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
        ref.read(worksViewerFeedCommandsProvider).appendNextPage(tabId),
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
        _rememberPostLocalState(postId);
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

  ({String? feedRequestId, String? policyDigest}) _feedAttributionForPost(
    ContentPostViewData post,
  ) {
    if (_usesExternalFeed) {
      return (
        feedRequestId: widget.feedRequestId,
        policyDigest: widget.policyDigest,
      );
    }
    final tabId = _isPremiumStreamSource
        ? 'premium'
        : _isVideoLikePost(post)
        ? 'video'
        : _isArticleLikePost(post) || _isTextOnlyMomentPost(post)
        ? 'article'
        : 'photo';
    final feed = _readFeedState(tabId);
    return (
      feedRequestId: feed?.feedRequestId,
      policyDigest: feed?.policyDigest,
    );
  }

  int _attributedPosition(int viewerIndex) {
    final initialFeedPosition = widget.initialFeedPosition;
    if (!_usesExternalFeed || initialFeedPosition == null) {
      return viewerIndex;
    }
    return max(0, initialFeedPosition + viewerIndex - _safeInitialPage);
  }

  void _trackImpressionForPost(ContentPostViewData post, {int? position}) {
    _articleHydrationAdmission.retainOnly(post.id);
    _rememberPostLocalState(post.id);
    final feedAttribution = _feedAttributionForPost(post);
    final viewerPosition = position ?? _currentPage;
    final attributedPosition = _attributedPosition(viewerPosition);
    final attribution = _WorksTrackingAttribution(
      referralSource: widget.referralSource,
      feedRequestId: feedAttribution.feedRequestId,
      position: attributedPosition,
      channelId: _immersiveChannelId(),
      policyDigest: feedAttribution.policyDigest,
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
      policyDigest: attribution.policyDigest,
      recallPath: post.recallPath,
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
    _articleReaderObservability.trackReaderOpen(
      postId: post.id,
      durationMs: DateTime.now().difference(_viewerOpenedAt).inMilliseconds,
      source: widget.source,
      template: article.template.name,
      fontPreset: article.fontPreset.name,
      pageCount: article.pages.length.clamp(1, 99),
      bookReaderEnabled: bookReaderEnabled,
    );
    if (!bookReaderEnabled) {
      _articleReaderObservability.trackReaderFallback(
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
    required ContentPostViewData post,
    required ContentArticleRender article,
    required bool hydrated,
  }) {
    if (article.documentSource == ArticleDetailDocumentSource.markdown) {
      return;
    }
    final bookReaderEnabled = ref.read(
      contentFeatureFlagProvider('enable_article_book_reader'),
    );
    _articleReaderObservability.trackReaderFallback(
      postId: post.id,
      reason:
          'document_structure:${WorksImmersiveViewerObservability.documentSourceName(article.documentSource)}:hydrated=$hydrated',
      bookReaderEnabled: bookReaderEnabled,
    );
  }

  Future<WorksViewerArticleHydrationResult> _maybeHydrateArticleDetail(
    ContentPostViewData post, {
    bool force = false,
  }) async {
    final raw = _effectiveRawPostById(post.id);
    if (_hasStructuredArticlePayload(raw)) {
      return WorksViewerArticleHydrationResult(
        terminal: WorksViewerArticleHydrationTerminal.recovered,
        generation: _articleHydrationAdmission.latestGeneration,
      );
    }
    if (!force && _failedArticleHydrationIds.contains(post.id)) {
      return WorksViewerArticleHydrationResult(
        terminal: WorksViewerArticleHydrationTerminal.stillBlocked,
        generation: _articleHydrationAdmission.latestGeneration,
        failure: _failedArticleHydrationErrorsById[post.id],
      );
    }
    return _articleHydrationAdmission.schedule(
      postId: post.id,
      task: (lease) =>
          _performArticleDetailHydration(post, force: force, lease: lease),
    );
  }

  Future<WorksViewerArticleHydrationTerminal> _performArticleDetailHydration(
    ContentPostViewData post, {
    required bool force,
    required WorksViewerArticleHydrationLease lease,
  }) async {
    final raw = _effectiveRawPostById(post.id);
    if (lease.isCancelled) {
      return WorksViewerArticleHydrationTerminal.superseded;
    }
    if (_hasStructuredArticlePayload(raw)) {
      return WorksViewerArticleHydrationTerminal.recovered;
    }
    if (force) {
      _failedArticleHydrationIds.remove(post.id);
      _failedArticleHydrationErrorsById.remove(post.id);
      final recovery = _articleHydrationErrorSemantic(post);
      _articleReaderObservability.trackReaderRecovery(
        postId: post.id,
        recoveryAction: recovery.recoveryAction?.name ?? 'retry',
        result: 'started',
        durationMs: 0,
        errorCode: recovery.sourceCode,
      );
    }
    _rememberPostLocalState(post.id);
    final startedAt = DateTime.now();
    try {
      final detail = await ref
          .read(workBrowserContentPostDetailReaderProvider)
          .getPost(postId: post.id, cancellation: lease.cancellation);
      if (lease.isCancelled ||
          !mounted ||
          !_postStateWindow.contains(post.id)) {
        _articleReaderObservability.trackHydration(
          postId: post.id,
          durationMs: DateTime.now().difference(startedAt).inMilliseconds,
          result: 'superseded',
          trigger: 'get_post',
          hadStructuredPayload: false,
        );
        return WorksViewerArticleHydrationTerminal.superseded;
      }
      applyConfirmedInteractionPost(ref, detail.post);
      _setMountedState(() {
        _rememberPostLocalState(post.id);
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
      _articleReaderObservability.trackHydration(
        postId: post.id,
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        result: 'success',
        trigger: 'get_post',
        hadStructuredPayload: false,
      );
      if (force) {
        _articleReaderObservability.trackReaderRecovery(
          postId: post.id,
          recoveryAction: 'retry',
          result: 'success',
          durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        );
      }
      return WorksViewerArticleHydrationTerminal.recovered;
    } catch (error) {
      if (lease.isCancelled ||
          !mounted ||
          !_postStateWindow.contains(post.id)) {
        _articleReaderObservability.trackHydration(
          postId: post.id,
          durationMs: DateTime.now().difference(startedAt).inMilliseconds,
          result: 'superseded',
          trigger: 'get_post',
          hadStructuredPayload: false,
        );
        return WorksViewerArticleHydrationTerminal.superseded;
      }
      if (mounted && _postStateWindow.contains(post.id)) {
        _setMountedState(() {
          _rememberPostLocalState(post.id);
          _failedArticleHydrationIds.add(post.id);
          _failedArticleHydrationErrorsById[post.id] = error;
        });
      }
      _articleReaderObservability.trackHydration(
        postId: post.id,
        durationMs: DateTime.now().difference(startedAt).inMilliseconds,
        result: 'error',
        trigger: 'get_post',
        hadStructuredPayload: false,
      );
      final semantic = runtime_error_display.runtimeErrorSemantic(
        context,
        error: error,
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      );
      final durationMs = DateTime.now().difference(startedAt).inMilliseconds;
      final recoveryAction = semantic.recoveryAction?.name ?? 'surface';
      final errorCode =
          semantic.sourceCode ?? ContentErrorCode.internalError.code;
      _articleReaderObservability.trackReaderError(
        postId: post.id,
        errorCode: errorCode,
        recoveryAction: recoveryAction,
        durationMs: durationMs,
      );
      if (force) {
        _articleReaderObservability.trackReaderRecovery(
          postId: post.id,
          recoveryAction: recoveryAction,
          result: 'failure',
          durationMs: durationMs,
          errorCode: errorCode,
        );
      }
      return WorksViewerArticleHydrationTerminal.stillBlocked;
    }
  }

  bool _shouldShowArticleHydrationError(
    ContentPostViewData post,
    ContentArticleRender article,
  ) {
    return article.documentSource == ArticleDetailDocumentSource.empty &&
        _failedArticleHydrationIds.contains(post.id);
  }

  UiErrorSemantic _articleHydrationErrorSemantic(ContentPostViewData post) {
    return runtime_error_display.runtimeErrorSemantic(
      context,
      error:
          _failedArticleHydrationErrorsById[post.id] ??
          Exception('article hydration failed'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    );
  }

  String _fallbackReasonName(String reason) =>
      WorksImmersiveViewerObservability.fallbackReasonName(reason);

  void _trackArticleReaderFallback(
    ContentPostViewData post,
    String reason, {
    required bool bookReaderEnabled,
  }) {
    _articleReaderObservability.trackReaderFallback(
      postId: post.id,
      reason: _fallbackReasonName(reason),
      bookReaderEnabled: bookReaderEnabled,
    );
  }

  void _trackArticlePageFlipCommit(
    ContentPostViewData post,
    WorksArticlePageFlipEvent event,
  ) {
    _articleReaderObservability.trackPageFlipCommit(
      postId: post.id,
      durationMs: event.durationMs,
      mechanism: event.mechanism,
      direction: event.direction,
      fromPage: event.fromPage,
      toPage: event.toPage,
    );
  }

  void _trackImagePageflipMotion(
    ContentPostViewData post,
    MediaPageFlipMotionEvent event,
  ) {
    final feedAttribution = _feedAttributionForPost(post);
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
          feedRequestId: feedAttribution.feedRequestId,
          position: _attributedPosition(_currentPage),
          channelId: _immersiveChannelId(),
          policyDigest: feedAttribution.policyDigest,
          recallPath: post.recallPath,
          supplySource: post.supplySource,
        );
  }

  void _trackArticlePageCurlAbort(
    ContentPostViewData post,
    WorksArticlePageCurlAbortEvent event,
  ) {
    _articleReaderObservability.trackPageCurlAbort(
      postId: post.id,
      corner: event.corner,
      progress: event.progress,
      direction: event.direction,
    );
  }

  void _flushDwell(ContentPostViewData post, {bool trackSkip = false}) {
    final enterTime = _pageEnterTime;
    final attribution = _activeTrackingAttribution;
    if (enterTime == null ||
        attribution == null ||
        _activeTrackedPost?.id != post.id) {
      return;
    }
    final durationMs = DateTime.now().difference(enterTime).inMilliseconds;
    final durationSec = durationMs / 1000.0;
    _contentBehaviorTracker.trackDwell(
      post.id,
      durationSeconds: durationSec,
      contentType: post.type,
      referralSource: attribution.referralSource,
      feedRequestId: attribution.feedRequestId,
      position: attribution.position,
      channelId: attribution.channelId,
      policyDigest: attribution.policyDigest,
      recallPath: post.recallPath,
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
        policyDigest: attribution.policyDigest,
        recallPath: post.recallPath,
        supplySource: post.supplySource,
      );
    }
    _pageEnterTime = null;
    _activeTrackedPost = null;
    _activeTrackingAttribution = null;

    if (_isArticleLikePost(post)) {
      _articleReaderObservability.trackReaderDwell(
        postId: post.id,
        durationMs: durationMs,
      );
      _articleReaderObservability.trackReaderExit(
        postId: post.id,
        durationMs: durationMs,
      );
    }

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

  ContentType _mapPostContentType(ContentPostViewData post) =>
      WorksImmersiveViewerObservability.contentTypeForPost(post);
}
