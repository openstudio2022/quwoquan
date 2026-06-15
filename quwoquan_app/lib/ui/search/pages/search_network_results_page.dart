import 'dart:async';

import 'package:flutter/cupertino.dart';
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
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/search/models/search_result_tab_spec.dart';
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
  List<SearchHit> _messageResults = const <SearchHit>[];
  List<SearchHit> _contactResults = const <SearchHit>[];
  List<SearchHit> _locationResults = const <SearchHit>[];
  List<SearchHit> _userResults = const <SearchHit>[];
  List<SearchDegradeSignal> _degradeSignals = const <SearchDegradeSignal>[];

  @override
  void initState() {
    super.initState();
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
    });
  }

  @override
  void dispose() {
    _debounceTimer?.cancel();
    _controller.dispose();
    _focusNode.dispose();
    super.dispose();
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
      final banner = _buildDegradeBanner(isDark: isDark);
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
      else if (_activeTabId == _tabArticle)
        ..._buildContentResultTiles(
          isDark: isDark,
          fgSecondary: fgSecondary,
          items: contentItems,
        )
      else
        ..._buildContentMasonryTiles(
          isDark: isDark,
          fgSecondary: fgSecondary,
          items: contentItems,
        ),
    ]);
  }

  Widget? _buildDegradeBanner({required bool isDark}) {
    if (_degradeSignals.isEmpty) {
      return null;
    }
    final first = _degradeSignals.first;
    return _StatusMessage(text: '部分结果已降级：${first.message}', isDark: isDark);
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
    void addSection({
      required String title,
      required String description,
      required int count,
      required List<Widget> tiles,
    }) {
      if (count == 0 || tiles.isEmpty) {
        return;
      }
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerLg));
      }
      sections.add(
        _CategorySummaryCard(
          title: title,
          description: description,
          count: count,
          isDark: isDark,
        ),
      );
      sections.addAll(tiles);
    }

    addSection(
      title: '聊天记录',
      description: '已连接',
      count: _messageResults.length,
      tiles: _buildGenericHitTiles(
        hits: _messageResults.take(3).toList(growable: false),
        emptyEyebrow: '聊天记录',
        isDark: isDark,
        fgSecondary: fgSecondary,
      ),
    );
    addSection(
      title: '联系人',
      description: '已连接',
      count: _contactResults.length,
      tiles: _buildGenericHitTiles(
        hits: _contactResults.take(4).toList(growable: false),
        emptyEyebrow: '联系人',
        isDark: isDark,
        fgSecondary: fgSecondary,
      ),
    );
    addSection(
      title: '已加入圈子',
      description: '已连接',
      count: _connectedGroupHits.length,
      tiles: _buildCompactHitGrid(
        hits: _connectedGroupHits.take(3).toList(growable: false),
        isDark: isDark,
        fallbackIcon: CupertinoIcons.person_3_fill,
      ),
    );
    addSection(
      title: '已关注地点',
      description: '已连接',
      count: _connectedLocationHits.length,
      tiles: _buildCompactHitGrid(
        hits: _connectedLocationHits.take(3).toList(growable: false),
        isDark: isDark,
        fallbackIcon: CupertinoIcons.location_solid,
      ),
    );
    addSection(
      title: '已关注的人',
      description: '已连接',
      count: _connectedUserHits.length,
      tiles: _buildCompactHitGrid(
        hits: _connectedUserHits.take(4).toList(growable: false),
        isDark: isDark,
        fallbackIcon: CupertinoIcons.person_crop_circle_fill,
      ),
    );
    addSection(
      title: '已互动内容',
      description: '赞评转过的内容优先',
      count: _connectedContentItems.length,
      tiles: _buildContentResultTiles(
        isDark: isDark,
        fgSecondary: fgSecondary,
        items: _connectedContentItems.take(2).toList(growable: false),
      ),
    );

    final discoverySections = _buildDiscoverySections(
      isDark: isDark,
      fgSecondary: fgSecondary,
    );
    if (discoverySections.isNotEmpty) {
      if (sections.isNotEmpty) {
        sections.add(SizedBox(height: AppSpacing.containerXl));
      }
      sections.add(
        _CategorySummaryCard(
          title: '发现区',
          description: '未连接结果按类别比例混排',
          count: _discoveryResultCount,
          isDark: isDark,
        ),
      );
      sections.addAll(discoverySections);
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
        _StatusMessage(text: '正在加载交集结果', isDark: isDark, loading: true),
      ];
    }
    final connectedCount =
        _messageResults.length +
        _contactResults.length +
        _connectedGroupHits.length +
        _connectedUserHits.length;
    final sections = <Widget>[
      _IntersectionOverviewCard(
        isDark: isDark,
        sharedInterestCount:
            _discoveryContentItems.length + _discoveryGroupHits.length,
        sharedCircleCount: _groupResults.length,
        sharedFollowingCount: _userResults.length,
        sharedDiscussionCount: _messageResults.length,
      ),
      SizedBox(height: AppSpacing.containerLg),
    ];
    void addIntersectionSection({
      required String title,
      required String description,
      required int count,
      required List<Widget> tiles,
    }) {
      if (count == 0 || tiles.isEmpty) {
        return;
      }
      if (sections.length > 2) {
        sections.add(SizedBox(height: AppSpacing.containerLg));
      }
      sections.add(
        _CategorySummaryCard(
          title: title,
          description: description,
          count: count,
          isDark: isDark,
        ),
      );
      sections.addAll(tiles);
    }

    addIntersectionSection(
      title: '感兴趣圈子',
      description: '按共同兴趣排序',
      count: _groupResults.length,
      tiles: _buildCompactHitGrid(
        hits: _groupResults.take(3).toList(growable: false),
        isDark: isDark,
        fallbackIcon: CupertinoIcons.person_3_fill,
        reasonLabel: '共同兴趣：摄影',
      ),
    );
    addIntersectionSection(
      title: '感兴趣地点',
      description: '按共同地点排序',
      count: _locationResults.length,
      tiles: _buildCompactHitGrid(
        hits: _locationResults.take(3).toList(growable: false),
        isDark: isDark,
        fallbackIcon: CupertinoIcons.location_solid,
        reasonLabel: '12个交集',
      ),
    );
    addIntersectionSection(
      title: '同趣的人',
      description: '按共同兴趣排序',
      count: _userResults.length,
      tiles: _buildCompactHitGrid(
        hits: _userResults.take(4).toList(growable: false),
        isDark: isDark,
        fallbackIcon: CupertinoIcons.person_crop_circle_fill,
        reasonLabel: '共同兴趣 3 个',
      ),
    );
    addIntersectionSection(
      title: '已互动内容',
      description: '赞评转过的内容',
      count: _connectedContentItems.length,
      tiles: _buildContentResultTiles(
        isDark: isDark,
        fgSecondary: fgSecondary,
        items: _connectedContentItems,
      ),
    );

    final flow = _buildDiscoverySections(
      isDark: isDark,
      fgSecondary: fgSecondary,
      intersectionMode: true,
    );
    if (flow.isNotEmpty) {
      sections.add(SizedBox(height: AppSpacing.containerXl));
      sections.add(
        _CategorySummaryCard(
          title: '交集发现流',
          description: connectedCount > 0 ? '按交集强度继续发现' : '按共同兴趣继续发现',
          count: _discoveryResultCount,
          isDark: isDark,
        ),
      );
      sections.addAll(flow);
    }
    if (sections.length <= 2) {
      return <Widget>[_StatusMessage(text: '没有找到相关交集结果', isDark: isDark)];
    }
    return sections;
  }

  List<Widget> _buildDiscoverySections({
    required bool isDark,
    required Color fgSecondary,
    bool intersectionMode = false,
  }) {
    final imageItems = _discoveryContentItems
        .where(
          (item) => item.contentType == 'image' || item.contentType == 'photo',
        )
        .toList(growable: false);
    final videoItems = _discoveryContentItems
        .where((item) => item.contentType == 'video')
        .toList(growable: false);
    final articleItems = _discoveryContentItems
        .where((item) => item.contentType == 'article')
        .toList(growable: false);
    final buckets = <_DiscoverySectionBucket>[
      _discoveryBucketForHits(
        title: intersectionMode ? '交集圈子' : '圈子',
        description: intersectionMode ? '共同圈子与兴趣' : '未加入圈子',
        hits: _discoveryGroupHits,
        chunkSize: 3,
        isDark: isDark,
        fallbackIcon: CupertinoIcons.person_3_fill,
        reasonLabel: intersectionMode ? '共同圈子：旅行圈' : null,
      ),
      _discoveryBucketForHits(
        title: intersectionMode ? '交集地点' : '地点',
        description: intersectionMode ? '共同关注与讨论地点' : '未关注地点',
        hits: _discoveryLocationHits,
        chunkSize: 3,
        isDark: isDark,
        fallbackIcon: CupertinoIcons.location_solid,
        reasonLabel: intersectionMode ? '12个交集' : null,
      ),
      _discoveryBucketForHits(
        title: intersectionMode ? '同趣的人' : '人',
        description: intersectionMode ? '共同兴趣更强的人' : '尚未连接的人',
        hits: _discoveryUserHits,
        chunkSize: 4,
        isDark: isDark,
        fallbackIcon: CupertinoIcons.person_crop_circle_fill,
        reasonLabel: intersectionMode ? '共同兴趣：摄影' : null,
      ),
      _discoveryBucketForContent(
        title: '图片',
        description: intersectionMode ? '带交集理由的图片' : '未互动图片',
        items: imageItems,
        chunkSize: 4,
        isDark: isDark,
        fgSecondary: fgSecondary,
        masonry: true,
      ),
      _discoveryBucketForContent(
        title: '视频',
        description: intersectionMode ? '带交集理由的视频' : '未互动视频',
        items: videoItems,
        chunkSize: 4,
        isDark: isDark,
        fgSecondary: fgSecondary,
        masonry: true,
      ),
      _discoveryBucketForContent(
        title: '长文',
        description: intersectionMode ? '带交集理由的长文' : '未互动长文',
        items: articleItems,
        chunkSize: 2,
        isDark: isDark,
        fgSecondary: fgSecondary,
        masonry: false,
      ),
    ].where((bucket) => bucket.sections.isNotEmpty).toList(growable: false);

    final mixed = <Widget>[];
    final working = buckets
        .map((bucket) => bucket.copy())
        .toList(growable: false);
    while (working.any((bucket) => bucket.sections.isNotEmpty)) {
      working.sort(
        (left, right) => right.sections.length.compareTo(left.sections.length),
      );
      final next = working.firstWhere((bucket) => bucket.sections.isNotEmpty);
      if (mixed.isNotEmpty) {
        mixed.add(SizedBox(height: AppSpacing.containerLg));
      }
      mixed.add(next.sections.removeAt(0));
    }
    return mixed;
  }

  _DiscoverySectionBucket _discoveryBucketForHits({
    required String title,
    required String description,
    required List<SearchHit> hits,
    required int chunkSize,
    required bool isDark,
    required IconData fallbackIcon,
    String? reasonLabel,
  }) {
    final sections = <Widget>[];
    for (var start = 0; start < hits.length; start += chunkSize) {
      final chunk = hits.skip(start).take(chunkSize).toList(growable: false);
      sections.add(
        _DiscoveryGroupBlock(
          title: title,
          description: description,
          count: chunk.length,
          isDark: isDark,
          child: Column(
            children: _buildCompactHitGrid(
              hits: chunk,
              isDark: isDark,
              fallbackIcon: fallbackIcon,
              reasonLabel: reasonLabel,
            ),
          ),
        ),
      );
    }
    return _DiscoverySectionBucket(sections);
  }

  _DiscoverySectionBucket _discoveryBucketForContent({
    required String title,
    required String description,
    required List<PostSearchItemView> items,
    required int chunkSize,
    required bool isDark,
    required Color fgSecondary,
    required bool masonry,
  }) {
    final sections = <Widget>[];
    for (var start = 0; start < items.length; start += chunkSize) {
      final chunk = items.skip(start).take(chunkSize).toList(growable: false);
      sections.add(
        _DiscoveryGroupBlock(
          title: title,
          description: description,
          count: chunk.length,
          isDark: isDark,
          child: Column(
            children: masonry
                ? _buildContentMasonryTiles(
                    isDark: isDark,
                    fgSecondary: fgSecondary,
                    items: chunk,
                  )
                : _buildContentResultTiles(
                    isDark: isDark,
                    fgSecondary: fgSecondary,
                    items: chunk,
                  ),
          ),
        ),
      );
    }
    return _DiscoverySectionBucket(sections);
  }

  List<Widget> _buildContentResultTiles({
    required bool isDark,
    required Color fgSecondary,
    List<PostSearchItemView>? items,
  }) {
    final cards = (items ?? _contentResults)
        .map(_NetworkResultCardModel.fromSearchItem)
        .toList(growable: false);
    return <Widget>[
      for (var i = 0; i < cards.length; i++) ...[
        PostPreviewListTile(
          isDark: isDark,
          title: cards[i].title,
          supportingText: cards[i].supportingText,
          coverUrl: cards[i].coverUrl,
          eyebrowText: cards[i].eyebrowText,
          showVideoBadge: cards[i].showVideoBadge,
          footer: Row(
            children: [
              Expanded(
                child: Text(
                  cards[i].footerLabel,
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
                label: '${cards[i].likeCount}',
                color: fgSecondary,
              ),
            ],
          ),
          onTap: () {
            unawaited(_openPost(cards[i].postId));
          },
        ),
        if (i != cards.length - 1) SizedBox(height: AppSpacing.containerSm),
      ],
    ];
  }

  List<Widget> _buildContentMasonryTiles({
    required bool isDark,
    required Color fgSecondary,
    required List<PostSearchItemView> items,
  }) {
    final cards = items
        .map(_NetworkResultCardModel.fromSearchItem)
        .toList(growable: false);
    if (cards.isEmpty) {
      return const <Widget>[];
    }
    return <Widget>[
      GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: cards.length,
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: 2,
          crossAxisSpacing: AppSpacing.intraGroupSm,
          mainAxisSpacing: AppSpacing.intraGroupSm,
          childAspectRatio: 0.72,
        ),
        itemBuilder: (context, index) {
          final card = cards[index];
          return PostPreviewCard(
            isDark: isDark,
            title: card.title,
            supportingText: card.supportingText,
            coverUrl: card.coverUrl,
            showVideoBadge: card.showVideoBadge,
            mediaAspectRatio: card.showVideoBadge ? 16 / 9 : 1,
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
  }

  List<Widget> _buildGenericHitTiles({
    required List<SearchHit> hits,
    required String emptyEyebrow,
    required bool isDark,
    required Color fgSecondary,
  }) {
    return <Widget>[
      for (var i = 0; i < hits.length; i++) ...[
        PostPreviewListTile(
          isDark: isDark,
          title: hits[i].title,
          supportingText: hits[i].snippet ?? hits[i].subtitle ?? '打开相关搜索结果',
          coverUrl: '',
          eyebrowText:
              SearchRegistry.entryFor(hits[i].objectType)?.label ??
              emptyEyebrow,
          footer: Text(
            hits[i].subtitle ?? emptyEyebrow,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () {},
        ),
        if (i != hits.length - 1) SizedBox(height: AppSpacing.containerSm),
      ],
    ];
  }

  List<Widget> _buildCompactHitGrid({
    required List<SearchHit> hits,
    required bool isDark,
    required IconData fallbackIcon,
    String? reasonLabel,
  }) {
    if (hits.isEmpty) {
      return const <Widget>[];
    }
    return <Widget>[
      GridView.builder(
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        itemCount: hits.length,
        gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
          crossAxisCount: fallbackIcon == CupertinoIcons.person_crop_circle_fill
              ? 4
              : 3,
          mainAxisSpacing: AppSpacing.intraGroupSm,
          crossAxisSpacing: AppSpacing.intraGroupSm,
          childAspectRatio:
              fallbackIcon == CupertinoIcons.person_crop_circle_fill
              ? 0.72
              : 0.86,
        ),
        itemBuilder: (context, index) {
          final hit = hits[index];
          return _CompactHitCard(
            hit: hit,
            isDark: isDark,
            fallbackIcon: fallbackIcon,
            reasonLabel: reasonLabel,
            onTap: () => _openSearchHit(hit),
          );
        },
      ),
    ];
  }

  void _openSearchHit(SearchHit hit) {
    switch (hit.objectType) {
      case SearchObjectType.chatContact:
      case SearchObjectType.chatConversation:
      case SearchObjectType.chatMessage:
        final payload = hit.payload.toWireMap();
        final conversationId = (payload['conversationId'] ?? hit.objectId)
            .toString()
            .trim();
        if (conversationId.isNotEmpty) {
          context.push(AppRoutePaths.chatDetail(id: conversationId));
        }
        return;
      case SearchObjectType.circleGroup:
      case SearchObjectType.circleCircle:
        _openGroup(_GroupResultCardModel.fromHit(hit));
        return;
      case SearchObjectType.entityHomepage:
        _openHomepage(hit.objectId);
        return;
      case SearchObjectType.userProfile:
        if (hit.objectId.trim().isNotEmpty) {
          context.push(AppRoutePaths.userProfile(username: hit.objectId));
        }
        return;
      case SearchObjectType.contentPost:
        unawaited(_openPost(hit.objectId));
        return;
      case SearchObjectType.integrationLocationPoi:
      case SearchObjectType.tag:
      case SearchObjectType.webDocument:
        return;
    }
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
      if (_activeTabId == _tabXiaoqu) {
        _xiaoquResult = null;
      } else {
        _groupResults = const <SearchHit>[];
        _messageResults = const <SearchHit>[];
        _contactResults = const <SearchHit>[];
        _locationResults = const <SearchHit>[];
        _userResults = const <SearchHit>[];
        _contentResults = const <PostSearchItemView>[];
        _degradeSignals = const <SearchDegradeSignal>[];
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
        final groupResponse = await _guardedSearchResponse(
          _loadGroupResponse(trimmedQuery),
        );
        final messageResponse = await _guardedSearchResponse(
          _loadMessageResponse(trimmedQuery),
        );
        final contactResponse = await _guardedSearchResponse(
          _loadContactResponse(trimmedQuery),
        );
        final locationResponse = await _guardedSearchResponse(
          _loadLocationResponse(trimmedQuery),
        );
        final userResponse = await _guardedSearchResponse(
          _loadUserResponse(trimmedQuery),
        );
        final contentResponse = await _guardedSearchResponse(
          _loadContentResponse(trimmedQuery),
        );
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _groupResults = _groupHitsFromResponse(groupResponse);
          _messageResults = _messageHitsFromResponse(messageResponse);
          _contactResults = _contactHitsFromResponse(contactResponse);
          _locationResults = _locationHitsFromResponse(locationResponse);
          _userResults = _userHitsFromResponse(userResponse);
          _contentResults = _contentItemsFromResponse(contentResponse);
          _degradeSignals = <SearchDegradeSignal>[
            ...groupResponse.degradeSignals,
            ...messageResponse.degradeSignals,
            ...contactResponse.degradeSignals,
            ...locationResponse.degradeSignals,
            ...userResponse.degradeSignals,
            ...contentResponse.degradeSignals,
          ];
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
        _degradeSignals =
            response?.degradeSignals ?? const <SearchDegradeSignal>[];
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
    final results = _hitsFromResponse(response)
        .where((hit) => hit.objectType == SearchObjectType.contentPost)
        .map(
          (hit) =>
              hit.asContentPostItem ??
              PostSearchItemView.fromMap(hit.payload.toWireMap()),
        )
        .toList(growable: false);
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
    return results.take(12).toList(growable: false);
  }

  Iterable<SearchHit> _hitsFromResponse(SearchResponse response) {
    if (response.hits.isNotEmpty) {
      return response.hits;
    }
    return response.sections.expand((section) => section.hits);
  }

  List<SearchHit> get _connectedGroupHits => _groupResults
      .where((hit) => hit.objectType == SearchObjectType.circleGroup)
      .toList(growable: false);

  List<SearchHit> get _discoveryGroupHits => _groupResults
      .where((hit) => hit.objectType == SearchObjectType.circleCircle)
      .toList(growable: false);

  List<SearchHit> get _connectedLocationHits => const <SearchHit>[];

  List<SearchHit> get _discoveryLocationHits => _locationResults;

  List<SearchHit> get _connectedUserHits => _userResults
      .where((hit) {
        final view = SocialRelationSearchItemView.fromMap(
          hit.payload.toWireMap(),
        );
        return view.relationshipCapability.canOpenConversation ||
            view.relationshipCapability.canUnfollow;
      })
      .toList(growable: false);

  List<SearchHit> get _discoveryUserHits => _userResults
      .where((hit) => !_connectedUserHits.contains(hit))
      .toList(growable: false);

  List<PostSearchItemView> get _connectedContentItems =>
      _contentResults.take(2).toList(growable: false);

  List<PostSearchItemView> get _discoveryContentItems => _contentResults
      .skip(_connectedContentItems.length)
      .toList(growable: false);

  int get _discoveryResultCount =>
      _discoveryGroupHits.length +
      _discoveryLocationHits.length +
      _discoveryUserHits.length +
      _discoveryContentItems.length;

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

  Future<SearchResponse> _loadMessageResponse(String query) {
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{
              SearchObjectType.chatConversation,
              SearchObjectType.chatMessage,
            },
            limit: 12,
          ),
        );
  }

  List<SearchHit> _messageHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.chatConversation ||
              hit.objectType == SearchObjectType.chatMessage,
        )
        .toList(growable: false);
  }

  Future<SearchResponse> _loadContactResponse(String query) {
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{SearchObjectType.chatContact},
            limit: 12,
          ),
        );
  }

  List<SearchHit> _contactHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where((hit) => hit.objectType == SearchObjectType.chatContact)
        .toList(growable: false);
  }

  Future<SearchResponse> _loadLocationResponse(String query) {
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{
              SearchObjectType.integrationLocationPoi,
            },
            limit: 12,
          ),
        );
  }

  List<SearchHit> _locationHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where(
          (hit) => hit.objectType == SearchObjectType.integrationLocationPoi,
        )
        .toList(growable: false);
  }

  Future<SearchResponse> _loadUserResponse(String query) {
    return ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{SearchObjectType.userProfile},
            limit: 12,
          ),
        );
  }

  List<SearchHit> _userHitsFromResponse(SearchResponse response) {
    return _hitsFromResponse(response)
        .where((hit) => hit.objectType == SearchObjectType.userProfile)
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

  void _openGroup(_GroupResultCardModel group) {
    if (group.circleId.trim().isEmpty) {
      return;
    }
    context.push(
      AppRoutePaths.circleDetail(id: group.circleId),
      extra: const CircleDetailPageRouteExtra(
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

class _DiscoveryGroupBlock extends StatelessWidget {
  const _DiscoveryGroupBlock({
    required this.title,
    required this.description,
    required this.count,
    required this.isDark,
    required this.child,
  });

  final String title;
  final String description;
  final int count;
  final bool isDark;
  final Widget child;

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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            Expanded(
              child: Text(
                title,
                style: TextStyle(
                  fontSize: _SearchResultTokens.sectionTitleSize,
                  fontWeight: _SearchResultTokens.sectionTitleWeight,
                  color: fgPrimary,
                ),
              ),
            ),
            Text(
              '$count',
              style: TextStyle(
                fontSize: AppTypography.iosCaption1,
                color: fgSecondary,
              ),
            ),
          ],
        ),
        if (description.trim().isNotEmpty) ...[
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            description,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
        SizedBox(height: AppSpacing.intraGroupSm),
        child,
      ],
    );
  }
}

