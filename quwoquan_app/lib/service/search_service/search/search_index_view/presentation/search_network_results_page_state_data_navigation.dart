part of 'search_network_results_page.dart';

extension _SearchNetworkResultsPageStateDataNavigation
    on _SearchNetworkResultsPageState {
  Iterable<SearchHit> _hitsFromResponse(SearchResponse response) {
    if (response.hits.isNotEmpty) {
      return response.hits;
    }
    return response.sections.expand((section) => section.hits);
  }

  List<SearchHit> get _connectedGroupHits => _groupResults
      .where(
        (hit) =>
            _SearchNetworkResultsPageState._hitConnectionState(hit) ==
            'connected',
      )
      .toList(growable: false);

  List<SearchHit> get _discoveryGroupHits => _groupResults
      .where(
        (hit) =>
            _SearchNetworkResultsPageState._hitConnectionState(hit) !=
            'connected',
      )
      .toList(growable: false);

  List<SearchHit> get _connectedUserHits => _userResults
      .where(
        (hit) =>
            _SearchNetworkResultsPageState._hitConnectionState(hit) ==
            'connected',
      )
      .toList(growable: false);

  List<SearchHit> get _discoveryUserHits => _userResults
      .where(
        (hit) =>
            _SearchNetworkResultsPageState._hitConnectionState(hit) !=
            'connected',
      )
      .toList(growable: false);

  // 命中实体置顶卡：只取云侧 entity.homepage（绑定实体主页），按搜索词标题匹配。
  SearchHit? get _intersectionEntityHit {
    final query = _query.trim();
    for (final hit in _locationResults) {
      if (hit.objectType == SearchObjectType.entityHomepage &&
          _entityTitleMatchesQuery(hit.title, query)) {
        return hit;
      }
    }
    return null;
  }

  // 已连接的一方地点（location.place 且 connectionState=connected）。实体顶卡走
  // entity.homepage（见 _intersectionEntityHit），与此处 location.place 互不重叠。
  List<SearchHit> get _connectedLocations {
    return _locationResults
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.locationPlace &&
              _SearchNetworkResultsPageState._hitConnectionState(hit) ==
                  'connected',
        )
        .toList(growable: false);
  }

  // 连接态分组（§3）：唯一真相源是云侧 connectionState 闭集（connected /
  // unconnected / intersection_lead）。已连接进「已形成的连接」，未连接 + 交集线索
  // 进「发现更多交集」；端不再用 take/skip 位置启发式伪造分组。
  List<PostSearchItemView> get _connectedContentItems => _contentResults
      .where((item) => item.connectionState == 'connected')
      .toList(growable: false);

  List<PostSearchItemView> get _discoveryContentItems => _contentResults
      .where((item) => item.connectionState != 'connected')
      .toList(growable: false);

  _EntityTopResultModel? _entityTopResult() {
    final query = _query.trim();
    for (final hit in _locationResults) {
      if (hit.objectType != SearchObjectType.entityHomepage) {
        continue;
      }
      if (!_entityTitleMatchesQuery(hit.title, query)) {
        continue;
      }
      return _EntityTopResultModel(
        homepageId: hit.objectId,
        title: hit.title,
        badge: SearchText.searchEntityHomepage,
        subtitle: hit.subtitle ?? SearchText.searchCategoryLocation,
        description: hit.snippet ?? SearchText.searchOpenHomepageDescription,
        meta: _SearchNetworkResultsPageState._entityMetaFromHit(hit),
      );
    }
    return null;
  }

  _LocationPlaceTopResultModel? _locationPlaceTopResult() {
    final query = _query.trim();
    for (final hit in _locationResults) {
      final place = hit.asLocationPlaceItem;
      if (place == null || !_entityTitleMatchesQuery(place.name, query)) {
        continue;
      }
      return _LocationPlaceTopResultModel(place: place);
    }
    return null;
  }

  bool _entityTitleMatchesQuery(String title, String query) {
    final normalizedTitle = title.trim().toLowerCase();
    final normalizedQuery = query.trim().toLowerCase();
    if (normalizedTitle.isEmpty || normalizedQuery.isEmpty) {
      return false;
    }
    return normalizedTitle.contains(normalizedQuery) ||
        normalizedQuery.contains(normalizedTitle);
  }

  List<PostSearchItemView> _contentItemsForActiveTab() {
    return switch (_activeTabId) {
      _SearchNetworkResultsPageState._tabImage =>
        _contentResults
            .where((item) => item.contentType == 'image')
            .toList(growable: false),
      _SearchNetworkResultsPageState._tabVideo =>
        _contentResults
            .where((item) => item.contentType == 'video')
            .toList(growable: false),
      _SearchNetworkResultsPageState._tabArticle =>
        _contentResults
            .where((item) => item.contentType == 'article')
            .toList(growable: false),
      _ => _contentResults,
    };
  }

  List<SearchHit> _groupHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.circleGroup ||
              hit.objectType == SearchObjectType.circleCircle,
        )
        .toList(growable: false);
  }

  List<SearchHit> _userHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where((hit) => hit.objectType == SearchObjectType.userProfile)
        .toList(growable: false);
  }

  // 实体顶卡 + 一方地点单源：消费云侧第一方对象 entity.homepage（已绑定实体主页）与
  // location.place（被内容引用但未绑定主页的自由文本地点，R-S05e）。不再走
  // integration.location_poi —— 后者是发布选点用的三方实时 POI，由默认搜索页 suggest 承接。
  List<SearchHit> _locationHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.entityHomepage ||
              hit.objectType == SearchObjectType.locationPlace,
        )
        .toList(growable: false);
  }

  Future<void> _showOpenPostFailure(
    Object error, {
    bool unavailableSearchResult = false,
  }) async {
    if (!mounted) {
      return;
    }
    final resolved = runtimeErrorSemantic(
      context,
      error: error,
      category: UiErrorCategory.submit,
      scope: UiErrorScope.global,
    );
    await AppActionErrorFeedback.show(
      context,
      semantic: UiErrorSemantic(
        category: resolved.category,
        scope: resolved.scope,
        title: unavailableSearchResult
            ? SearchText.searchResultUnavailableTitle
            : ContentText.workOpenFailedTitle,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction:
            resolved.primaryAction ??
            const UiErrorAction(
              type: UiErrorActionType.dismiss,
              label: FoundationText.confirm,
            ),
        secondaryAction: resolved.secondaryAction,
        dismissible: true,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        copyKey: unavailableSearchResult
            ? 'searchResultUnavailableTitle'
            : 'workOpenFailedTitle',
        recoveryAction: resolved.recoveryAction,
      ),
    );
  }

  bool _isUnavailableSearchContent(Object error) {
    final failure = runtimeFailureFromError(error);
    if (failure == null) {
      return false;
    }
    return switch (ContentErrorCode.fromCode(failure.code)) {
      ContentErrorCode.postNotFound || ContentErrorCode.contentDeleted => true,
      _ => false,
    };
  }

  void _removeUnavailableSearchContent(String postId) {
    if (!mounted) {
      return;
    }
    final nextCloudMeta = Map<String, _ContentCloudMeta>.of(
      _contentCloudMetaById,
    )..remove(postId);
    final nextRanks = Map<String, int>.of(_searchRankByObjectId)
      ..remove(postId);
    _setState(() {
      _contentResults = _contentResults
          .where((item) => item.postId != postId)
          .toList(growable: false);
      _contentCloudMetaById = Map<String, _ContentCloudMeta>.unmodifiable(
        nextCloudMeta,
      );
      _searchRankByObjectId = Map<String, int>.unmodifiable(nextRanks);
    });
  }

  void _openHomepage(String homepageId) {
    if (homepageId.trim().isEmpty) {
      return;
    }
    _reportSearchClick(
      objectId: homepageId,
      target: 'homepages',
      objectType: SearchObjectType.entityHomepage,
    );
    context.push(
      AppRoutePaths.homepageDetail(id: homepageId),
      extra: const HomepageDetailPageRouteExtra(
        referralSource: ReferralSource.search,
      ),
    );
  }

  Future<void> _openAssistantCitation(
    AssistantRunVisibleReferenceView citation,
  ) async {
    final destination = CitationDestinationResolver.resolve(
      citation.destination,
    );
    switch (destination) {
      case InternalCitationDestination():
        final navigationTarget =
            CitationDestinationNavigationMapper.resolveInternal(destination);
        if (navigationTarget == null) {
          return;
        }
        context.push(navigationTarget.routePath);
      case ExternalCitationDestination():
        await launchUrl(destination.uri, mode: LaunchMode.externalApplication);
      case null:
        // 未知对象、无链接与非法 URL 均 fail-closed，绝不回退打开 post。
        return;
    }
  }

  void _handleSearchSubmitted(String value) {
    final nextQuery = value.trim();
    if (nextQuery != _query.trim()) {
      _reportSearchRefine(action: 'query_resubmit');
    }
    _setState(() {
      _query = nextQuery;
    });
    _scheduleRefresh(immediate: true);
  }

  void _editEmptySearchQuery() {
    _controller
      ..clear()
      ..selection = const TextSelection.collapsed(offset: 0);
    _setState(() {
      _query = '';
    });
    _focusNode.requestFocus();
  }

  void _handleClose() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.globalSearch);
  }

  void _openUserProfile(SearchHit hit) {
    final userID = hit.asUserProfileItem?.userId.trim() ?? hit.objectId.trim();
    if (userID.isEmpty) {
      return;
    }
    _reportSearchClick(
      objectId: userID,
      target: 'users',
      objectType: SearchObjectType.userProfile,
    );
    context.push(AppRoutePaths.userProfile(userHandle: userID));
  }

  Future<void> _openPost(String postId) async {
    if (postId.trim().isEmpty) {
      return;
    }
    _reportSearchClick(
      objectId: postId,
      target: 'posts',
      objectType: SearchObjectType.contentPost,
    );
    try {
      final detail = await ref
          .read(globalSearchContentPostDetailReaderProvider)
          .getPost(postId: postId);
      applyConfirmedInteractionPost(ref, detail.post);
      if (!mounted) {
        return;
      }
      final dto = detail.post;
      final raw = detail.mergedArticleWireMap;
      final interactionSnapshot = buildMediaViewerInteractionSnapshot(
        posts: <ContentPostViewData>[dto],
        discoveryState: ref.read(discoveryStateProvider),
        relationshipState: ref.read(userRelationshipStateProvider),
        postInteractionState: ref.read(postInteractionStateProvider),
      );
      primeMediaViewerInteractionSnapshot(ref, interactionSnapshot);
      final navFeedRequestId = ref
          .read(feedSessionProvider.notifier)
          .newFeedRequestId();
      final result = await context.push<Object?>(
        AppRoutePaths.workBrowser(
          workId: dto.id,
          filter: dto.isVideoLike
              ? 'video'
              : (dto.isArticleLike ? 'article' : 'image'),
          source: 'global-search-network',
          index: '0',
        ),
        extra: MediaViewerExtra(
          posts: <ContentSurfaceView>[
            ContentSurfaceViewMapper.fromDto(dto, wire: raw),
          ],
          dtoPosts: <ContentPostViewData>[dto],
          initialIndex: 0,
          source: 'global-search-network',
          rawPostsById: searchNetworkSinglePostMediaRaws(dto: dto, wire: raw),
          interactionSnapshot: interactionSnapshot,
          referralSource: ReferralSource.search,
          feedRequestId: navFeedRequestId,
        ),
      );
      if (result is MediaViewerResult) {
        applyMediaViewerResultToInteractionState(ref, result);
      }
    } catch (error) {
      final unavailableSearchResult = _isUnavailableSearchContent(error);
      if (unavailableSearchResult) {
        _reportSearchDegrade(objectId: postId, target: 'posts');
        _removeUnavailableSearchContent(postId);
      }
      await _showOpenPostFailure(
        error,
        unavailableSearchResult: unavailableSearchResult,
      );
    }
  }
}
