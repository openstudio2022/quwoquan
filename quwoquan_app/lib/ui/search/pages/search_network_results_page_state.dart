part of 'search_network_results_page.dart';

class _SearchNetworkResultsPageState
    extends ConsumerState<SearchNetworkResultsPage> {
  static const Duration _queryDebounce = Duration(milliseconds: 220);
  static const String _tabXiaoqu = SearchResultTabIds.xiaoqu;
  static const String _tabAll = SearchResultTabIds.all;
  static const String _tabIntersection = SearchResultTabIds.intersection;
  static const String _tabVideo = SearchResultTabIds.video;
  static const String _tabImage = SearchResultTabIds.image;
  static const String _tabArticle = SearchResultTabIds.article;

  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late String _query;
  late String _activeTabId;
  List<_SearchNetworkTab> _tabs = const [];
  Timer? _debounceTimer;
  int _requestToken = 0;
  bool _isLoading = false;
  UiErrorSemantic? _errorSemantic;
  AssistantSearchResultView? _xiaoquResult;
  List<PostSearchItemView> _contentResults = const <PostSearchItemView>[];
  List<SearchHit> _groupResults = const <SearchHit>[];
  List<SearchHit> _locationResults = const <SearchHit>[];
  // 云侧内容命中的排序/封面/理由元信息（按 postId 索引），由 [_contentItemsFromResponse]
  // 解析云侧 SearchHit 时填充；结果页据此消费 rankPosition/coverWidth/coverHeight/rankReasons
  // （R-001/R-003）。本地/mock 命中无云信号时为空，回退既有端侧渲染。
  Map<String, _ContentCloudMeta> _contentCloudMetaById =
      const <String, _ContentCloudMeta>{};
  // 云侧相关搜索词（relatedTerms）；非空时「相关搜索」卡优先消费，空则回退既有派生词。
  List<String> _relatedTerms = const <String>[];
  List<SearchDegradeSignal> _degradeSignals = const <SearchDegradeSignal>[];
  bool _showAllConnections = false;
  static const int _connectionCollapsedCap = 4;
  late final DateTime _pageEnteredAt;
  bool _didTrackPageImpression = false;
  ContentBehaviorTracker? _behaviorTracker;
  String? _feedRequestIdAtEnter;

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    _query = widget.launchContext.prefilledQuery.trim();
    _controller = TextEditingController(text: _query);
    _focusNode = FocusNode();
    _tabs = _buildBaseTabs();
    final initialTabId = _normalizeInitialTabId(
      widget.launchContext.initialNetworkTabId,
    );
    _activeTabId = _tabs.any((tab) => tab.id == initialTabId)
        ? initialTabId!
        : _tabAll;
    _scheduleRefresh(immediate: true);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _focusNode.requestFocus();
      _trackPageImpressionIfNeeded();
    });
  }

  @override
  void dispose() {
    _trackPageDwell();
    _debounceTimer?.cancel();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
  }

  void _trackPageImpressionIfNeeded() {
    if (_didTrackPageImpression) {
      return;
    }
    _didTrackPageImpression = true;
    _behaviorTracker = ref.read(contentBehaviorTrackerProvider);
    _feedRequestIdAtEnter = ref
        .read(feedSessionProvider.notifier)
        .currentFeedRequestId;
    _behaviorTracker!.trackImpression(
      'search_network_results',
      contentType: 'search_page',
      referralSource: ReferralSource.search,
      feedRequestId: _feedRequestIdAtEnter,
      tags: <String>[
        widget.launchContext.entrySurfaceId,
        _activeTabId,
        if (_query.trim().isNotEmpty) _query.trim(),
      ],
    );
  }

  void _trackPageDwell() {
    final tracker = _behaviorTracker;
    if (tracker == null) {
      return;
    }
    final elapsedSeconds =
        DateTime.now().difference(_pageEnteredAt).inMilliseconds / 1000.0;
    tracker.trackDwell(
      'search_network_results',
      durationSeconds: elapsedSeconds,
      contentType: 'search_page',
      referralSource: ReferralSource.search,
      feedRequestId: _feedRequestIdAtEnter,
      tags: <String>[
        widget.launchContext.entrySurfaceId,
        _activeTabId,
        if (_query.trim().isNotEmpty) _query.trim(),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final backgroundColor = SettingsSemanticConstants.pageBackground(isDark);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final activeTab = _tabs.firstWhere((tab) => tab.id == _activeTabId);

    return AppFullscreenModalSurface(
      backgroundColor: backgroundColor,
      safeAreaTop: false,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildSearchChrome(isDark, fgSecondary, backgroundColor),
          SizedBox(height: AppSpacing.containerSm),
          SecondaryCapsuleTabBar(
            isDark: isDark,
            tabs: _tabs.map((tab) => tab.label).toList(growable: false),
            activeIndex: _tabs.indexWhere((tab) => tab.id == _activeTabId),
            onTap: (index) {
              setState(() {
                _activeTabId = _tabs[index].id;
              });
              _scheduleRefresh(immediate: true);
            },
          ),
          SizedBox(height: AppSpacing.containerSm),
          Expanded(
            child: _errorSemantic != null && !_isLoading
                ? AppPageErrorState(
                    semantic: _errorSemantic!,
                    onAction: (action) async {
                      if (action.type == UiErrorActionType.retry ||
                          action.type == UiErrorActionType.resubmit) {
                        await _loadResults();
                      }
                    },
                  )
                : Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.containerMd,
                      0,
                      AppSpacing.containerMd,
                      AppSpacing.containerLg,
                    ),
                    child: ListView(
                      key: ValueKey<String>('network_results_$_activeTabId'),
                      padding: EdgeInsets.zero,
                      children: _buildResultChildren(
                        isDark: isDark,
                        fgSecondary: fgSecondary,
                        activeTab: activeTab,
                      ),
                    ),
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildSearchChrome(
    bool isDark,
    Color fgSecondary,
    Color backgroundColor,
  ) {
    final fieldBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final hasSearchText = _controller.text.trim().isNotEmpty;
    final topInset = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );
    return DecoratedBox(
      decoration: BoxDecoration(color: backgroundColor),
      child: Padding(
        padding: EdgeInsets.only(top: topInset),
        child: SizedBox(
          height: AppSpacing.appChromeTopBarHeight(context),
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.feedContentHorizontal(context),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(
                    AppSpacing.appChromeActionButtonSize,
                  ),
                  onPressed: _handleClose,
                  child: Icon(
                    CupertinoIcons.chevron_back,
                    color: fgSecondary,
                    size: AppSpacing.appChromeActionIconSize,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Expanded(
                  child: AppSearchField(
                    key: const ValueKey<String>('search_network_field'),
                    controller: _controller,
                    focusNode: _focusNode,
                    placeholder: UITextConstants.globalSearchTitle,
                    onSubmitted: _handleSearchSubmitted,
                    onChanged: (value) {
                      setState(() {
                        _query = value.trim();
                      });
                      _scheduleRefresh();
                    },
                    backgroundColor: fieldBackground,
                    elevated: false,
                    padding: EdgeInsetsDirectional.only(
                      start: AppSpacing.containerSm,
                      end: AppSpacing.containerSm,
                    ),
                  ),
                ),
                AnimatedSwitcher(
                  duration: const Duration(milliseconds: 160),
                  child: hasSearchText
                      ? Padding(
                          key: const ValueKey<String>(
                            'search_network_submit_visible',
                          ),
                          padding: EdgeInsetsDirectional.only(
                            start: AppSpacing.intraGroupXs,
                          ),
                          child: CupertinoButton(
                            key: const ValueKey<String>(
                              'search_network_submit_button',
                            ),
                            padding: EdgeInsets.symmetric(
                              horizontal: AppSpacing.containerXs,
                            ),
                            minimumSize: const Size(
                              0,
                              AppSpacing.appChromeTextActionMinHeight,
                            ),
                            onPressed: () =>
                                _handleSearchSubmitted(_controller.text),
                            child: Text(
                              UITextConstants.search,
                              style: TextStyle(
                                fontSize: AppTypography.iosSubheadline,
                                fontWeight: AppTypography.medium,
                                color: AppColors.primaryColor,
                              ),
                            ),
                          ),
                        )
                      : const SizedBox.shrink(
                          key: ValueKey<String>('search_network_submit_hidden'),
                        ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  List<_SearchNetworkTab> _buildBaseTabs() {
    return SearchResultTabSpec.fixedTabs
        .map(
          (tab) => _SearchNetworkTab(
            id: tab.id,
            label: tab.label,
            description: tab.description,
          ),
        )
        .toList(growable: false);
  }

  String? _normalizeInitialTabId(String? tabId) {
    return SearchResultTabSpec.normalizeInitialTabId(tabId);
  }

  bool get _hasRenderableResultsForActiveTab {
    if (_activeTabId == _tabIntersection) {
      return _groupResults.isNotEmpty ||
          _connectedGroupHits.isNotEmpty ||
          _discoveryGroupHits.isNotEmpty ||
          _contentResults.isNotEmpty ||
          _intersectionEntityHit != null ||
          _connectedLocations.isNotEmpty;
    }
    if (_activeTabId == _tabAll) {
      return _contentResults.isNotEmpty || _entityTopResult() != null;
    }
    return _contentResults.isNotEmpty;
  }

  List<SearchDegradeSignal> _mergeDegradeSignals(
    Iterable<SearchResponse> responses,
  ) {
    final seen = <String>{};
    final merged = <SearchDegradeSignal>[];
    for (final response in responses) {
      for (final signal in response.degradeSignals) {
        final key = '${signal.code}|${signal.objectType?.wireValue ?? ''}';
        if (seen.add(key)) {
          merged.add(signal);
        }
      }
    }
    return merged;
  }

  Widget? _buildDegradeBanner() {
    if (_degradeSignals.isEmpty || _hasRenderableResultsForActiveTab) {
      return null;
    }
    const friendlyMessage = UITextConstants.searchPartialGroupFailed;
    return AppTransientErrorNotice(
      semantic: UiErrorSemantic(
        category: UiErrorCategory.sectionLoad,
        scope: UiErrorScope.section,
        title: friendlyMessage,
        message: friendlyMessage,
        copyKey: 'searchPartialGroupFailed',
        presentation: UiErrorPresentation.transientNotice,
        tone: UiErrorTone.caution,
      ),
    );
  }

  List<Widget> _buildXiaoquCitationTiles({
    required bool isDark,
    required Color fgSecondary,
  }) {
    final citations =
        _xiaoquResult?.citations ?? const <AssistantSearchCitationView>[];
    return <Widget>[
      for (var i = 0; i < citations.length; i++) ...[
        PostPreviewListTile(
          isDark: isDark,
          title: citations[i].title,
          supportingText: citations[i].snippet ?? '打开相关线索',
          coverUrl: citations[i].coverUrl ?? '',
          eyebrowText:
              citations[i].badgeLabel ??
              citations[i].sourceDomain ??
              citations[i].objectType,
          showVideoBadge: citations[i].contentType == 'video',
          footer: Text(
            citations[i].sourceDomain ?? citations[i].objectType,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () {
            unawaited(_openAssistantCitation(citations[i]));
          },
        ),
        if (i != citations.length - 1) SizedBox(height: AppSpacing.containerSm),
      ],
    ];
  }

  List<Widget> _buildIntersectionGrid({required List<Widget> cells}) =>
      _buildAdaptiveMasonry(cells: cells);

  // 双列瀑布流：每个 cell 按自身内容高度排布，避免固定宽高比造成的卡片底部留白。
  List<Widget> _buildAdaptiveMasonry({required List<Widget> cells}) {
    if (cells.isEmpty) {
      return const <Widget>[];
    }
    return <Widget>[
      MasonryGridView.count(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        padding: EdgeInsets.zero,
        crossAxisCount: 2,
        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
        itemCount: cells.length,
        itemBuilder: (context, index) => cells[index],
      ),
    ];
  }

  // 发现更多交集：基于已有连接继续延展的结果，混入相关搜索卡。
  List<Widget> _discoverCells({required bool isDark}) {
    final models = _discoverCardModels();
    final cells = <Widget>[
      for (final model in models)
        _IntersectionCard(
          model: model,
          isDark: isDark,
          onTap: () => _openIntersectionTarget(model),
        ),
    ];
    final related = _buildRelatedSearchCard(isDark: isDark);
    if (related != null) {
      final insertAt = (cells.length / 2).floor();
      cells.insert(insertAt, related);
    }
    return cells;
  }

  List<_IntersectionCardModel> _discoverCardModels() {
    final models = <_IntersectionCardModel>[];
    for (final item in _discoveryContentItems) {
      final card = _NetworkResultCardModel.fromSearchItem(item);
      final isVideo = item.contentType == 'video';
      final isArticle = item.contentType == 'article';
      // §3：发现/交集线索区的交集句只来自云侧 primaryText；无 primaryText 不拼装。
      final intersectionSentence =
          item.intersectionReason?.primaryText.trim() ?? '';
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.post,
          targetId: item.postId,
          coverUrl: item.coverUrl ?? '',
          categoryLabel: isVideo ? '视频' : (isArticle ? '长文' : '图片'),
          categoryIcon: isVideo
              ? CupertinoIcons.play_rectangle_fill
              : (isArticle
                    ? CupertinoIcons.doc_text_fill
                    : CupertinoIcons.photo_fill),
          title: card.title,
          reasonIcon: CupertinoIcons.sparkles,
          reasonText: intersectionSentence,
          footerText: card.footerLabel,
          metricLabel: item.likeCount > 0 ? '${item.likeCount}' : null,
          metricIcon: CupertinoIcons.heart,
          showVideoBadge: isVideo,
        ),
      );
    }
    for (final hit in _discoveryGroupHits) {
      final card = _GroupResultCardModel.fromHit(hit);
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.circle,
          targetId: card.circleId,
          coverUrl: card.coverUrl,
          categoryLabel: '圈子',
          categoryIcon: CupertinoIcons.person_3_fill,
          title: hit.title,
          reasonIcon: CupertinoIcons.person_2_fill,
          reasonText: _hitIntersectionPrimaryText(hit),
          footerText: card.footerLabel,
        ),
      );
    }
    return models;
  }

  // 交集 Tab 顶部实体卡：只消费命中实体真实字段；连接说明只来自云侧 primaryText，
  // 无 primaryText 不展示句子，关注/内容计数不在端侧编造。
  _EntityTopResultModel? _intersectionEntityResult() {
    final hit = _intersectionEntityHit;
    if (hit == null) {
      return null;
    }
    final primaryText = _hitIntersectionPrimaryText(hit);
    return _EntityTopResultModel(
      homepageId: hit.objectId,
      title: hit.title,
      badge: '地点',
      subtitle: hit.subtitle ?? '地点主页',
      connectionReason: primaryText.isNotEmpty ? primaryText : null,
      description: hit.snippet ?? '',
      meta: '',
      actionLabel: '访问主页',
    );
  }

  void _openIntersectionTarget(_IntersectionCardModel model) {
    final id = model.targetId.trim();
    switch (model.targetType) {
      case _IntersectionTargetType.circle:
        if (id.isNotEmpty) {
          context.push(
            AppRoutePaths.circleDetail(id: id),
            extra: const CircleDetailPageRouteExtra(
              referralSource: ReferralSource.search,
            ),
          );
        }
      case _IntersectionTargetType.homepage:
        _openHomepage(id);
      case _IntersectionTargetType.locationPlace:
        _openLocationPlace(
          placeId: id,
          placeName: model.title,
          address: model.footerText,
        );
      case _IntersectionTargetType.post:
        unawaited(_openPost(id));
      case _IntersectionTargetType.user:
        if (id.isNotEmpty) {
          context.push(AppRoutePaths.userProfile(username: id));
        }
    }
  }

  void _openLocationPlace({
    required String placeId,
    required String placeName,
    required String address,
  }) {
    if (placeId.trim().isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.locationPlaceLanding(placeId: placeId),
      extra: LocationPlaceLandingPageRouteExtra(
        placeName: placeName,
        address: address,
        referralSource: ReferralSource.search,
      ),
    );
  }

  Widget? _buildRelatedSearchCard({required bool isDark}) {
    final terms = _relatedSearchTerms();
    if (terms.isEmpty) {
      return null;
    }
    return _RelatedSearchCard(
      card: RelatedSearchTermCardView(terms: terms).limited(),
      isDark: isDark,
      onTap: _submitRelatedSearch,
    );
  }

  List<NetworkSearchSuggestion> _relatedSearchTerms() {
    final query = _query.trim();
    if (query.isEmpty) {
      return const <NetworkSearchSuggestion>[];
    }
    // R-003：云侧 relatedTerms 非空时优先消费，缺失（本地/mock）才回退端侧派生词。
    if (_relatedTerms.isNotEmpty) {
      final seen = <String>{};
      final cloud = <NetworkSearchSuggestion>[];
      for (final term in _relatedTerms) {
        final trimmed = term.trim();
        if (trimmed.isEmpty || !seen.add(trimmed.toLowerCase())) {
          continue;
        }
        cloud.add(NetworkSearchSuggestion(query: trimmed, title: trimmed));
      }
      if (cloud.isNotEmpty) {
        return cloud;
      }
    }
    final seeds = <String>[
      '$query 攻略',
      '$query 拍照机位',
      '$query 交集',
      '$query 圈子',
      '$query 长文',
    ];
    final seen = <String>{};
    return seeds
        .where((item) => seen.add(item.toLowerCase()))
        .map((item) => NetworkSearchSuggestion(query: item, title: item))
        .toList(growable: false);
  }

  void _submitRelatedSearch(NetworkSearchSuggestion term) {
    final nextQuery = term.query.trim();
    if (nextQuery.isEmpty) {
      return;
    }
    setState(() {
      _query = nextQuery;
      _controller.text = nextQuery;
      _activeTabId = _tabAll;
    });
    _scheduleRefresh(immediate: true);
  }

  void _scheduleRefresh({bool immediate = false}) {
    _debounceTimer?.cancel();
    if (immediate) {
      unawaited(_loadResults());
      return;
    }
    _debounceTimer = Timer(_queryDebounce, () => unawaited(_loadResults()));
  }

  Future<SearchResponse> _guardedSearchResponse(
    Future<SearchResponse> future,
  ) async {
    try {
      return await future;
    } catch (error) {
      return SearchResponse(
        request: SearchRequest(query: _query.trim(), mode: SearchMode.result),
        sections: const <SearchSection>[],
        degradeSignals: <SearchDegradeSignal>[
          SearchDegradeSignal(
            code: '',
            message: UITextConstants.searchPartialGroupFailed,
          ),
        ],
      );
    }
  }

  Future<SearchResponse> _loadContentResponse(String query) async {
    final selection = widget.launchContext.searchObjectSelection.normalized();
    final contentTypes = switch (_activeTabId) {
      _tabVideo => const <SearchContentTypeFilter>{
        SearchContentTypeFilter.video,
      },
      _tabImage => const <SearchContentTypeFilter>{
        SearchContentTypeFilter.image,
      },
      _tabArticle => const <SearchContentTypeFilter>{
        SearchContentTypeFilter.article,
      },
      _ => selection.contentTypes,
    };
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{SearchObjectType.contentPost},
            limit: 12,
            contentTypes: contentTypes,
          ),
        );
  }

  Iterable<SearchHit> _hitsFromResponse(SearchResponse response) {
    if (response.hits.isNotEmpty) {
      return response.hits;
    }
    return response.sections.expand((section) => section.hits);
  }

  List<SearchHit> get _connectedGroupHits => _groupResults
      .where((hit) => _hitConnectionState(hit) == 'connected')
      .toList(growable: false);

  List<SearchHit> get _discoveryGroupHits => _groupResults
      .where((hit) => _hitConnectionState(hit) != 'connected')
      .toList(growable: false);

  // 命中实体置顶卡：只取云侧 entity.homepage（绑定实体主页），按搜索词标题匹配；
  // 一方地点 location.place 不进顶卡（落地体验见 _connectedLocations 与 location 落地页）。
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
              _hitConnectionState(hit) == 'connected',
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

  // 任意对象 hit 的连接态（content 走 PostSearchItemView，其余对象走 payload 透传）。
  static String _hitConnectionState(SearchHit hit) {
    final raw = hit.payload.toWireMap()['connectionState'];
    final state = raw?.toString().trim() ?? '';
    return state.isEmpty ? 'unconnected' : state;
  }

  // 云侧交集结论句（G2 端只读 primaryText，不回退 displayText/label，不本地拼装）。
  static String _hitIntersectionPrimaryText(SearchHit hit) {
    final reason = hit.payload.toWireMap()['intersectionReason'];
    if (reason is Map) {
      return reason['primaryText']?.toString().trim() ?? '';
    }
    return '';
  }

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
        badge: '实体主页',
        subtitle: hit.subtitle ?? '地点',
        description: hit.snippet ?? '打开主页查看介绍',
        meta: _entityMetaFromHit(hit),
      );
    }
    return null;
  }

  static String _entityMetaFromHit(SearchHit hit) {
    final payload = hit.payload.toWireMap();
    final followerCount = payload['followerCount'] ?? payload['followCount'];
    final contentCount = payload['contentCount'] ?? payload['postCount'];
    final parts = <String>[];
    if (followerCount is num && followerCount > 0) {
      parts.add('${_formatCompactCount(followerCount)}关注');
    }
    if (contentCount is num && contentCount > 0) {
      parts.add('${_formatCompactCount(contentCount)}内容');
    }
    return parts.join(' · ');
  }

  static String _formatCompactCount(num value) {
    if (value >= 10000) {
      return '${(value / 10000).toStringAsFixed(1)}万';
    }
    return value.toInt().toString();
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
      _tabImage =>
        _contentResults
            .where(
              (item) => item.contentType == 'image',
            )
            .toList(growable: false),
      _tabVideo =>
        _contentResults
            .where((item) => item.contentType == 'video')
            .toList(growable: false),
      _tabArticle =>
        _contentResults
            .where((item) => item.contentType == 'article')
            .toList(growable: false),
      _ => _contentResults,
    };
  }

  Future<SearchResponse> _loadGroupResponse(String query) {
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{
              SearchObjectType.circleGroup,
              SearchObjectType.circleCircle,
            },
            limit: 12,
          ),
        );
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

  // 实体顶卡 + 一方地点单源：消费云侧第一方对象 entity.homepage（已绑定实体主页）与
  // location.place（被内容引用但未绑定主页的自由文本地点，R-S05e）。不再走
  // integration.location_poi —— 后者是发布选点用的三方实时 POI，由默认搜索页 suggest 承接。
  Future<SearchResponse> _loadLocationResponse(String query) {
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{
              SearchObjectType.entityHomepage,
              SearchObjectType.locationPlace,
            },
            limit: 12,
          ),
        );
  }

  List<SearchHit> _locationHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.entityHomepage ||
              hit.objectType == SearchObjectType.locationPlace,
        )
        .toList(growable: false);
  }

  Future<void> _showOpenPostFailure(Object error) async {
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
        title: UITextConstants.workOpenFailedTitle,
        message: resolved.message,
        secondaryMessage: resolved.secondaryMessage,
        primaryAction:
            resolved.primaryAction ??
            const UiErrorAction(
              type: UiErrorActionType.dismiss,
              label: UITextConstants.confirm,
            ),
        secondaryAction: resolved.secondaryAction,
        dismissible: true,
        sourceCode: resolved.sourceCode,
        failureKind: resolved.failureKind,
        copyKey: 'workOpenFailedTitle',
        recoveryAction: resolved.recoveryAction,
      ),
    );
  }

  void _openHomepage(String homepageId) {
    if (homepageId.trim().isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.homepageDetail(id: homepageId),
      extra: const HomepageDetailPageRouteExtra(
        referralSource: ReferralSource.search,
      ),
    );
  }

  Future<void> _openAssistantCitation(
    AssistantSearchCitationView citation,
  ) async {
    switch (citation.objectType) {
      case 'circle':
        if (citation.objectId.isNotEmpty) {
          context.push(AppRoutePaths.circleDetail(id: citation.objectId));
        }
        return;
      case 'conversation':
        if (citation.objectId.isNotEmpty) {
          context.push(AppRoutePaths.chatDetail(id: citation.objectId));
        }
        return;
      case 'post':
      default:
        if (citation.objectId.isNotEmpty) {
          await _openPost(citation.objectId);
        }
        return;
    }
  }

  void _handleSearchSubmitted(String value) {
    setState(() {
      _query = value.trim();
    });
    _scheduleRefresh(immediate: true);
  }

  void _handleClose() {
    if (context.canPop()) {
      context.pop();
      return;
    }
    context.go(AppRoutePaths.globalSearch);
  }
}