class _IntersectionOverviewCard extends StatelessWidget {
  const _IntersectionOverviewCard({
    required this.isDark,
    required this.sharedInterestCount,
    required this.sharedCircleCount,
    required this.sharedFollowingCount,
    required this.sharedDiscussionCount,
  });

  final bool isDark;
  final int sharedInterestCount;
  final int sharedCircleCount;
  final int sharedFollowingCount;
  final int sharedDiscussionCount;

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
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Row(
          children: [
            _IntersectionMetric(label: '共同兴趣', value: sharedInterestCount),
            _IntersectionMetric(label: '共同圈子', value: sharedCircleCount),
            _IntersectionMetric(label: '共同关注', value: sharedFollowingCount),
            _IntersectionMetric(label: '共同讨论', value: sharedDiscussionCount),
          ],
        ),
      ),
    );
  }
}

class _IntersectionMetric extends StatelessWidget {
  const _IntersectionMetric({required this.label, required this.value});

  final String label;
  final int value;

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
    return Expanded(
      child: Column(
        children: [
          Text(
            '$value',
            style: TextStyle(
              fontSize: _SearchResultTokens.sectionTitleSize,
              fontWeight: _SearchResultTokens.sectionTitleWeight,
              color: fgPrimary,
            ),
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          Text(
            label,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }
}

class _CompactHitCard extends StatelessWidget {
  const _CompactHitCard({
    required this.hit,
    required this.isDark,
    required this.fallbackIcon,
    required this.onTap,
    this.reasonLabel,
  });

  final SearchHit hit;
  final bool isDark;
  final IconData fallbackIcon;
  final VoidCallback onTap;
  final String? reasonLabel;

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
    final isPerson = fallbackIcon == CupertinoIcons.person_crop_circle_fill;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(
          AppSpacing.contentPreviewCornerRadius,
        ),
        border: Border.all(color: border),
      ),
      child: CupertinoButton(
        padding: EdgeInsets.all(AppSpacing.intraGroupSm),
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: isPerson
                  ? AppSpacing.avatarUserMd
                  : AppSpacing.avatarUserLg,
              height: isPerson
                  ? AppSpacing.avatarUserMd
                  : AppSpacing.avatarUserLg,
              decoration: BoxDecoration(
                color: AppColors.primaryColor.withValues(alpha: 0.1),
                shape: isPerson ? BoxShape.circle : BoxShape.rectangle,
                borderRadius: isPerson
                    ? null
                    : BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Icon(
                fallbackIcon,
                color: AppColors.primaryColor,
                size: AppSpacing.iconMedium,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              hit.title,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: _SearchResultTokens.cardTitleSize,
                fontWeight: _SearchResultTokens.bodyWeight,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
            Text(
              reasonLabel ?? hit.subtitle ?? hit.snippet ?? '相关结果',
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption2,
                color: fgSecondary,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _DiscoverySectionBucket {
  _DiscoverySectionBucket(this.sections);

  final List<Widget> sections;

  _DiscoverySectionBucket copy() {
    return _DiscoverySectionBucket(List<Widget>.of(sections));
  }
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
