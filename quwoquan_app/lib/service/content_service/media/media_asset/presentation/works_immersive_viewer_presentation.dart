part of 'works_immersive_viewer.dart';

enum _WorksInternalFeedTerminal {
  loading,
  content,
  canonicalEmpty,
  blockingError,
}

final class _WorksInternalFeedAggregate {
  const _WorksInternalFeedAggregate({
    required this.terminal,
    required this.posts,
    this.blockingError,
    this.emptyReason,
  });

  final _WorksInternalFeedTerminal terminal;
  final List<ContentPostViewData> posts;
  final Object? blockingError;
  final ContentFeedEmptyReason? emptyReason;
}

extension _WorksImmersiveViewerPresentation on _WorksImmersiveViewerState {
  List<ContentPostViewData> _buildFeed() {
    if (_usesExternalFeed) {
      final external = widget.externalPosts!;
      final filterTypes = _effectiveFilterContentTypes;
      if (filterTypes.contains('image') && filterTypes.length == 1) {
        return external.where(_isImageLikePost).toList(growable: false);
      }
      if (filterTypes.contains('video') && filterTypes.length == 1) {
        return external.where(_isVideoLikePost).toList(growable: false);
      }
      if (filterTypes.contains('article') && filterTypes.length == 1) {
        return external
            .where(
              (post) => _isArticleLikePost(post) || _isTextOnlyMomentPost(post),
            )
            .toList(growable: false);
      }
      if (filterTypes.isNotEmpty) {
        return external
            .where((post) {
              if (filterTypes.contains('image') && _isImageLikePost(post)) {
                return true;
              }
              if (filterTypes.contains('video') && _isVideoLikePost(post)) {
                return true;
              }
              if (filterTypes.contains('article') &&
                  (_isArticleLikePost(post) || _isTextOnlyMomentPost(post))) {
                return true;
              }
              return false;
            })
            .toList(growable: false);
      }
      return external;
    }
    return _buildInternalFeedAggregate().posts;
  }

  _WorksInternalFeedAggregate _buildInternalFeedAggregate() {
    final channelIds = _trackedFeedTabIds;
    final feedStates = <String, AsyncValue<WorksViewerFeedSnapshot>>{
      for (final channelId in channelIds)
        channelId: ref.watch(worksViewerFeedProvider(channelId)),
    };
    final snapshots = <String, WorksViewerFeedSnapshot>{
      for (final entry in feedStates.entries) entry.key: ?entry.value.value,
    };
    final posts = _buildInternalFeedPosts(snapshots);
    if (posts.isNotEmpty) {
      return _WorksInternalFeedAggregate(
        terminal: _WorksInternalFeedTerminal.content,
        posts: posts,
      );
    }

    for (final entry in feedStates.entries) {
      final state = entry.value;
      final error = state.hasError ? state.error : state.value?.blockingError;
      if (error != null) {
        return _WorksInternalFeedAggregate(
          terminal: _WorksInternalFeedTerminal.blockingError,
          posts: posts,
          blockingError: error,
        );
      }
    }

    if (feedStates.values.any(
      (state) => state.isLoading || (state.value?.isLoading ?? false),
    )) {
      return _WorksInternalFeedAggregate(
        terminal: _WorksInternalFeedTerminal.loading,
        posts: posts,
      );
    }

    final emptyReasons = <ContentFeedEmptyReason>[
      for (final channelId in channelIds) ?snapshots[channelId]?.emptyReason,
    ];
    if (channelIds.isNotEmpty && emptyReasons.length == channelIds.length) {
      final reason =
          emptyReasons.contains(ContentFeedEmptyReason.noActiveRelease)
          ? ContentFeedEmptyReason.noActiveRelease
          : emptyReasons.first;
      return _WorksInternalFeedAggregate(
        terminal: _WorksInternalFeedTerminal.canonicalEmpty,
        posts: posts,
        emptyReason: reason,
      );
    }

    return _WorksInternalFeedAggregate(
      terminal: _WorksInternalFeedTerminal.blockingError,
      posts: posts,
      blockingError: StateError(
        'Works feed completed without content or a canonical empty reason.',
      ),
    );
  }

