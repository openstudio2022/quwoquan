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
  bool _isSlow = false;
  final AppRequestWaitController _waitController = AppRequestWaitController();
  UiErrorSemantic? _errorSemantic;
  AssistantSearchResultView? _xiaoquResult;
  List<PostSearchItemView> _contentResults = const <PostSearchItemView>[];
  List<SearchHit> _userResults = const <SearchHit>[];
  List<SearchHit> _groupResults = const <SearchHit>[];
  List<SearchHit> _locationResults = const <SearchHit>[];
  // 云侧内容命中的排序/封面/理由元信息（按 postId 索引），由 [_contentItemsFromResponse]
  // 解析云侧 SearchHit 时填充；结果页据此消费 rankPosition/coverWidth/coverHeight/rankReasons
  // （R-001/R-003）。本地/mock 命中无云信号时为空，回退既有端侧渲染。
  Map<String, _ContentCloudMeta> _contentCloudMetaById =
      const <String, _ContentCloudMeta>{};
  // relatedTerms 只消费 search-service 响应，空时不在客户端合成业务词。
  List<String> _relatedTerms = const <String>[];
  List<SearchDegradeSignal> _degradeSignals = const <SearchDegradeSignal>[];
  bool _showAllConnections = false;
  static const int _connectionCollapsedCap = 4;
  late final DateTime _pageEnteredAt;
  bool _didTrackPageImpression = false;
  ContentBehaviorTracker? _behaviorTracker;
  String? _feedRequestIdAtEnter;
  // 搜索反馈归因锚点：云响应 envelope 的 requestId + 条目位次映射。
  // 本地/mock 扇出无 requestId 时不上报（fail-closed，不合成伪 id）。
  String? _searchRequestId;
  final Set<String> _searchImpressionReported = <String>{};
  Map<String, int> _searchRankByObjectId = const <String, int>{};
  late final AppTelemetryRecorder _appTelemetry;
  final Set<String> _searchTelemetrySubmitted = <String>{};
  String? _telemetryResultRequestId;
  DateTime? _telemetryResultShownAt;
  int _telemetryResultCount = 0;
  String? _telemetryResultAction;

  void _setMountedState(VoidCallback update) {
    if (!mounted) {
      return;
    }
    setState(update);
  }

  void _setState(VoidCallback update) {
    setState(update);
  }

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    _appTelemetry = ref.read(appTelemetryReporterProvider);
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
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _scheduleRefresh(immediate: true);
      _focusNode.requestFocus();
      _trackPageImpressionIfNeeded();
    });
  }

  @override
  void dispose() {
    _recordSearchResultDwellIfNeeded();
    _trackPageDwell();
    _debounceTimer?.cancel();
    _requestToken += 1;
    _waitController.dispose();
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

  /// 查询级 impression：一次云搜索响应渲染完成上报一次（同 requestId 去重）。
  void _reportSearchImpression(SearchResponse response) {
    final requestId = response.searchRequestId;
    if (requestId == null || !_searchImpressionReported.add(requestId)) {
      return;
    }
    _reportSearchFeedbackEvent(requestId: requestId, eventType: 'impression');
  }

  /// 条目 click 反馈（携带 rankPosition 归因）；fire-and-forget 不阻断跳转。
  void _reportSearchClick({
    required String objectId,
    required String target,
    required SearchObjectType objectType,
  }) {
    final requestId = _searchRequestId;
    if (requestId == null || objectId.trim().isEmpty) {
      return;
    }
    _reportSearchFeedbackEvent(
      requestId: requestId,
      eventType: 'click',
      objectId: objectId,
      target: target,
    );
    final rankPosition = _searchRankByObjectId[objectId];
    if (rankPosition != null) {
      _recordSearchTelemetry(
        AppTelemetryPayload.searchResultClick(
          requestId: requestId,
          objectType: objectType.wireValue,
          rankPosition: rankPosition,
          action: _activeTabId,
        ),
      );
    }
  }

  void _reportSearchRefine({required String action}) {
    final requestId = _searchRequestId;
    if (requestId == null || action.trim().isEmpty) {
      return;
    }
    _reportSearchFeedbackEvent(requestId: requestId, eventType: 'refine');
    _recordSearchTelemetry(
      AppTelemetryPayload.searchRefine(
        requestId: requestId,
        action: action.trim(),
      ),
    );
  }

  /// 命中已过期或已删除时记录 degrade，供搜索索引新鲜度 SLI 归因。
  void _reportSearchDegrade({
    required String objectId,
    required String target,
  }) {
    final requestId = _searchRequestId;
    if (requestId == null || objectId.trim().isEmpty) {
      return;
    }
    _reportSearchFeedbackEvent(
      requestId: requestId,
      eventType: 'degrade',
      objectId: objectId,
      target: target,
    );
  }

  void _reportSearchFeedbackEvent({
    required String requestId,
    required String eventType,
    String? objectId,
    String? target,
  }) {
    unawaited(
      ref
          .read(searchFeedbackCommandWriterProvider)
          .reportSearchFeedback(
            ReportSearchFeedbackCommand(
              searchRequestId: requestId,
              eventType: eventType,
              objectId: objectId,
              target: target,
              rankPosition: objectId == null
                  ? null
                  : _searchRankByObjectId[objectId],
              referralSource: ReferralSource.search.value,
              feedRequestId: _feedRequestIdAtEnter,
            ),
          )
          .catchError((Object error) {
            if (kDebugMode) {
              debugPrint('search $eventType feedback degraded: $error');
            }
            return const SearchFeedbackAck(accepted: false);
          }),
    );
  }

  void _recordSearchResponseTelemetry({
    required SearchResponse response,
    required DateTime submittedAt,
    required int durationMs,
    required String action,
  }) {
    final requestId = response.searchRequestId?.trim();
    if (requestId == null ||
        requestId.isEmpty ||
        !_searchTelemetrySubmitted.add(requestId)) {
      return;
    }
    final resultCount = _hitsFromResponse(response).length;
    _recordSearchTelemetry(
      AppTelemetryPayload.searchQuerySubmit(
        requestId: requestId,
        surfaceId: AppUiSurfaces.globalSearchNetworkResults.id,
        action: action,
      ),
      occurredAt: submittedAt,
    );
    if (resultCount == 0) {
      _recordSearchTelemetry(
        AppTelemetryPayload.searchZeroResult(
          requestId: requestId,
          durationMs: durationMs,
          action: action,
        ),
      );
      return;
    }
    _recordSearchTelemetry(
      AppTelemetryPayload.searchResultImpression(
        requestId: requestId,
        resultCount: resultCount,
        durationMs: durationMs,
        action: action,
      ),
    );
    _telemetryResultRequestId = requestId;
    _telemetryResultShownAt = DateTime.now();
    _telemetryResultCount = resultCount;
    _telemetryResultAction = action;
  }

  void _recordSearchResultDwellIfNeeded() {
    final requestId = _telemetryResultRequestId;
    final shownAt = _telemetryResultShownAt;
    if (requestId == null || shownAt == null || _telemetryResultCount <= 0) {
      return;
    }
    final elapsed = DateTime.now().difference(shownAt).inMilliseconds;
    final resultCount = _telemetryResultCount;
    final action = _telemetryResultAction;
    _telemetryResultRequestId = null;
    _telemetryResultShownAt = null;
    _telemetryResultCount = 0;
    _telemetryResultAction = null;
    _recordSearchTelemetry(
      AppTelemetryPayload.searchResultDwell(
        requestId: requestId,
        durationMs: elapsed < 0 ? 0 : elapsed,
        resultCount: resultCount,
        action: action,
      ),
    );
  }

  void _recordSearchTelemetry(
    AppTelemetryPayload payload, {
    DateTime? occurredAt,
  }) {
    unawaited(
      _appTelemetry
          .record(
            payload,
            pageName: PageNames.globalSearchNetwork,
            occurredAt: occurredAt,
          )
          .catchError((Object error) {
            if (kDebugMode) {
              debugPrint(
                'search telemetry ${payload.eventType} degraded: $error',
              );
            }
            return AppTelemetryRecordResult.rejected;
          }),
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
              final nextTabId = _tabs[index].id;
              if (nextTabId != _activeTabId) {
                _reportSearchRefine(action: 'tab:$nextTabId');
              }
              setState(() {
                _activeTabId = nextTabId;
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

  // 连接态由 canonical SearchHit 强类型字段单源承载。
  static String _hitConnectionState(SearchHit hit) {
    final state = hit.connectionState.trim();
    return state.isEmpty ? 'unconnected' : state;
  }

  // 云侧交集结论句（G2 端只读 primaryText，不回退 displayText/label，不本地拼装）。
  static String _contentIntersectionPrimaryText(PostSearchItemView item) {
    final reason = item.intersectionReason;
    if (reason == null) {
      return '';
    }
    final displayReason = displayReadyIntersectionReason(
      reason,
      contextObjectTarget: IntersectionTarget(
        objectType: 'post',
        objectId: item.postId,
        objectKind: 'content',
        routeId: 'workBrowser',
      ),
    );
    return displayReason?.primaryText.trim() ?? '';
  }

  static String _hitIntersectionPrimaryText(SearchHit hit) {
    final reason = hit.intersectionReason;
    if (reason == null) {
      return '';
    }
    final displayReason = displayReadyIntersectionReason(
      reason,
      contextObjectTarget: _searchHitContextTarget(hit),
    );
    return displayReason?.primaryText.trim() ?? '';
  }

  static IntersectionTarget? _searchHitContextTarget(SearchHit hit) {
    final id = hit.objectId.trim();
    if (id.isEmpty) {
      return null;
    }
    switch (hit.objectType) {
      case SearchObjectType.contentPost:
        return IntersectionTarget(
          objectType: 'post',
          objectId: id,
          objectKind: 'content',
          routeId: 'workBrowser',
        );
      case SearchObjectType.circleCircle:
        return IntersectionTarget(
          objectType: 'circle',
          objectId: id,
          objectKind: 'circle',
          routeId: 'circleDetail',
        );
      case SearchObjectType.entityHomepage:
      case SearchObjectType.locationPlace:
      case SearchObjectType.integrationLocationPoi:
        return IntersectionTarget(
          objectType: 'homepage',
          objectId: id,
          objectKind: 'place',
          routeId: 'homepageDetail',
        );
      case SearchObjectType.userProfile:
        return IntersectionTarget(
          objectType: 'user',
          objectId: id,
          objectKind: 'person',
          routeId: 'userProfile',
        );
      case SearchObjectType.webDocument:
      case SearchObjectType.chatContact:
      case SearchObjectType.chatConversation:
      case SearchObjectType.chatMessage:
      case SearchObjectType.circleGroup:
      case SearchObjectType.tag:
        return null;
    }
  }

  static String _entityMetaFromHit(SearchHit hit) {
    final item = hit.asEntityHomepageItem;
    final followerCount = item?.followerCount ?? 0;
    final contentCount = item?.contentCount ?? 0;
    final parts = <String>[];
    if (followerCount > 0) {
      parts.add(
        UITextConstants.searchFollowerCount(_formatCompactCount(followerCount)),
      );
    }
    if (contentCount > 0) {
      parts.add(
        UITextConstants.searchContentCount(_formatCompactCount(contentCount)),
      );
    }
    return parts.join(' · ');
  }

  static String _formatCompactCount(num value) {
    if (value >= 10000) {
      return UITextConstants.searchTenThousands(value / 10000);
    }
    return value.toInt().toString();
  }
}
