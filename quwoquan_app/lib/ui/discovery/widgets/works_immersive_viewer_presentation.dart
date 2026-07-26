part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerPresentation on _WorksImmersiveViewerState {
  List<PostBaseDto> _buildFeed() {
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
    if (_isPremiumStreamSource) {
      // 精品流单路数据源（B3）：premium 频道经服务端 premium_stream fail-closed
      // 池召回（recallPath=premium_pool）；池空返回空列表即空态，不混入浏览流。
      final premium =
          ref.watch(discoveryFeedProvider('premium')).value?.items ??
          const <PostBaseDto>[];
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
    final photos = ref.watch(discoveryFeedProvider('photo')).value?.items ?? [];
    final videos = ref.watch(discoveryFeedProvider('video')).value?.items ?? [];
    final articles =
        ref.watch(discoveryFeedProvider('article')).value?.items ?? [];

    final filterTypes = _effectiveFilterContentTypes;
    if (filterTypes.contains('image') && filterTypes.length == 1) return photos;
    if (filterTypes.contains('video') && filterTypes.length == 1) return videos;
    if (filterTypes.contains('article') && filterTypes.length == 1) {
      return articles;
    }
    if (filterTypes.isNotEmpty) {
      final result = <PostBaseDto>[];
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

    final result = <PostBaseDto>[];
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
    if ((raw[ArticleDetailWireKeys.articleMarkdown]?.toString().trim() ?? '')
        .isNotEmpty) {
      return true;
    }
    return false;
  }

  Map<String, Object?>? _effectiveRawPostById(String postId) {
    return _hydratedRawPostsById[postId] ?? _rawPostById(postId);
  }

  Map<String, Object?> _rawArticleDataFor(PostBaseDto post) {
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
      'coverUrl': (raw?[ArticleDetailWireKeys.coverUrl] ?? post.coverUrl)
          .toString(),
      'thumbnailUrl': (raw?['thumbnailUrl'] ?? post.thumbnailUrl).toString(),
      'mediaUrls': raw?['mediaUrls'] ?? post.imageUrls,
      'likeCount': raw?['likeCount'] ?? post.likeCount,
      'commentCount': raw?['commentCount'] ?? post.commentCount,
      'shareCount': raw?['shareCount'] ?? post.shareCount,
      'createdAt': raw?['createdAt'] ?? post.createdAt,
    };
  }

  ContentArticleRender _articleViewFor(PostBaseDto post) {
    return projectArticleDetailView(
      Map<String, dynamic>.from(_rawArticleDataFor(post)),
      fallbackArticleId: post.id,
    );
  }

  int _articlePageCount(PostBaseDto post) {
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
      if (!mounted || _resolvedArticlePageCount[postId] == safePageCount) {
        return;
      }
      _setMountedState(() {
        _resolvedArticlePageCount[postId] = safePageCount;
      });
    });
  }

  ({int current, int total}) _innerProgress(List<PostBaseDto> posts) {
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

  bool _isVideoLikePost(PostBaseDto post) {
    if (post.isVideoLike) {
      return true;
    }
    if (post.type.trim().toLowerCase() == 'video') {
      return true;
    }
    return _videoItemsFor(post).isNotEmpty;
  }

  bool _isArticleLikePost(PostBaseDto post) {
    return post.isArticleLike;
  }

  bool _isTextOnlyMomentPost(PostBaseDto post) {
    return post.identity == 'moment' && post.isTextOnly;
  }

  bool _isImageLikePost(PostBaseDto post) {
    if (_isVideoLikePost(post) ||
        _isArticleLikePost(post) ||
        _isTextOnlyMomentPost(post)) {
      return false;
    }
    return _imageUrlsForPost(post).isNotEmpty;
  }

  bool get _canSwipePrimaryTabs =>
      widget.showTopNavigation &&
      (widget.onSwitchToFollowing != null ||
          widget.onSwitchToCircles != null ||
          widget.onSwitchToMoment != null);

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
      return;
    }
    widget.onSwitchToMoment?.call();
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

  List<String> _imageUrlsForPost(PostBaseDto post) {
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
    return <String>[
      for (var index = 0; index < canonical.length; index++)
        overrides[index] ?? canonical[index],
    ];
  }

  String? _originalMediaIdFor(PostBaseDto post, int imageIndex) {
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

  int _defaultImageIndexFor(PostBaseDto post) {
    if (!_usesExternalFeed) return 0;
    final initialPost = widget.externalPosts![_safeInitialPage];
    if (post.id != initialPost.id) return 0;
    final total = _imageUrlsForPost(post).length;
    if (total <= 1) return 0;
    return widget.initialImageIndex.clamp(0, total - 1);
  }

  /// 作品级统一投影：raw wire + PostBaseDto 收敛为 [WorkBrowserItemDto]。
  /// 视频集（mediaItems）、图片序列、交集摘要只允许从该投影读取。
  WorkBrowserItemDto _workItemFor(PostBaseDto post) {
    final cached = _workItemCache[post.id];
    if (cached != null) return cached;
    final raw = _effectiveRawPostById(post.id);
    final source = raw == null
        ? post.toMap()
        : Map<String, dynamic>.from(
            raw.map((k, v) => MapEntry(k.toString(), v)),
          );
    final item = WorkBrowserItemDto.fromMap(source);
    _workItemCache[post.id] = item;
    return item;
  }

  /// 视频集序列：契约 mediaItems[kind=video]，为空时回落单视频；边界解析为交付引用。
  List<_WorksVideoDeliveryItem> _videoItemsFor(PostBaseDto post) {
    final resolver = MediaDeliveryResolver.fromRuntimeConfig();
    final rawItems = _workItemFor(post).videoItems;
    final sources = rawItems.isNotEmpty
        ? rawItems
        : (post.mediaVideoUrl.isEmpty
              ? const <WorkBrowserMediaItemDto>[]
              : <WorkBrowserMediaItemDto>[
                  WorkBrowserMediaItemDto(
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
                  ),
                ]);
    final resolved = <_WorksVideoDeliveryItem>[];
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
      resolved.add(
        _WorksVideoDeliveryItem(
          deliveryReference: delivery,
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
    required WorkBrowserMediaItemDto item,
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

  Map<String, dynamic> _wireMapForPresentation(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    if (raw == null) {
      return post.toMap();
    }
    return Map<String, dynamic>.from(
      raw.map((k, v) => MapEntry(k.toString(), v)),
    );
  }

  String _titleForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final rawTitle = raw?['title']?.toString().trim() ?? '';
    if (rawTitle.isNotEmpty) return rawTitle;
    final summary = _summaryForPost(post.id);
    final summaryTitle = summary?.title?.trim() ?? '';
    if (summaryTitle.isNotEmpty) return summaryTitle;
    final pres = PostReadPresentation.fromPostBase(
      post,
      wire: _wireMapForPresentation(post),
    );
    return pres.title.isNotEmpty ? pres.title : post.normalizedTitle;
  }

  String _bodyForPost(PostBaseDto post) {
    final raw = _effectiveRawPostById(post.id);
    final rawBody =
        raw?['body']?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.description]?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.content]?.toString().trim() ??
        raw?[ContentPostImmersiveWireKeys.caption]?.toString().trim() ??
        '';
    if (rawBody.isNotEmpty) return rawBody;
    final summary = _summaryForPost(post.id);
    final summaryBody = summary?.body?.trim() ?? '';
    if (summaryBody.isNotEmpty) return summaryBody;
    final pres = PostReadPresentation.fromPostBase(
      post,
      wire: _wireMapForPresentation(post),
    );
    return pres.body.isNotEmpty ? pres.body : post.normalizedBody;
  }

  String _overlayTitleForPost(PostBaseDto post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _titleForPost(post);
  }

  String _overlayBodyForPost(PostBaseDto post) {
    if (_isArticleLikePost(post) || _isTextOnlyMomentPost(post)) {
      return '';
    }
    return _bodyForPost(post);
  }

  _WorksTopChromeTheme _topChromeThemeForPost(
    BuildContext context,
    PostBaseDto? post,
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

  ArticlePaperTexture _resolveArticlePaperTexture(PostBaseDto post) {
    final override = _articlePaperThemeOverrides[post.id];
    if (override != null && override != 'system') {
      return articlePaperTextureFromString(override);
    }
    final item = _workItemFor(post);
    final profile = item.articleRenderProfile ?? const <String, dynamic>{};
    final profileTexture = _stringFromProfile(profile, 'paperTexture');
    if (profileTexture != null && profileTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(profileTexture);
    }
    final topLevelTexture = item.paperTexture;
    if (topLevelTexture != null && topLevelTexture.trim().isNotEmpty) {
      return articlePaperTextureFromString(topLevelTexture);
    }
    final vertical =
        item.contentVertical ??
        _stringFromProfile(profile, 'contentVertical') ??
        ContentUIConfig.articleDarkPaperDefaultTheme;
    final mapped = ContentUIConfig.articlePaperVerticalDefaults[vertical];
    return articlePaperTextureFromString(
      mapped ?? ContentUIConfig.articleDarkPaperDefaultTheme,
    );
  }

  String? _stringFromProfile(Map<String, dynamic> profile, String key) {
    final value = profile[key];
    if (value == null) return null;
    return value.toString();
  }

  void _handleArticleInlineMentionTap(
    PostBaseDto post,
    ArticleInlineSpan span,
  ) {
    final targetType = span.targetType?.trim();
    final targetId = span.targetId?.trim() ?? '';
    if (targetId.isEmpty) return;
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

  bool _showsCaptionOverlay(PostBaseDto post) {
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

  ImmersiveViewerStageLayoutSpec _layoutSpecForPost(PostBaseDto post) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  ImmersiveViewerStageLayoutSpec _engagementLayoutSpecForPost(
    PostBaseDto post,
  ) {
    if (_isArticleLikePost(post)) {
      return ImmersiveViewerStageLayoutSpec.articleStage;
    }
    if (_isTextOnlyMomentPost(post)) {
      return ImmersiveViewerStageLayoutSpec.textStage;
    }
    return ImmersiveViewerStageLayoutSpec.mediaStage;
  }

  double _statusBarContentInsetFor(PostBaseDto post) {
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

  bool _shouldMediaInvadeStatusBar(PostBaseDto post) {
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
      if (_expandedCaptionPostIds.contains(postId)) {
        _expandedCaptionPostIds.remove(postId);
      } else {
        _expandedCaptionPostIds.add(postId);
      }
    });
  }
}