  List<ContentPostViewData> _buildInternalFeedPosts(
    Map<String, WorksViewerFeedSnapshot> snapshots,
  ) {
    if (_isPremiumStreamSource) {
      // 精品流单路数据源（B3）：premium 频道经服务端 premium_stream fail-closed
      // 池召回（recallPath=premium_pool）；池空返回空列表即空态，不混入浏览流。
      final premium =
          snapshots['premium']?.items ?? const <ContentPostViewData>[];
      final filterTypes = _effectiveFilterContentTypes;
      if (filterTypes.isEmpty) {
        return premium;
      }
      return premium
          .where((post) {
            if (filterTypes.contains('image') && _isImageLikePost(post)) {
              return true;
            }
            if (filterTypes.contains('video') && _isVideoLikePost(post)) {
              return true;
            }
            if (filterTypes.contains('article') &&
                (_isArticleLikePost(post) || _isTextOnlyMomentPost(post))) {
              return true;
            }
            return false;
          })
          .toList(growable: false);
    }
    final photos = snapshots['photo']?.items ?? const <ContentPostViewData>[];
    final videos = snapshots['video']?.items ?? const <ContentPostViewData>[];
    final articles =
        snapshots['article']?.items ?? const <ContentPostViewData>[];

    final filterTypes = _effectiveFilterContentTypes;
    if (filterTypes.contains('image') && filterTypes.length == 1) return photos;
    if (filterTypes.contains('video') && filterTypes.length == 1) return videos;
    if (filterTypes.contains('article') && filterTypes.length == 1) {
      return articles;
    }
    if (filterTypes.isNotEmpty) {
      final result = <ContentPostViewData>[];
      final maxLen = max(photos.length, max(videos.length, articles.length));
      for (var i = 0; i < maxLen; i++) {
        if (filterTypes.contains('image') && i < photos.length) {
          result.add(photos[i]);
        }
        if (filterTypes.contains('video') && i < videos.length) {
          result.add(videos[i]);
        }
        if (filterTypes.contains('article') && i < articles.length) {
          result.add(articles[i]);
        }
      }
      return result;
    }

    final result = <ContentPostViewData>[];
    final maxLen = max(photos.length, max(videos.length, articles.length));
    for (var i = 0; i < maxLen; i++) {
      if (i < photos.length) result.add(photos[i]);
      if (i < videos.length) result.add(videos[i]);
      if (i < articles.length) result.add(articles[i]);
    }
    return result;
  }

  bool _hasStructuredArticlePayload(Map<String, Object?>? raw) {
    if (raw == null) {
      return false;
    }
    if ((raw[ContentMediaPostProjectionKeys.articleMarkdown]
                ?.toString()
                .trim() ??
            '')
        .isNotEmpty) {
      return true;
    }
    return false;
  }

  Map<String, Object?>? _effectiveRawPostById(String postId) {
    return _hydratedRawPostsById[postId] ?? _rawPostById(postId);
  }

  Map<String, Object?> _rawArticleDataFor(ContentPostViewData post) {
    final raw = _effectiveRawPostById(post.id);
    final hasStructuredPayload = _hasStructuredArticlePayload(raw);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    final rawBody = raw?['body']?.toString().trim() ?? '';
    return <String, Object?>{
      ...?raw,
      'postId': post.id,
      'type': (raw?['contentType'] ?? 'article').toString(),
      'contentType': (raw?['contentType'] ?? 'article').toString(),
      'authorId': (raw?['authorId'] ?? post.authorId).toString(),
      'displayName': (raw?['authorDisplayName'] ?? post.displayName).toString(),
      'authorAvatarUrl': (raw?['authorAvatarUrl'] ?? post.avatarUrl).toString(),
      'title': rawTitle.isNotEmpty
          ? rawTitle
          : (hasStructuredPayload ? '' : post.title),
      'body': rawBody.isNotEmpty
          ? rawBody
          : (hasStructuredPayload ? '' : post.body),
      'coverUrl':
          (raw?[ContentMediaPostProjectionKeys.coverUrl] ?? post.coverUrl)
              .toString(),
      'thumbnailUrl': (raw?['thumbnailUrl'] ?? post.thumbnailUrl).toString(),
      'mediaUrls': raw?['mediaUrls'] ?? post.imageUrls,
      'likeCount': raw?['likeCount'] ?? post.likeCount,
      'commentCount': raw?['commentCount'] ?? post.commentCount,
      'shareCount': raw?['shareCount'] ?? post.shareCount,
      'createdAt': raw?['createdAt'] ?? post.createdAt,
    };
  }

