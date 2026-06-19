import 'dart:async';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/ui/entity/models/homepage_route_models.dart';
import 'package:quwoquan_app/ui/content/models/content_route_models.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/search/models/search_result_tab_spec.dart';
import 'package:quwoquan_app/ui/search/pages/location_place_landing_page.dart';
import 'package:quwoquan_app/ui/search/services/search_network_results_media_wiring.dart';

class _SearchResultTokens {
  _SearchResultTokens._();

  static const double sectionTitleSize = AppTypography.iosBody;
  static const FontWeight sectionTitleWeight = AppTypography.semiBold;
  static const double bodySize = AppTypography.iosCallout;
  static const FontWeight bodyWeight = AppTypography.regular;
  static const double cardTitleSize = AppTypography.iosFootnote;
  static const double captionSize = AppTypography.iosCaption1;
}

class SearchNetworkResultsPage extends ConsumerStatefulWidget {
  const SearchNetworkResultsPage({super.key, required this.launchContext});

  final SearchLaunchContext launchContext;

  @override
  ConsumerState<SearchNetworkResultsPage> createState() =>
      _SearchNetworkResultsPageState();
}

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
    _feedRequestIdAtEnter =
        ref.read(feedSessionProvider.notifier).currentFeedRequestId;
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

  List<Widget> _buildResultChildren({
    required bool isDark,
    required Color fgSecondary,
    required _SearchNetworkTab activeTab,
  }) {
    List<Widget> withDegradeBanner(List<Widget> children) {
      final banner = _buildDegradeBanner();
      if (banner == null) {
        return children;
      }
      return <Widget>[
        banner,
        SizedBox(height: AppSpacing.containerMd),
        ...children,
      ];
    }

    if (_activeTabId == _tabXiaoqu) {
      return <Widget>[
        _XiaoquSummaryCard(
          query: _query,
          result: _xiaoquResult,
          isDark: isDark,
        ),
        SizedBox(height: AppSpacing.containerMd),
        if (_isLoading)
          _StatusMessage(text: '小趣正在整理搜索方向', isDark: isDark, loading: true)
        else if ((_xiaoquResult?.citations?.length ?? 0) == 0)
          _StatusMessage(text: '暂时没有找到可引用的网络结果', isDark: isDark)
        else
          ..._buildXiaoquCitationTiles(
            isDark: isDark,
            fgSecondary: fgSecondary,
          ),
      ];
    }

    if (_activeTabId == _tabAll) {
      return withDegradeBanner(
        _buildAllResultChildren(
          isDark: isDark,
          fgSecondary: fgSecondary,
          activeTab: activeTab,
        ),
      );
    }

    if (_activeTabId == _tabIntersection) {
      return withDegradeBanner(
        _buildIntersectionResultChildren(
          isDark: isDark,
          fgSecondary: fgSecondary,
        ),
      );
    }

    final contentItems = _contentItemsForActiveTab();
    return withDegradeBanner(<Widget>[
      if (_isLoading)
        _StatusMessage(
          text: '正在加载${activeTab.label}结果',
          isDark: isDark,
          loading: true,
        )
      else if (contentItems.isEmpty)
        _StatusMessage(text: '没有找到相关${activeTab.label}结果', isDark: isDark)
      else
        ..._buildContentMasonryTiles(
          isDark: isDark,
          fgSecondary: fgSecondary,
          items: contentItems,
          relatedSearchCard: _buildRelatedSearchCard(isDark: isDark),
        ),
    ]);
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
    final message = _degradeSignals
        .map((signal) => signal.message.trim())
        .firstWhere(
          (value) => value.isNotEmpty,
          orElse: () => '部分结果暂时不可用，请稍后重试。',
        );
    return AppTransientErrorNotice(
      semantic: UiErrorSemantic(
        category: UiErrorCategory.sectionLoad,
        scope: UiErrorScope.section,
        title: message,
        message: message,
        presentation: UiErrorPresentation.transientNotice,
        tone: UiErrorTone.caution,
      ),
    );
  }

  List<Widget> _buildAllResultChildren({
    required bool isDark,
    required Color fgSecondary,
    required _SearchNetworkTab activeTab,
  }) {
    if (_isLoading) {
      return <Widget>[
        _StatusMessage(text: '正在加载应用内结果', isDark: isDark, loading: true),
      ];
    }

    final sections = <Widget>[];
    final entity = _entityTopResult();
    if (entity != null) {
      sections.add(
        _EntityTopResultCard(
          entity: entity,
          isDark: isDark,
          onTap: () => _openHomepage(entity.homepageId),
        ),
      );
    }
    final relatedSearchCard = _buildRelatedSearchCard(isDark: isDark);
    final mixedTiles = _buildContentMasonryTiles(
      isDark: isDark,
      fgSecondary: fgSecondary,
      items: _contentResults,
      relatedSearchCard: relatedSearchCard,
    );
    if (mixedTiles.isNotEmpty) {
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerLg));
      }
      sections.addAll(mixedTiles);
    }

    if (sections.isEmpty) {
      return <Widget>[
        _CategorySummaryCard(
          title: activeTab.label,
          description: activeTab.description,
          count: 0,
          isDark: isDark,
        ),
        _StatusMessage(text: '没有找到相关应用内结果', isDark: isDark),
      ];
    }
    return sections;
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

  List<Widget> _buildIntersectionResultChildren({
    required bool isDark,
    required Color fgSecondary,
  }) {
    if (_isLoading) {
      return <Widget>[
        _StatusMessage(text: '正在整理与你的交集', isDark: isDark, loading: true),
      ];
    }

    final sections = <Widget>[];

    final connections = _connectionCardModels();
    if (connections.isNotEmpty) {
      final hasMore = connections.length > _connectionCollapsedCap;
      final visible = _showAllConnections
          ? connections
          : connections.take(_connectionCollapsedCap).toList(growable: false);
      sections.add(
        _SearchResultSectionHeader(
          title: '已形成的连接',
          subtitle: '基于你的互动、关注和加入',
          actionLabel: hasMore ? (_showAllConnections ? '收起' : '查看全部') : null,
          onAction: hasMore
              ? () => setState(() => _showAllConnections = !_showAllConnections)
              : null,
        ),
      );
      sections.add(SizedBox(height: AppSpacing.intraGroupMd));
      sections.addAll(
        _buildIntersectionGrid(
          cells: visible
              .map(
                (model) => _IntersectionCard(
                  model: model,
                  isDark: isDark,
                  onTap: () => _openIntersectionTarget(model),
                ),
              )
              .toList(growable: false),
        ),
      );
    }

    final entity = _intersectionEntityResult();
    final discoverCells = _discoverCells(isDark: isDark);
    if (entity != null || discoverCells.isNotEmpty) {
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerXl));
      }
      sections.add(
        _SearchResultSectionHeader(
          title: '发现更多交集',
          subtitle: _query.trim().isEmpty
              ? '为你推荐更多相关内容'
              : '为你推荐更多与“${_query.trim()}”相关的内容',
        ),
      );
      sections.add(SizedBox(height: AppSpacing.intraGroupMd));
      if (entity != null) {
        sections.add(
          _EntityTopResultCard(
            entity: entity,
            isDark: isDark,
            onTap: () => _openHomepage(entity.homepageId),
          ),
        );
        if (discoverCells.isNotEmpty) {
          sections.add(SizedBox(height: AppSpacing.intraGroupMd));
        }
      }
      sections.addAll(_buildIntersectionGrid(cells: discoverCells));
    }

    if (sections.isEmpty) {
      return <Widget>[_StatusMessage(text: '还没有找到和你相关的交集', isDark: isDark)];
    }
    return sections;
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

  // 已形成的连接：展示用户与搜索词之间已经存在的真实连接（connectionState=connected）。
  // 仅展示连接态本身（你已加入 / 你关注过 / 你互动过），footer 用云侧真实计数，
  // 不拼装交集句、不伪造好友数、不编造互动数。
  List<_IntersectionCardModel> _connectionCardModels() {
    final models = <_IntersectionCardModel>[];
    for (final hit in _connectedGroupHits) {
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
          reasonText: '你已加入',
          footerText: card.footerLabel,
        ),
      );
    }
    for (final hit in _connectedLocations) {
      // 一方地点 location.place：未绑定实体主页，落地到临时地点卡（WP-D / R-S05e-1），
      // 不再误导向 homepage 详情。
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.locationPlace,
          targetId: hit.objectId,
          coverUrl: '',
          categoryLabel: '地点',
          categoryIcon: CupertinoIcons.location_solid,
          title: hit.title,
          reasonIcon: CupertinoIcons.location_solid,
          reasonText: '你关注过',
          footerText: hit.subtitle?.trim() ?? '',
        ),
      );
    }
    for (final item in _connectedContentItems) {
      final isVideo = item.contentType == 'video';
      final card = _NetworkResultCardModel.fromSearchItem(item);
      models.add(
        _IntersectionCardModel(
          targetType: _IntersectionTargetType.post,
          targetId: item.postId,
          coverUrl: item.coverUrl ?? '',
          categoryLabel: isVideo ? '视频' : '图片',
          categoryIcon: isVideo
              ? CupertinoIcons.play_rectangle_fill
              : CupertinoIcons.photo_fill,
          title: card.title,
          reasonIcon: isVideo
              ? CupertinoIcons.chat_bubble_fill
              : CupertinoIcons.heart_fill,
          reasonText: isVideo ? '你互动过' : '你点赞过',
          footerText: card.footerLabel,
          metricLabel: item.likeCount > 0 ? '${item.likeCount}' : null,
          metricIcon: CupertinoIcons.heart,
          showVideoBadge: isVideo,
        ),
      );
    }
    return models;
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
      final intersectionSentence = item.intersectionReason?.primaryText.trim() ?? '';
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

  List<Widget> _buildContentMasonryTiles({
    required bool isDark,
    required Color fgSecondary,
    required List<PostSearchItemView> items,
    Widget? relatedSearchCard,
  }) {
    final cards = items
        .map(_NetworkResultCardModel.fromSearchItem)
        .toList(growable: false);
    if (cards.isEmpty && relatedSearchCard == null) {
      return const <Widget>[];
    }
    final cells = <Widget>[
      ?relatedSearchCard,
      for (final card in cards)
        Builder(
          builder: (context) {
            final meta = _contentCloudMetaById[card.postId];
            // R-003：优先用云侧封面真实宽高比 / 排序理由；缺失时回退既有端侧渲染。
            final aspectRatio =
                meta?.aspectRatio ?? (card.showVideoBadge ? 16 / 9 : 1);
            final supportingText = meta?.topRankReason ?? card.supportingText;
            return PostPreviewCard(
              isDark: isDark,
              title: card.title,
              supportingText: supportingText,
              coverUrl: card.coverUrl,
              showVideoBadge: card.showVideoBadge,
              mediaAspectRatio: aspectRatio,
              footer: Row(
                children: [
                  Expanded(
                    child: Text(
                      card.footerLabel,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: AppTypography.iosCaption1,
                        color: fgSecondary,
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupXs),
                  PostCardMetric(
                    icon: CupertinoIcons.heart,
                    label: '${card.likeCount}',
                    color: fgSecondary,
                  ),
                ],
              ),
              onTap: () {
                unawaited(_openPost(card.postId));
              },
            );
          },
        ),
    ];
    return _buildAdaptiveMasonry(cells: cells);
  }

  void _scheduleRefresh({bool immediate = false}) {
    _debounceTimer?.cancel();
    if (immediate) {
      unawaited(_loadResults());
      return;
    }
    _debounceTimer = Timer(_queryDebounce, () => unawaited(_loadResults()));
  }

  Future<void> _loadResults() async {
    final token = ++_requestToken;
    final trimmedQuery = _query.trim();
    setState(() {
      _isLoading = true;
      _errorSemantic = null;
      _degradeSignals = const <SearchDegradeSignal>[];
      if (_activeTabId == _tabXiaoqu) {
        _xiaoquResult = null;
      } else {
        _groupResults = const <SearchHit>[];
        _locationResults = const <SearchHit>[];
        _contentResults = const <PostSearchItemView>[];
        _contentCloudMetaById = const <String, _ContentCloudMeta>{};
        _relatedTerms = const <String>[];
      }
    });
    try {
      if (_activeTabId == _tabXiaoqu) {
        final result = await ref
            .read(assistantRepositoryProvider)
            .searchXiaoquResults(query: trimmedQuery);
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _xiaoquResult = result;
          _isLoading = false;
        });
        return;
      }

      if (_activeTabId == _tabAll || _activeTabId == _tabIntersection) {
        if (trimmedQuery.isEmpty) {
          if (!mounted || token != _requestToken) {
            return;
          }
          setState(() {
            _isLoading = false;
          });
          return;
        }
        if (_activeTabId == _tabAll) {
          final locationResponse = await _guardedSearchResponse(
            _loadLocationResponse(trimmedQuery),
          );
          final contentResponse = await _guardedSearchResponse(
            _loadContentResponse(trimmedQuery),
          );
          if (!mounted || token != _requestToken) {
            return;
          }
          setState(() {
            _locationResults = _locationHitsFromResponse(locationResponse);
            _contentResults = _contentItemsFromResponse(contentResponse);
            _relatedTerms = contentResponse.relatedTerms;
            _degradeSignals = _mergeDegradeSignals(<SearchResponse>[
              locationResponse,
              contentResponse,
            ]);
            _isLoading = false;
          });
          return;
        }
        final groupResponse = await _guardedSearchResponse(
          _loadGroupResponse(trimmedQuery),
        );
        final locationResponse = await _guardedSearchResponse(
          _loadLocationResponse(trimmedQuery),
        );
        final contentResponse = await _guardedSearchResponse(
          _loadContentResponse(trimmedQuery),
        );
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _groupResults = _groupHitsFromResponse(groupResponse);
          _locationResults = _locationHitsFromResponse(locationResponse);
          _contentResults = _contentItemsFromResponse(contentResponse);
          _degradeSignals = _mergeDegradeSignals(<SearchResponse>[
            groupResponse,
            locationResponse,
            contentResponse,
          ]);
          _isLoading = false;
        });
        return;
      }

      final response = trimmedQuery.isEmpty
          ? null
          : await _guardedSearchResponse(_loadContentResponse(trimmedQuery));
      final items = response == null
          ? const <PostSearchItemView>[]
          : _contentItemsFromResponse(response);
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _contentResults = items;
        _relatedTerms = response?.relatedTerms ?? const <String>[];
        _degradeSignals = response?.degradeSignals ?? const <SearchDegradeSignal>[];
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _errorSemantic = runtimeErrorSemantic(
          context,
          error: error,
          category: UiErrorCategory.pageLoad,
          scope: UiErrorScope.page,
        );
        _isLoading = false;
      });
    }
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
            code: 'search_domain_failed',
            message: '部分搜索分组加载失败，已继续展示其它结果。',
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

  List<PostSearchItemView> _contentItemsFromResponse(SearchResponse response) {
    final cloudMeta = <String, _ContentCloudMeta>{};
    final results = <PostSearchItemView>[];
    for (final hit in _hitsFromResponse(response)) {
      if (hit.objectType != SearchObjectType.contentPost) {
        continue;
      }
      final item =
          hit.asContentPostItem ??
          PostSearchItemView.fromMap(hit.payload.toWireMap());
      results.add(item);
      final meta = _ContentCloudMeta(
        rankPosition: hit.rankPosition,
        coverWidth: hit.coverWidth,
        coverHeight: hit.coverHeight,
        rankReasons: hit.rankReasons,
      );
      if (item.postId.isNotEmpty && meta.hasCloudSignal) {
        cloudMeta[item.postId] = meta;
      }
    }
    // R-001：命中携带云侧 rankPosition 时，按云侧排序而非端侧 publishedAt 兜底排序。
    final hasCloudRank = results.any(
      (item) => cloudMeta[item.postId]?.rankPosition != null,
    );
    if (hasCloudRank) {
      results.sort((left, right) {
        final leftRank = cloudMeta[left.postId]?.rankPosition;
        final rightRank = cloudMeta[right.postId]?.rankPosition;
        if (leftRank == null && rightRank == null) {
          return 0;
        }
        if (leftRank == null) {
          return 1;
        }
        if (rightRank == null) {
          return -1;
        }
        return leftRank.compareTo(rightRank);
      });
    } else {
      results.sort((left, right) {
        final leftTime = left.publishedAt;
        final rightTime = right.publishedAt;
        if (leftTime == null && rightTime == null) {
          return 0;
        }
        if (leftTime == null) {
          return 1;
        }
        if (rightTime == null) {
          return -1;
        }
        return rightTime.compareTo(leftTime);
      });
    }
    final sorted = results.take(12).toList(growable: false);
    _contentCloudMetaById = cloudMeta;
    return sorted;
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
              (item) =>
                  item.contentType == 'image' || item.contentType == 'photo',
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

  Future<void> _openPost(String postId) async {
    if (postId.trim().isEmpty) {
      return;
    }
    try {
      final detail = await ref
          .read(contentRepositoryProvider)
          .getPost(postId: postId);
      applyConfirmedInteractionPost(ref, detail.post);
      if (!mounted) {
        return;
      }
      final dto = detail.post;
      final raw = detail.mergedArticleWireMap;
      final interactionSnapshot = buildMediaViewerInteractionSnapshot(
        posts: <PostBaseDto>[dto],
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
          dtoPosts: <PostBaseDto>[dto],
          initialIndex: 0,
          category: dto.isVideoLike
              ? 'video'
              : (dto.identity == 'moment' ? 'moment' : 'photo'),
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
      await _showOpenPostFailure(error);
    }
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
        title: '内容暂时打不开',
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

class _XiaoquSummaryCard extends StatelessWidget {
  const _XiaoquSummaryCard({
    required this.query,
    required this.result,
    required this.isDark,
  });

  final String query;
  final AssistantSearchResultView? result;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.primaryColor.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(
          color: AppColors.primaryColor.withValues(alpha: 0.18),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(
                  CupertinoIcons.sparkles,
                  color: AppColors.assistantMarkColor,
                  size: AppSpacing.iconMedium,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Text(
                  '小趣',
                  style: TextStyle(
                    fontSize: _SearchResultTokens.sectionTitleSize,
                    fontWeight: _SearchResultTokens.sectionTitleWeight,
                    color: fgPrimary,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              query.trim().isEmpty ? '为你整理了当前热门网络结果' : '正在为你整理“$query”的网络结果',
              style: TextStyle(
                fontSize: _SearchResultTokens.bodySize,
                fontWeight: _SearchResultTokens.bodyWeight,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              (result?.summary?.trim().isNotEmpty == true)
                  ? result!.summary!.trim()
                  : '先按圈子讨论分类聚合内容，再把最相关的创作和讨论铺开，方便继续筛选。',
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: fgSecondary,
              ),
            ),
            if ((result?.citations?.length ?? 0) > 0) ...[
              SizedBox(height: AppSpacing.containerSm),
              Text(
                '已整理 ${result!.citations!.length} 条可继续查看的引用线索',
                style: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: fgSecondary,
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusMessage extends StatelessWidget {
  const _StatusMessage({
    required this.text,
    required this.isDark,
    this.loading = false,
  });

  final String text;
  final bool isDark;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.only(top: AppSpacing.containerLg),
      child: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (loading) ...[
              CupertinoActivityIndicator(radius: AppSpacing.iconSmall / 2),
              SizedBox(height: AppSpacing.containerSm),
            ],
            Text(
              text,
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                color: fgSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _CategorySummaryCard extends StatelessWidget {
  const _CategorySummaryCard({
    required this.title,
    required this.description,
    required this.count,
    required this.isDark,
  });

  final String title;
  final String description;
  final int count;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.containerMd),
      child: Text(
        '$title · $count 条结果${description.isEmpty ? '' : ' · $description'}',
        style: TextStyle(
          fontSize: AppTypography.iosFootnote,
          color: fgSecondary,
        ),
      ),
    );
  }
}

class _SearchResultSectionHeader extends StatelessWidget {
  const _SearchResultSectionHeader({
    required this.title,
    this.subtitle,
    this.actionLabel,
    this.onAction,
  });

  final String title;
  final String? subtitle;
  final String? actionLabel;
  final VoidCallback? onAction;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: TextStyle(
                  fontSize: _SearchResultTokens.sectionTitleSize,
                  fontWeight: _SearchResultTokens.sectionTitleWeight,
                  color: fgPrimary,
                ),
              ),
              if (subtitle != null && subtitle!.trim().isNotEmpty) ...[
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  subtitle!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosCaption1,
                    color: fgSecondary,
                  ),
                ),
              ],
            ],
          ),
        ),
        if (actionLabel != null && onAction != null)
          CupertinoButton(
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: onAction,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  actionLabel!,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    color: fgSecondary,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs / 2),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.iconSmall,
                  color: fgSecondary,
                ),
              ],
            ),
          ),
      ],
    );
  }
}

