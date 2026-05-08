import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/integration/location_poi_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_contract.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/search/search_registry.g.dart';
import 'package:quwoquan_app/cloud/services/assistant/assistant_repository.dart';
import 'package:quwoquan_app/cloud/runtime/generated/entity/homepage_models.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/search_repository.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/search/services/search_network_results_media_wiring.dart';
import 'package:quwoquan_app/ui/entity/widgets/homepage_summary_card.dart';

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

  late final TextEditingController _controller;
  late final FocusNode _focusNode;
  late String _query;
  late String _activeTabId;
  List<_SearchNetworkTab> _tabs = const [];
  Timer? _debounceTimer;
  int _requestToken = 0;
  bool _isLoading = false;
  String? _errorText;
  AssistantSearchResultView? _xiaoquResult;
  List<PostSearchItemView> _contentResults = const <PostSearchItemView>[];
  List<HomepageSummary> _homepageResults = const <HomepageSummary>[];
  List<SearchHit> _groupResults = const <SearchHit>[];
  List<LocationPoiDto> _locationResults = const <LocationPoiDto>[];

  @override
  void initState() {
    super.initState();
    _query = widget.launchContext.prefilledQuery.trim();
    _controller = TextEditingController(text: _query);
    _focusNode = FocusNode();
    _tabs = _buildBaseTabs();
    final initialTabId = widget.launchContext.initialNetworkTabId;
    _activeTabId = _tabs.any((tab) => tab.id == initialTabId)
        ? initialTabId!
        : _tabs.first.id;
    unawaited(_appendCategoryTabsFromRepo());
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
      contentPadding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerXs,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                onPressed: _handleClose,
                child: Icon(
                  CupertinoIcons.chevron_back,
                  color: fgSecondary,
                  size: AppSpacing.iconLarge,
                ),
              ),
              SizedBox(width: AppSpacing.containerSm),
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
                ),
              ),
            ],
          ),
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
        ],
      ),
    );
  }

  List<_SearchNetworkTab> _buildBaseTabs() {
    return <_SearchNetworkTab>[
      const _SearchNetworkTab(
        id: 'xiaoqu',
        label: '小趣搜',
        description: '从圈子内容和创作里快速梳理线索',
      ),
      const _SearchNetworkTab(
        id: 'homepages',
        label: '主页',
        description: '搜索共享主页并进入详情',
      ),
      _SearchNetworkTab(
        id: 'groups',
        label: SearchRegistry.sectionById('groups')?.title ?? '群组',
        description: '搜索圈子与群组结果',
      ),
      _SearchNetworkTab(
        id: 'locations',
        label: SearchRegistry.sectionById('locations')?.title ?? '位置',
        description: '搜索站内可挂载的位置结果',
      ),
    ];
  }

  Future<void> _appendCategoryTabsFromRepo() async {
    try {
      final cfg = await ref
          .read(circleRepositoryProvider)
          .getCircleCategoryConfig();
      if (!mounted) {
        return;
      }
      final extra = <_SearchNetworkTab>[];
      for (final entry in cfg.entries) {
        final CircleCategoryTabConfigDto value = entry.value;
        extra.add(
          _SearchNetworkTab(
            id: entry.key,
            label: value.label.isNotEmpty ? value.label : entry.key,
            description: value.desc ?? '',
          ),
        );
      }
      final merged = [..._buildBaseTabs(), ...extra];
      final prevActive = _activeTabId;
      final want = widget.launchContext.initialNetworkTabId;
      var nextActive = prevActive;
      if (want != null && merged.any((t) => t.id == want)) {
        nextActive = want;
      } else if (!merged.any((t) => t.id == prevActive)) {
        nextActive = merged.first.id;
      }
      setState(() {
        _tabs = merged;
        _activeTabId = nextActive;
      });
      if (nextActive != prevActive) {
        _scheduleRefresh(immediate: true);
      }
    } catch (_) {}
  }

  List<Widget> _buildResultChildren({
    required bool isDark,
    required Color fgSecondary,
    required _SearchNetworkTab activeTab,
  }) {
    if (_activeTabId == 'xiaoqu') {
      return <Widget>[
        _XiaoquSummaryCard(
          query: _query,
          result: _xiaoquResult,
          isDark: isDark,
        ),
        SizedBox(height: AppSpacing.containerMd),
        if (_isLoading)
          _StatusMessage(text: '小趣搜正在整理网络结果', isDark: isDark, loading: true)
        else if (_errorText != null)
          _StatusMessage(text: _errorText!, isDark: isDark)
        else if ((_xiaoquResult?.citations?.length ?? 0) == 0)
          _StatusMessage(text: '暂时没有找到可引用的网络结果', isDark: isDark)
        else
          ..._buildXiaoquCitationTiles(
            isDark: isDark,
            fgSecondary: fgSecondary,
          ),
      ];
    }

    if (_activeTabId == 'homepages') {
      return <Widget>[
        _CategorySummaryCard(
          title: activeTab.label,
          description: activeTab.description,
          count: _homepageResults.length,
          isDark: isDark,
        ),
        if (_isLoading)
          _StatusMessage(text: '正在加载共享主页', isDark: isDark, loading: true)
        else if (_errorText != null)
          _StatusMessage(text: _errorText!, isDark: isDark)
        else if (_homepageResults.isEmpty)
          _StatusMessage(text: '没有找到相关主页', isDark: isDark)
        else
          ..._buildHomepageResultTiles(),
      ];
    }

    if (_activeTabId == 'groups') {
      return <Widget>[
        _CategorySummaryCard(
          title: activeTab.label,
          description: activeTab.description,
          count: _groupResults.length,
          isDark: isDark,
        ),
        if (_isLoading)
          _StatusMessage(text: '正在加载群组结果', isDark: isDark, loading: true)
        else if (_errorText != null)
          _StatusMessage(text: _errorText!, isDark: isDark)
        else if (_groupResults.isEmpty)
          _StatusMessage(text: '没有找到相关群组', isDark: isDark)
        else
          ..._buildGroupResultTiles(isDark: isDark, fgSecondary: fgSecondary),
      ];
    }

    if (_activeTabId == 'locations') {
      return <Widget>[
        _CategorySummaryCard(
          title: activeTab.label,
          description: activeTab.description,
          count: _locationResults.length,
          isDark: isDark,
        ),
        if (_isLoading)
          _StatusMessage(text: '正在加载位置结果', isDark: isDark, loading: true)
        else if (_errorText != null)
          _StatusMessage(text: _errorText!, isDark: isDark)
        else if (_locationResults.isEmpty)
          _StatusMessage(text: '没有找到相关位置', isDark: isDark)
        else
          ..._buildLocationResultTiles(
            isDark: isDark,
            fgSecondary: fgSecondary,
          ),
      ];
    }

    return <Widget>[
      _CategorySummaryCard(
        title: activeTab.label,
        description: activeTab.description,
        count: _contentResults.length,
        isDark: isDark,
      ),
      if (_isLoading)
        _StatusMessage(text: '正在加载网络结果', isDark: isDark, loading: true)
      else if (_errorText != null)
        _StatusMessage(text: _errorText!, isDark: isDark)
      else if (_contentResults.isEmpty)
        _StatusMessage(text: '没有找到相关网络结果', isDark: isDark)
      else
        ..._buildContentResultTiles(isDark: isDark, fgSecondary: fgSecondary),
    ];
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

  List<Widget> _buildContentResultTiles({
    required bool isDark,
    required Color fgSecondary,
  }) {
    final cards = _contentResults
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

  List<Widget> _buildHomepageResultTiles() {
    return <Widget>[
      for (var i = 0; i < _homepageResults.length; i++) ...[
        HomepageSummaryCard(
          key: ValueKey<String>(
            'search_homepage_result_${_homepageResults[i].id}',
          ),
          summary: _homepageResults[i],
          onTap: () => _openHomepage(_homepageResults[i].id),
        ),
        if (i != _homepageResults.length - 1)
          SizedBox(height: AppSpacing.containerSm),
      ],
    ];
  }

  List<Widget> _buildGroupResultTiles({
    required bool isDark,
    required Color fgSecondary,
  }) {
    final cards = _groupResults
        .map(_GroupResultCardModel.fromHit)
        .toList(growable: false);
    return <Widget>[
      for (var i = 0; i < cards.length; i++) ...[
        PostPreviewListTile(
          isDark: isDark,
          title: cards[i].title,
          supportingText: cards[i].supportingText,
          coverUrl: cards[i].coverUrl,
          eyebrowText: cards[i].eyebrowText,
          footer: Text(
            cards[i].footerLabel,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () => _openGroup(cards[i]),
        ),
        if (i != cards.length - 1) SizedBox(height: AppSpacing.containerSm),
      ],
    ];
  }

  List<Widget> _buildLocationResultTiles({
    required bool isDark,
    required Color fgSecondary,
  }) {
    final cards = _locationResults
        .map(_LocationResultCardModel.fromDto)
        .toList(growable: false);
    return <Widget>[
      for (var i = 0; i < cards.length; i++) ...[
        PostPreviewListTile(
          isDark: isDark,
          title: cards[i].title,
          supportingText: cards[i].supportingText,
          coverUrl: '',
          eyebrowText: cards[i].eyebrowText,
          footer: Text(
            cards[i].footerLabel,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
          onTap: () {},
        ),
        if (i != cards.length - 1) SizedBox(height: AppSpacing.containerSm),
      ],
    ];
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
      _errorText = null;
      if (_activeTabId == 'xiaoqu') {
        _xiaoquResult = null;
      } else if (_activeTabId == 'homepages') {
        _homepageResults = const <HomepageSummary>[];
      } else if (_activeTabId == 'groups') {
        _groupResults = const <SearchHit>[];
      } else if (_activeTabId == 'locations') {
        _locationResults = const <LocationPoiDto>[];
      } else {
        _contentResults = const <PostSearchItemView>[];
      }
    });
    try {
      if (_activeTabId == 'xiaoqu') {
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

      if (_activeTabId == 'homepages') {
        final items = trimmedQuery.isEmpty
            ? const <HomepageSummary>[]
            : await _loadHomepageResults(trimmedQuery);
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _homepageResults = items;
          _isLoading = false;
        });
        return;
      }

      if (_activeTabId == 'groups') {
        final items = trimmedQuery.isEmpty
            ? const <SearchHit>[]
            : await _loadGroupResults(trimmedQuery);
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _groupResults = items;
          _isLoading = false;
        });
        return;
      }

      if (_activeTabId == 'locations') {
        final items = trimmedQuery.isEmpty
            ? const <LocationPoiDto>[]
            : await _loadLocationResults(trimmedQuery);
        if (!mounted || token != _requestToken) {
          return;
        }
        setState(() {
          _locationResults = items;
          _isLoading = false;
        });
        return;
      }

      final items = trimmedQuery.isEmpty
          ? const <PostSearchItemView>[]
          : await _loadContentResults(trimmedQuery);
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _contentResults = items;
        _isLoading = false;
      });
    } catch (_) {
      if (!mounted || token != _requestToken) {
        return;
      }
      setState(() {
        _errorText = '网络结果暂时不可用，请稍后重试';
        _isLoading = false;
      });
    }
  }

  Future<List<PostSearchItemView>> _loadContentResults(String query) async {
    final categoryId = _activeTabId == 'all' ? null : _activeTabId;
    final selection = widget.launchContext.searchObjectSelection.normalized();
    final response = await ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{SearchObjectType.contentPost},
            limit: 12,
            categoryId: categoryId,
            contentTypes: selection.contentTypes,
          ),
        );
    final results = response.hits
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

  Future<List<HomepageSummary>> _loadHomepageResults(String query) async {
    final response = await ref
        .read(searchRepositoryProvider)
        .search(
          SearchRequest(
            query: query,
            mode: SearchMode.result,
            objectTypes: const <SearchObjectType>{
              SearchObjectType.entityHomepage,
            },
            limit: 12,
          ),
        );
    return response.hits
        .where((hit) => hit.objectType == SearchObjectType.entityHomepage)
        .map((hit) => HomepageSummary.fromMap(hit.payload.toWireMap()))
        .toList(growable: false);
  }

  Future<List<SearchHit>> _loadGroupResults(String query) async {
    final response = await ref
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
    return response.hits
        .where(
          (hit) =>
              hit.objectType == SearchObjectType.circleGroup ||
              hit.objectType == SearchObjectType.circleCircle,
        )
        .toList(growable: false);
  }

  Future<List<LocationPoiDto>> _loadLocationResults(String query) async {
    final response = await ref
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
    return response.hits
        .where(
          (hit) => hit.objectType == SearchObjectType.integrationLocationPoi,
        )
        .map((hit) => LocationPoiDto.fromMap(hit.payload.toWireMap()))
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
      if (dto.isArticleLike) {
        context.push(AppRoutePaths.articleDetail(id: dto.id));
        return;
      }
      final route = dto.isVideoLike
          ? '/video-viewer/0'
          : '/media-viewer/photo/0';
      final interactionSnapshot = buildMediaViewerInteractionSnapshot(
        posts: <PostBaseDto>[dto],
        discoveryState: ref.read(discoveryStateProvider),
        relationshipState: ref.read(userRelationshipStateProvider),
        postInteractionState: ref.read(postInteractionStateProvider),
      );
      primeMediaViewerInteractionSnapshot(ref, interactionSnapshot);
      final result = await context.push<Object?>(
        route,
        extra: MediaViewerExtra(
          posts: <PostSummaryView>[
            PostSummaryView.fromDto(
              dto,
              surfaceId: PostReadSurfaceId.searchCard,
              wire: raw,
            ),
          ],
          dtoPosts: <PostBaseDto>[dto],
          initialIndex: 0,
          category: dto.isVideoLike
              ? 'video'
              : (dto.identity == 'moment' ? 'moment' : 'photo'),
          source: 'global-search-network',
          rawPostsById: searchNetworkSinglePostMediaRaws(dto: dto, wire: raw),
          interactionSnapshot: interactionSnapshot,
        ),
      );
      if (result is MediaViewerResult) {
        applyMediaViewerResultToInteractionState(ref, result);
      }
    } catch (_) {
      return;
    }
  }

  void _openHomepage(String homepageId) {
    if (homepageId.trim().isEmpty) {
      return;
    }
    context.push(AppRoutePaths.homepageDetail(id: homepageId));
  }

  void _openGroup(_GroupResultCardModel group) {
    if (group.circleId.trim().isEmpty) {
      return;
    }
    context.push(AppRoutePaths.circleDetail(id: group.circleId));
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
                  color: AppColors.primaryColor,
                  size: AppSpacing.iconMedium,
                ),
                SizedBox(width: AppSpacing.intraGroupSm),
                Text(
                  '小趣搜',
                  style: TextStyle(
                    fontSize: AppTypography.iosTitle3,
                    fontWeight: AppTypography.semiBold,
                    color: fgPrimary,
                  ),
                ),
              ],
            ),
            SizedBox(height: AppSpacing.containerSm),
            Text(
              query.trim().isEmpty ? '为你整理了当前热门网络结果' : '正在为你整理“$query”的网络结果',
              style: TextStyle(
                fontSize: AppTypography.iosBody,
                fontWeight: AppTypography.medium,
                color: fgPrimary,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              (result?.summary?.trim().isNotEmpty == true)
                  ? result!.summary!.trim()
                  : '先按圈子频道分类聚合内容，再把最相关的创作和讨论铺开，方便继续筛选。',
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
      footerLabel: footerSegments.isEmpty ? '群组结果' : footerSegments.join(' · '),
      eyebrowText: isCircle ? '圈子' : '群组',
    );
  }
}

class _LocationResultCardModel {
  const _LocationResultCardModel({
    required this.title,
    required this.supportingText,
    required this.footerLabel,
    required this.eyebrowText,
  });

  final String title;
  final String supportingText;
  final String footerLabel;
  final String eyebrowText;

  factory _LocationResultCardModel.fromDto(LocationPoiDto dto) {
    final footerSegments = <String>[
      if (dto.distanceMeters != null) '${dto.distanceMeters} m',
      '${dto.latitude.toStringAsFixed(4)}, ${dto.longitude.toStringAsFixed(4)}',
    ];
    return _LocationResultCardModel(
      title: dto.name,
      supportingText: (dto.address ?? '').trim().isNotEmpty
          ? dto.address!.trim()
          : '站内位置结果',
      footerLabel: footerSegments.join(' · '),
      eyebrowText: '位置',
    );
  }
}