  ContentArticleRender _articleViewFor(ContentPostViewData post) {
    final PostArticleDetailProjector projector = ref.read(
      postArticleDetailProjectorProvider,
    );
    // _rawArticleDataFor 每次返回新建 map，无需再做防御拷贝。
    return projector.project(
      _rawArticleDataFor(post),
      fallbackArticleId: post.id,
    );
  }

  int _articlePageCount(ContentPostViewData post) {
    return (_resolvedArticlePageCount[post.id] ??
            _articleViewFor(post).pages.length)
        .clamp(1, 99);
  }

  void _handleResolvedArticlePageCount(String postId, int pageCount) {
    final safePageCount = pageCount.clamp(1, 99);
    if (_resolvedArticlePageCount[postId] == safePageCount) {
      return;
    }
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted ||
          !_postStateWindow.contains(postId) ||
          _resolvedArticlePageCount[postId] == safePageCount) {
        return;
      }
      _setMountedState(() {
        _rememberPostLocalState(postId);
        _resolvedArticlePageCount[postId] = safePageCount;
      });
    });
  }

  ({int current, int total}) _innerProgress(List<ContentPostViewData> posts) {
    if (posts.isEmpty) return (current: 1, total: 1);
    final idx = _currentPage.clamp(0, posts.length - 1);
    final current = posts[idx];
    if (_isImageLikePost(current)) {
      final imageUrls = _imageUrlsForPost(current);
      final total = imageUrls.isEmpty ? 1 : imageUrls.length;
      final currentIndex =
          (_photoInnerIndex[current.id] ?? _defaultImageIndexFor(current))
              .clamp(0, total - 1) +
          1;
      return (current: currentIndex, total: total);
    }
    if (_isArticleLikePost(current)) {
      final total = _articlePageCount(current);
      final currentCard =
          (_articleInnerIndex[current.id] ?? 0).clamp(0, total - 1) + 1;
      return (current: currentCard, total: total);
    }
    if (_isTextOnlyMomentPost(current)) {
      return (current: 1, total: 1);
    }
    if (_isVideoLikePost(current)) {
      final items = _videoItemsFor(current);
      final total = items.isEmpty ? 1 : items.length.clamp(1, 99);
      final currentEpisode = _videoIndexFor(current.id, items) + 1;
      return (current: currentEpisode, total: total);
    }
    return (current: 1, total: 1);
  }

  bool _isVideoLikePost(ContentPostViewData post) {
    if (post.isVideoLike) {
      return true;
    }
    if (post.type.trim().toLowerCase() == 'video') {
      return true;
    }
    return _videoItemsFor(post).isNotEmpty;
  }

  bool _isArticleLikePost(ContentPostViewData post) {
    return post.isArticleLike;
  }

  bool _isTextOnlyMomentPost(ContentPostViewData post) {
    return post.identity == 'moment' && post.isTextOnly;
  }

  bool _isImageLikePost(ContentPostViewData post) {
    if (_isVideoLikePost(post) ||
        _isArticleLikePost(post) ||
        _isTextOnlyMomentPost(post)) {
      return false;
    }
    return _imageUrlsForPost(post).isNotEmpty;
  }

  bool get _canSwipePrimaryTabs =>
      widget.showTopNavigation &&
      (widget.onSwitchToFollowing != null || widget.onSwitchToCircles != null);

  bool get _canDismissViewerWithEdgeGesture =>
      widget.onDismissed != null || widget.onTapBack != null;

  bool _supportsEdgeDismissDirection(TabSwipeDirection direction) {
    if (!_canDismissViewerWithEdgeGesture) {
      return false;
    }
    return switch (Theme.of(context).platform) {
      TargetPlatform.android || TargetPlatform.fuchsia => true,
      TargetPlatform.iOS ||
      TargetPlatform.macOS ||
      TargetPlatform.linux ||
      TargetPlatform.windows => direction == TabSwipeDirection.previous,
    };
  }

  bool _edgeDismissWouldStealPageFlip(TabSwipeDirection direction) {
    final capabilities = _gestureCapabilitiesForCurrentPost();
    if (capabilities == null) {
      return false;
    }
    return switch (direction) {
      TabSwipeDirection.previous => capabilities.canFlipBack,
      TabSwipeDirection.next => capabilities.canFlipForward,
    };
  }

  void _resetEdgeDismissTracking() {
    _activeEdgeDismissDirection = null;
    _activeEdgeDismissDistance = 0;
  }

  void _handleEdgeDismissDragStart(TabSwipeDirection direction) {
    _activeEdgeDismissDirection = direction;
    _activeEdgeDismissDistance = 0;
  }

  void _handleEdgeDismissDragUpdate(
    DragUpdateDetails details,
    TabSwipeDirection direction,
  ) {
    if (_activeEdgeDismissDirection != direction) {
      return;
    }
    final signedDelta = direction == TabSwipeDirection.previous
        ? details.delta.dx
        : -details.delta.dx;
    _activeEdgeDismissDistance = max(
      0,
      _activeEdgeDismissDistance + signedDelta,
    );
  }

  void _handleEdgeDismissDragEnd(
    DragEndDetails details,
    TabSwipeDirection direction,
  ) {
    if (_activeEdgeDismissDirection != direction) {
      return;
    }
    final signedVelocity = direction == TabSwipeDirection.previous
        ? (details.primaryVelocity ?? 0)
        : -(details.primaryVelocity ?? 0);
    final shouldDismiss =
        _activeEdgeDismissDistance >=
            _WorksImmersiveViewerState._edgeDismissMinDistance ||
        signedVelocity >= _WorksImmersiveViewerState._edgeDismissMinVelocity;
    _resetEdgeDismissTracking();
    if (shouldDismiss) {
      _dismissViewer();
    }
  }

  Widget _buildEdgeDismissHotzone(TabSwipeDirection direction) {
    if (!_supportsEdgeDismissDirection(direction) ||
        _edgeDismissWouldStealPageFlip(direction)) {
      return const SizedBox.shrink();
    }
    return Positioned(
      top: 0,
      bottom: 0,
      left: direction == TabSwipeDirection.previous ? 0 : null,
      right: direction == TabSwipeDirection.next ? 0 : null,
      child: SizedBox(
        key: ValueKey<String>('works-edge-dismiss-${direction.name}'),
        width: _WorksImmersiveViewerState._edgeDismissHotzoneWidth,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onHorizontalDragStart: (_) => _handleEdgeDismissDragStart(direction),
          onHorizontalDragUpdate: (details) =>
              _handleEdgeDismissDragUpdate(details, direction),
          onHorizontalDragEnd: (details) =>
              _handleEdgeDismissDragEnd(details, direction),
          onHorizontalDragCancel: _resetEdgeDismissTracking,
          child: const SizedBox.expand(),
        ),
      ),
    );
  }

  void _switchToPreviousPrimaryTab() {
    if (widget.onSwitchToFollowing != null) {
      widget.onSwitchToFollowing!();
    }
  }

  void _switchToNextPrimaryTab() {
    widget.onSwitchToCircles?.call();
  }

  void _handlePrimaryTabSwipe(TabSwipeDirection direction) {
    if (!_canSwipePrimaryTabs) {
      return;
    }
    if (direction == TabSwipeDirection.previous) {
      _switchToPreviousPrimaryTab();
      return;
    }
    _switchToNextPrimaryTab();
  }

  void _handlePrimaryTabSwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handlePrimaryTabSwipe(direction);
  }

  List<String> _imageUrlsForPost(ContentPostViewData post) {
    final projected = _workItemFor(post).effectiveImageUrls
        .map((url) => url.trim())
        .where((url) => url.isNotEmpty)
        .toList(growable: false);
    final fallback = post.hasImages
        ? post.mediaImageUrls
        : post.primaryImageUrl.isNotEmpty
        ? <String>[post.primaryImageUrl]
        : const <String>[];
    final canonical = projected.isNotEmpty ? projected : fallback;
    final overrides = _originalImageUrlsByPostId[post.id];
    if (overrides == null || overrides.isEmpty) {
      return canonical;
    }
    final now = DateTime.now();
    return <String>[
      for (var index = 0; index < canonical.length; index++)
        if (overrides[index]?.isUsableAt(now) ?? false)
          overrides[index]!.url
        else
          canonical[index],
    ];
  }

  String? _originalMediaIdFor(ContentPostViewData post, int imageIndex) {
    final item = _workItemFor(post);
    final imageItems = item.mediaItems
        .where((media) => media.kind == 'image' && media.url.trim().isNotEmpty)
        .toList(growable: false);
    if (imageIndex >= 0 && imageIndex < imageItems.length) {
      final mediaId = imageItems[imageIndex].mediaAssetId?.trim() ?? '';
      if (mediaId.isNotEmpty) {
        return mediaId;
      }
    }
    if (_imageUrlsForPost(post).length == 1) {
      final mediaId = item.mediaAssetId?.trim() ?? '';
      if (mediaId.isNotEmpty) {
        return mediaId;
      }
    }
    return null;
  }

  int _defaultImageIndexFor(ContentPostViewData post) {
    if (!_usesExternalFeed) return 0;
    final initialPost = widget.externalPosts![_safeInitialPage];
    if (post.id != initialPost.id) return 0;
    final total = _imageUrlsForPost(post).length;
    if (total <= 1) return 0;
    return widget.initialImageIndex.clamp(0, total - 1);
  }

  /// 作品级统一投影：canonical Post + viewer supplemental 收敛为 ViewData。
  /// 视频集（mediaItems）、图片序列、交集摘要只允许从该投影读取。
  WorkBrowserViewData _workItemFor(ContentPostViewData post) {
    final cached = _workItemCache.read(post.id);
    if (cached != null) return cached;
    final raw = _effectiveRawPostById(post.id);
    final item = WorkBrowserViewData.fromPost(
      post,
      supplemental: raw == null
          ? null
          : Map<String, Object?>.from(
              raw.map((key, value) => MapEntry(key.toString(), value)),
            ),
    );
    _workItemCache.write(post.id, item);
    return item;
  }

  /// 视频集序列：契约 mediaItems[kind=video]，为空时回落单视频；边界解析为交付引用。
  List<_WorksVideoDeliveryItem> _videoItemsFor(ContentPostViewData post) {
    final endpointConfig = ref.watch(mediaEndpointConfigProvider);
    if (endpointConfig == null) {
      return const <_WorksVideoDeliveryItem>[];
    }
    final resolver = MediaDeliveryResolver(endpointConfig);
    final rawItems = _workItemFor(post).videoItems;
    final sources = rawItems.isNotEmpty
        ? rawItems
        : (post.mediaVideoUrl.isEmpty
              ? const <WorkBrowserMediaViewData>[]
              : <WorkBrowserMediaViewData>[
                  WorkBrowserMediaViewData(
                    kind: 'video',
                    url: post.mediaVideoUrl,
                    coverUrl: post.mediaVideoCoverUrl.isEmpty
                        ? null
                        : post.mediaVideoCoverUrl,
                    durationMs: post.durationMs,
                    mediaAssetId: _workItemFor(post).mediaAssetId,
                    mediaAssetVersion: _workItemFor(post).mediaAssetVersion,
                    previewTrackManifestUrl: _workItemFor(
                      post,
                    ).previewTrackManifestUrl,
                    previewTrackVersion: _workItemFor(post).previewTrackVersion,
                    hlsCmafMasterManifestUrl: post.hlsCmafMasterManifestUrl,
                    hlsCmafDescriptorVersion: post.hlsCmafDescriptorVersion,
                  ),
                ]);
    final resolved = <_WorksVideoDeliveryItem>[];
    final identityAllocator = WorksVideoEpisodeIdentityAllocator(post.id);
    for (final item in sources) {
      final delivery = resolver.tryResolve(
        item.url,
        kind: MediaDeliveryKind.video,
        assetId: item.mediaAssetId ?? post.id,
        version: item.mediaAssetVersion ?? 0,
      );
      if (delivery == null) {
        continue;
      }
      final assetId = item.mediaAssetId?.trim() ?? '';
      final assetVersion = item.mediaAssetVersion ?? 0;
      final adaptiveDelivery = assetId.isEmpty || assetVersion <= 0
          ? null
          : resolver.tryResolve(
              item.hlsCmafMasterManifestUrl,
              kind: MediaDeliveryKind.video,
              assetId: assetId,
              version: assetVersion,
            );
      resolved.add(
        _WorksVideoDeliveryItem(
          identity: identityAllocator.allocate(
            deliveryCacheIdentity: delivery.cacheIdentity,
            mediaAssetId: item.mediaAssetId,
            mediaAssetVersion: item.mediaAssetVersion,
          ),
          deliveryReference: delivery,
          adaptiveDeliveryReference: adaptiveDelivery,
          adaptiveDescriptorVersion: item.hlsCmafDescriptorVersion ?? 0,
          coverReference: resolver.tryResolve(
            item.coverUrl,
            kind: MediaDeliveryKind.image,
            assetId: item.mediaAssetId ?? post.id,
            version: item.mediaAssetVersion ?? 0,
          ),
          verifiedDuration: item.durationMs == null
              ? null
              : Duration(milliseconds: item.durationMs!),
          previewTrackDescriptor: _previewTrackDescriptor(
            resolver: resolver,
            item: item,
          ),
        ),
      );
    }
    return resolved;
  }

  int _videoIndexFor(String postId, List<_WorksVideoDeliveryItem> items) {
    if (items.isEmpty) {
      return 0;
    }
    final identity = _videoInnerIdentity[postId];
    if (identity != null) {
      final identityIndex = items.indexWhere(
        (item) => item.identity == identity,
      );
      if (identityIndex >= 0) {
        return identityIndex;
      }
    }
    return (_videoInnerIndex[postId] ?? 0).clamp(0, items.length - 1);
  }

  VideoPreviewTrackDescriptor? _previewTrackDescriptor({
    required MediaDeliveryResolver resolver,
    required WorkBrowserMediaViewData item,
  }) {
    final assetId = item.mediaAssetId?.trim() ?? '';
    final assetVersion = item.mediaAssetVersion ?? 0;
    final trackVersion = item.previewTrackVersion ?? 0;
    if (assetId.isEmpty || assetVersion <= 0 || trackVersion <= 0) {
      return null;
    }
    final reference = resolver.tryResolve(
      item.previewTrackManifestUrl,
      kind: MediaDeliveryKind.video,
      assetId: assetId,
      version: assetVersion,
    );
    if (reference == null) {
      return null;
    }
    return VideoPreviewTrackDescriptor(
      assetId: assetId,
      assetVersion: assetVersion,
      trackVersion: trackVersion,
      manifestReference: reference,
    );
  }

  void _applyFilterSelection(Set<String> selectedIds) {
    final nextIds = selectedIds.isEmpty || selectedIds.contains('all')
        ? <String>{'all'}
        : selectedIds;
    _setMountedState(() {
      _selectedWorkFilterIds = nextIds;
      _currentPage = 0;
      _invalidateVideoViewport(resetDurationWindow: false);
      _pageController.jumpToPage(0);
    });
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _retainPostLocalStateAround(_buildFeed(), _currentPage);
    });
  }

  Map<String, Object?>? _rawPostById(String postId) {
    final external = widget.rawPostsById[postId];
    if (external != null) return external.toObjectMap();
    return null;
  }

  ContentSurfaceView? _summaryForPost(String postId) {
    final external = widget.externalPostViews;
    if (external == null || external.isEmpty) return null;
    for (final item in external) {
      if (item.postId == postId) return item;
    }
    return null;
  }

  String _titleForPost(ContentPostViewData post) {
    final raw = _effectiveRawPostById(post.id);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    if (rawTitle.isNotEmpty) return rawTitle;
    final summary = _summaryForPost(post.id);
    final summaryTitle = summary?.title?.trim() ?? '';
    if (summaryTitle.isNotEmpty) return summaryTitle;
    return post.normalizedTitle;
  }

  String _bodyForPost(ContentPostViewData post) {
    final raw = _effectiveRawPostById(post.id);
    final rawBody =
        raw?['body']?.toString().trim() ??
        raw?[ContentMediaPostProjectionKeys.description]?.toString().trim() ??
        raw?[ContentMediaPostProjectionKeys.content]?.toString().trim() ??
        raw?[ContentMediaPostProjectionKeys.caption]?.toString().trim() ??
        '';
    if (rawBody.isNotEmpty) return rawBody;
    final summary = _summaryForPost(post.id);
    final summaryBody = summary?.body?.trim() ?? '';
    if (summaryBody.isNotEmpty) return summaryBody;
    return post.normalizedBody;
  }

  String _overlayTitleForPost(ContentPostViewData post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _titleForPost(post);
  }

  String _overlayBodyForPost(ContentPostViewData post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _bodyForPost(post);
  }

  _WorksTopChromeTheme _topChromeThemeForPost(
    BuildContext context,
    ContentPostViewData? post,
  ) {
    return _WorksTopChromeTheme(
      overlayStyle: const SystemUiOverlayStyle(
        statusBarColor: AppColors.black,
        statusBarIconBrightness: Brightness.light,
        statusBarBrightness: Brightness.dark,
        systemNavigationBarColor: AppColors.black,
        systemNavigationBarIconBrightness: Brightness.light,
      ),
      foregroundColor: AppColors.white,
      mutedForegroundColor: AppColors.white.withValues(alpha: 0.72),
    );
  }

  ArticlePaperTexture _resolveArticlePaperTexture(ContentPostViewData post) {
    final override = _articlePaperThemeOverrides[post.id];
    if (override != null && override != 'system') {
      return articlePaperTextureFromString(override);
    }
    final item = _workItemFor(post);
    final profileTexture = item.articleRenderProfile?['paperTexture']
        ?.toString();
    if (profileTexture != null && profileTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(profileTexture);
    }
    final topLevelTexture = item.paperTexture;
    if (topLevelTexture != null && topLevelTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(topLevelTexture);
    }
    return articlePaperTextureFromString(
      _contentMediaViewerPolicy.articleDarkPaperDefaultTheme,
    );
  }

  void _handleArticleInlineMentionTap(
    ContentPostViewData post,
    ArticleInlineSpan span,
  ) {
    final targetType = span.targetType?.trim();
    final targetId = span.targetId?.trim() ?? '';
    if (targetId.isEmpty) return;
    // 行内链接（GWT-004）：白名单 scheme 已在解析期收口，这里只负责打开。
    if (span.isLink) {
      final uri = Uri.tryParse(targetId);
      if (uri != null) {
        unawaited(launchUrl(uri, mode: LaunchMode.externalApplication));
      }
      return;
    }
    if (span.isTag) {
      final tagRef = _tagRefForArticleMention(targetId);
      if (tagRef.isEmpty) return;
      context.push(AppRoutePaths.globalSearchNetworkResults(query: tagRef));
      return;
    }
    if (targetType == 'homepage') {
      context.push(AppRoutePaths.homepageDetail(id: targetId));
      return;
    }
    if (targetType != 'entity') return;
    final homepageId = _workItemFor(post).entityMentions
        .where((mention) => mention.subjectId.trim() == targetId)
        .map((mention) => mention.homepageId.trim())
        .where((id) => id.isNotEmpty)
        .firstOrNull;
    if (homepageId == null) return;
    context.push(AppRoutePaths.homepageDetail(id: homepageId));
  }

  String _tagRefForArticleMention(String targetId) {
    final normalized = targetId.trim();
    return normalized.startsWith('tag:')
        ? normalized.substring('tag:'.length)
        : normalized;
  }

  bool _showsCaptionOverlay(ContentPostViewData post) {
    if (_isArticleLikePost(post)) {
      return false;
    }
    // 视频作品恒显示 caption 区（极简控制条挂载在 caption header）。
    if (_isVideoLikePost(post)) {
      return true;
    }
    // 图片多图作品恒显示（点指示器挂载在 caption header）。
    if (_isImageLikePost(post) && _imageUrlsForPost(post).length > 1) {
      return true;
    }
    return _overlayTitleForPost(post).isNotEmpty ||
        _overlayBodyForPost(post).isNotEmpty;
  }

  ImmersiveViewerStageLayoutSpec _layoutSpecForPost(ContentPostViewData post) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  ImmersiveViewerStageLayoutSpec _engagementLayoutSpecForPost(
    ContentPostViewData post,
  ) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  double _statusBarContentInsetFor(ContentPostViewData post) {
    if (_isArticleLikePost(post)) {
      return AppSpacing.zero;
    }
    if (widget.topChromeSafeInset <= AppSpacing.zero) {
      return AppSpacing.zero;
    }
    return _shouldMediaInvadeStatusBar(post)
        ? AppSpacing.zero
        : widget.topChromeSafeInset;
  }

  bool _shouldMediaInvadeStatusBar(ContentPostViewData post) {
    if (_isVideoLikePost(post)) {
      return true;
    }
    if (!_isImageLikePost(post)) {
      return false;
    }
    final aspectRatio = post.aspectRatio;
    if (aspectRatio == null || aspectRatio <= AppSpacing.zero) {
      return false;
    }
    return aspectRatio <= AppSpacing.immersiveStatusBarMaxAspectRatio;
  }

  bool _isCaptionExpanded(String postId) {
    return _expandedCaptionPostIds.contains(postId);
  }

  void _toggleCaptionExpanded(String postId) {
    _setMountedState(() {
      _rememberPostLocalState(postId);
      if (_expandedCaptionPostIds.contains(postId)) {
        _expandedCaptionPostIds.remove(postId);
      } else {
        _expandedCaptionPostIds.add(postId);
      }
    });
  }
}