class _MediaCategoryBadge extends StatelessWidget {
  const _MediaCategoryBadge({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.45),
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.intraGroupSm,
          vertical: AppSpacing.intraGroupXs / 2,
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.iosCaption2,
            color: AppColors.white,
          ),
        ),
      ),
    );
  }
}

class _IntersectionCardPlaceholder extends StatelessWidget {
  const _IntersectionCardPlaceholder({required this.icon});

  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return ColoredBox(
      color: AppColors.primaryColor.withValues(alpha: 0.08),
      child: Center(
        child: Icon(
          icon,
          color: AppColors.primaryColor,
          size: AppSpacing.iconLarge,
        ),
      ),
    );
  }
}

class _IntersectionCard extends StatelessWidget {
  const _IntersectionCard({
    required this.model,
    required this.isDark,
    required this.onTap,
  });

  final _IntersectionCardModel model;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final hasCover = model.coverUrl.trim().isNotEmpty;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: 16 / 10,
              child: ClipRRect(
                borderRadius: const BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.contentPreviewCornerRadius),
                ),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (hasCover)
                      CachedNetworkImage(
                        imageUrl: model.coverUrl,
                        fit: BoxFit.cover,
                        placeholder: (context, url) =>
                            _IntersectionCardPlaceholder(
                              icon: model.categoryIcon,
                            ),
                        errorWidget: (context, url, error) =>
                            _IntersectionCardPlaceholder(
                              icon: model.categoryIcon,
                            ),
                      )
                    else
                      _IntersectionCardPlaceholder(icon: model.categoryIcon),
                    Positioned(
                      top: AppSpacing.postPreviewCardPadding,
                      left: AppSpacing.postPreviewCardPadding,
                      child: _MediaCategoryBadge(label: model.categoryLabel),
                    ),
                    if (model.showVideoBadge)
                      Positioned(
                        top: AppSpacing.postPreviewCardPadding,
                        right: AppSpacing.postPreviewCardPadding,
                        child: Icon(
                          CupertinoIcons.play_circle_fill,
                          color: AppColors.white,
                          size: AppSpacing.iconLarge - AppSpacing.xs,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.all(AppSpacing.postPreviewCardPadding),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    model.title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosFootnote,
                      fontWeight: AppTypography.medium,
                      color: fgPrimary,
                    ),
                  ),
                  // §3：交集句只在有云侧文案时展示；无 primaryText 不渲染句行、不占位。
                  if (model.reasonText.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Row(
                      children: [
                        Icon(
                          model.reasonIcon,
                          size: AppSpacing.iconSmall,
                          color: AppColors.primaryColor,
                        ),
                        SizedBox(width: AppSpacing.intraGroupXs / 2),
                        Expanded(
                          child: Text(
                            model.reasonText,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption1,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ],
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  Row(
                    children: [
                      Expanded(
                        child: Text(
                          model.footerText,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: AppTypography.iosCaption1,
                            color: fgSecondary,
                          ),
                        ),
                      ),
                      if (model.metricLabel != null) ...[
                        SizedBox(width: AppSpacing.intraGroupXs),
                        PostCardMetric(
                          icon: model.metricIcon ?? CupertinoIcons.heart,
                          label: model.metricLabel!,
                          color: fgSecondary,
                        ),
                      ],
                    ],
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _EntityTopResultCard extends StatelessWidget {
  const _EntityTopResultCard({
    required this.entity,
    required this.isDark,
    required this.onTap,
  });

  final _EntityTopResultModel entity;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Row(
          children: [
            Container(
              width: AppSpacing.avatarUserLg,
              height: AppSpacing.avatarUserLg,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.1),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.building_2_fill,
                size: AppSpacing.iconMedium,
                color: AppColors.primaryColor,
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          entity.title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: _SearchResultTokens.sectionTitleSize,
                            fontWeight: _SearchResultTokens.sectionTitleWeight,
                            color: fgPrimary,
                          ),
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupSm),
                      Text(
                        entity.badge,
                        style: TextStyle(
                          fontSize: _SearchResultTokens.captionSize,
                          color: AppColors.primaryColor,
                        ),
                      ),
                    ],
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  Text(
                    entity.subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: _SearchResultTokens.captionSize,
                      color: fgSecondary,
                    ),
                  ),
                  if (entity.connectionReason != null &&
                      entity.connectionReason!.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      entity.connectionReason!,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: AppColors.primaryColor,
                      ),
                    ),
                  ],
                  if (entity.description.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      entity.description,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                  if (entity.meta.trim().isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      entity.meta,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.captionSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            if (entity.actionLabel != null) ...[
              DecoratedBox(
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                  border: Border.all(color: AppColors.primaryColor),
                ),
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerSm,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  child: Text(
                    entity.actionLabel!,
                    style: TextStyle(
                      fontSize: _SearchResultTokens.captionSize,
                      color: AppColors.primaryColor,
                    ),
                  ),
                ),
              ),
            ] else
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconSmall,
                color: fgSecondary,
              ),
          ],
        ),
      ),
    );
  }
}

class _RelatedSearchCard extends StatelessWidget {
  const _RelatedSearchCard({
    required this.card,
    required this.isDark,
    required this.onTap,
  });

  final RelatedSearchTermCardView card;
  final bool isDark;
  final ValueChanged<NetworkSearchSuggestion> onTap;

  @override
  Widget build(BuildContext context) {
    final surface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final border = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '相关搜索',
              style: TextStyle(
                fontSize: _SearchResultTokens.cardTitleSize,
                fontWeight: _SearchResultTokens.sectionTitleWeight,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            for (var i = 0; i < card.terms.length; i++)
              Padding(
                padding: EdgeInsets.only(
                  bottom: i == card.terms.length - 1
                      ? 0
                      : AppSpacing.intraGroupSm,
                ),
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => onTap(card.terms[i]),
                  child: Align(
                    alignment: Alignment.centerLeft,
                    child: Text(
                      card.terms[i].displayTitle,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(
                        fontSize: _SearchResultTokens.bodySize,
                        fontWeight: _SearchResultTokens.bodyWeight,
                        color: fgPrimary,
                      ),
                    ),
                  ),
                ),
              ),
            if (card.terms.isEmpty)
              Text(
                '暂无相关搜索词',
                style: TextStyle(
                  fontSize: _SearchResultTokens.captionSize,
                  color: fgSecondary,
                ),
              ),
          ],
        ),
      ),
    );
  }
}

enum _IntersectionTargetType { circle, homepage, post, user, locationPlace }

class _IntersectionCardModel {
  const _IntersectionCardModel({
    required this.targetType,
    required this.targetId,
    required this.coverUrl,
    required this.categoryLabel,
    required this.categoryIcon,
    required this.title,
    required this.reasonIcon,
    required this.reasonText,
    required this.footerText,
    this.metricLabel,
    this.metricIcon,
    this.showVideoBadge = false,
  });

  final _IntersectionTargetType targetType;
  final String targetId;
  final String coverUrl;
  final String categoryLabel;
  final IconData categoryIcon;
  final String title;
  final IconData reasonIcon;
  final String reasonText;
  final String footerText;
  final String? metricLabel;
  final IconData? metricIcon;
  final bool showVideoBadge;
}

class _SearchNetworkTab {
  const _SearchNetworkTab({
    required this.id,
    required this.label,
    required this.description,
  });

  final String id;
  final String label;
  final String description;
}

/// 云侧内容命中的排序 / 封面 / 理由元信息（R-001/R-003）。
///
/// 与 [PostSearchItemView] 解耦：仅承载云侧透传字段，按 postId 旁挂到结果页状态，
/// 避免改动跨 tab 共享的 [PostSearchItemView] 字段表（其被交集 tab 等多处消费）。
class _ContentCloudMeta {
  const _ContentCloudMeta({
    this.rankPosition,
    this.coverWidth,
    this.coverHeight,
    this.rankReasons = const <String>[],
  });

  final int? rankPosition;
  final double? coverWidth;
  final double? coverHeight;
  final List<String> rankReasons;

  /// 是否携带任一云侧信号；无信号的命中（本地/mock）不入元信息表。
  bool get hasCloudSignal =>
      rankPosition != null ||
      coverWidth != null ||
      coverHeight != null ||
      rankReasons.isNotEmpty;

  /// 云侧封面真实宽高比；缺失任一维度则返回 null，由调用方回退默认比例。
  double? get aspectRatio {
    final width = coverWidth;
    final height = coverHeight;
    if (width == null || height == null || width <= 0 || height <= 0) {
      return null;
    }
    return width / height;
  }

  /// 首条排序理由（人类可读标签），用于卡片排序透明化文案。
  String? get topRankReason => rankReasons.isEmpty ? null : rankReasons.first;
}

class _NetworkResultCardModel {
  const _NetworkResultCardModel({
    required this.postId,
    required this.title,
    required this.supportingText,
    required this.coverUrl,
    required this.footerLabel,
    required this.eyebrowText,
    required this.likeCount,
    required this.showVideoBadge,
  });

  final String postId;
  final String title;
  final String supportingText;
  final String coverUrl;
  final String footerLabel;
  final String eyebrowText;
  final int likeCount;
  final bool showVideoBadge;

  factory _NetworkResultCardModel.fromSearchItem(PostSearchItemView item) {
    final footerSegments = <String>[
      if ((item.circleName ?? '').trim().isNotEmpty) item.circleName!.trim(),
      if ((item.authorDisplayName ?? '').trim().isNotEmpty)
        item.authorDisplayName!.trim(),
    ];
    return _NetworkResultCardModel(
      postId: item.postId,
      title: item.title?.trim().isNotEmpty == true
          ? item.title!.trim()
          : (item.highlightText?.trim().isNotEmpty == true
                ? item.highlightText!.trim()
                : (item.summary?.trim().isNotEmpty == true
                      ? item.summary!.trim()
                      : (item.authorDisplayName?.trim().isNotEmpty == true
                            ? item.authorDisplayName!.trim()
                            : '网络结果'))),
      supportingText: item.summary?.trim().isNotEmpty == true
          ? item.summary!.trim()
          : (item.highlightText?.trim().isNotEmpty == true
                ? item.highlightText!.trim()
                : '打开相关内容'),
      coverUrl: item.coverUrl ?? '',
      footerLabel: footerSegments.isEmpty ? '内容结果' : footerSegments.join(' · '),
      eyebrowText: item.subCategory?.trim().isNotEmpty == true
          ? item.subCategory!.trim()
          : (item.circleName?.trim().isNotEmpty == true
                ? item.circleName!.trim()
                : '网络结果'),
      likeCount: item.likeCount,
      showVideoBadge: item.contentType == 'video',
    );
  }
}

class _EntityTopResultModel {
  const _EntityTopResultModel({
    required this.homepageId,
    required this.title,
    required this.badge,
    required this.subtitle,
    required this.description,
    required this.meta,
    this.connectionReason,
    this.actionLabel,
  });

  final String homepageId;
  final String title;
  final String badge;
  final String subtitle;
  final String description;
  final String meta;
  final String? connectionReason;
  final String? actionLabel;
}

class _GroupResultCardModel {
  const _GroupResultCardModel({
    required this.circleId,
    required this.title,
    required this.supportingText,
    required this.coverUrl,
    required this.footerLabel,
    required this.eyebrowText,
  });

  final String circleId;
  final String title;
  final String supportingText;
  final String coverUrl;
  final String footerLabel;
  final String eyebrowText;

  factory _GroupResultCardModel.fromHit(SearchHit hit) {
    final isCircle = hit.objectType == SearchObjectType.circleCircle;
    final view =
        hit.asCircleCircleItem ??
        CircleSearchItemView.fromMap(hit.payload.toWireMap());
    final circleId = isCircle
        ? hit.objectId
        : (view.circleId.isNotEmpty ? view.circleId : hit.objectId);
    final memberCount = view.memberCount;
    final postCount = view.postCount;
    final circleNameLabel = view.circleName?.trim() ?? '';
    final footerSegments = <String>[
      if (circleNameLabel.isNotEmpty) circleNameLabel,
      if (memberCount > 0) '$memberCount 人',
      if (postCount > 0) '$postCount 篇内容',
      if (hit.resolvedFrom == SearchResolvedFrom.localFallback) '本地回退',
    ];
    return _GroupResultCardModel(
      circleId: circleId,
      title: hit.title,
      supportingText: hit.snippet?.trim().isNotEmpty == true
          ? hit.snippet!.trim()
          : (hit.subtitle?.trim().isNotEmpty == true
                ? hit.subtitle!.trim()
                : '打开相关圈子'),
      coverUrl: view.coverUrl ?? '',
      footerLabel: footerSegments.isEmpty ? '讨论结果' : footerSegments.join(' · '),
      eyebrowText: isCircle ? '圈子' : '讨论',
    );
  }
}
