import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/constants/assistant_text_constants.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show CircleDiscoveryFeedQuery, CircleDiscoveryFeedScope;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/navigation/centered_scrollable_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_navigation.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_order.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_media_viewer_wiring.dart';
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_wire.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_entity_bridge_strip.dart';
import 'package:quwoquan_app/core/models/circle_detail_page_route_extra.dart';
import 'package:quwoquan_app/ui/discovery/services/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';

part 'home_circles_hub_page_widgets.dart';

class CirclesHubPage extends ConsumerStatefulWidget {
  const CirclesHubPage({super.key, this.onPrimaryOverflowSwipe});

  final ValueChanged<TabSwipeDirection>? onPrimaryOverflowSwipe;

  @override
  ConsumerState<CirclesHubPage> createState() => _CirclesHubPageState();
}

const double _homeCircleCoverAspectRatio = 4 / 3;
const int _maxHomeCircleRailItems = 10;

TextStyle _homeCircleRailTitleTextStyle() {
  return const TextStyle(
    fontSize: AppTypography.secondary,
    fontWeight: AppTypography.medium,
  );
}

TextStyle _homeCircleRailMetaTextStyle() {
  return const TextStyle(fontSize: AppTypography.xs);
}

double _measureSingleLineTextHeight(BuildContext context, TextStyle style) {
  final painter = TextPainter(
    text: TextSpan(text: 'Hg', style: style),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    maxLines: 1,
  )..layout();
  return painter.height;
}

enum _HomeCirclesModuleTab { recommended, mine }

final class _CirclesHubFeedPage {
  const _CirclesHubFeedPage({
    required this.circles,
    required this.items,
    required this.loadedAt,
    this.nextCursor,
  });

  final List<CircleDto> circles;
  final List<CircleHubFeedPostEntry> items;
  final DateTime loadedAt;
  final String? nextCursor;
}

class _CirclesHubPageState extends ConsumerState<CirclesHubPage> {
  String _activeCategoryId = '';
  _HomeCirclesModuleTab _activeModuleTab = _HomeCirclesModuleTab.recommended;
  final Map<String, String> _activeSubCategoryIdsByCategory =
      <String, String>{};
  final GlobalKey _categoryBarKey = GlobalKey();
  final ScrollController _scrollController = ScrollController();
  final Map<String, _CirclesHubFeedPage> _feedPages =
      <String, _CirclesHubFeedPage>{};
  final Set<String> _loadingFeedKeys = <String>{};
  late List<CircleHubFeedPostEntry> _circleFeedItems;
  // 分类配置的唯一真相源是 metadata 投影的 generated 常量。
  final Map<String, CircleCategoryTabConfigDto> _categoryConfig =
      CircleCategoryTabDefaults.remoteStyleFallback;
  List<CircleDto> _hubCircleDtos = [];
  bool _isBootstrapping = true;
  UiErrorSemantic? _pageErrorSemantic;
  int _bootstrapGeneration = 0;

  // R20 页面曝光/停留：hub 属列表页，以稳定页面 id 走行为通道（同全局搜索页模式）。
  static const String _hubPageContentId = 'home_circles_hub';
  late final DateTime _pageEnteredAt;
  ContentBehaviorTracker? _behaviorTracker;

  @override
  void initState() {
    super.initState();
    _pageEnteredAt = DateTime.now();
    _circleFeedItems = [];
    _scrollController.addListener(_loadMoreWhenNeeded);
    unawaited(_loadActiveFeed());
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _behaviorTracker = ref.read(contentBehaviorTrackerProvider);
      _behaviorTracker!.trackImpression(
        _hubPageContentId,
        contentType: 'circle_hub_page',
        referralSource: ReferralSource.organicFeed,
      );
    });
  }

  @override
  void dispose() {
    _scrollController
      ..removeListener(_loadMoreWhenNeeded)
      ..dispose();
    final tracker = _behaviorTracker;
    if (tracker != null) {
      tracker.trackDwell(
        _hubPageContentId,
        durationSeconds:
            DateTime.now().difference(_pageEnteredAt).inMilliseconds / 1000.0,
        contentType: 'circle_hub_page',
        referralSource: ReferralSource.organicFeed,
      );
    }
    super.dispose();
  }

  void _loadMoreWhenNeeded() {
    if (!_scrollController.hasClients ||
        _scrollController.position.extentAfter > AppSpacing.containerMd) {
      return;
    }
    unawaited(_loadActiveFeed(loadMore: true));
  }

  String _feedPageKey({
    required CircleDiscoveryFeedScope scope,
    required String categoryId,
    required String subCategoryId,
  }) {
    return '${scope.wireValue}|$categoryId|$subCategoryId|recommended';
  }

  Future<void> _loadActiveFeed({bool loadMore = false}) async {
    final requestGeneration = ++_bootstrapGeneration;
    final categoryId = _effectiveActiveCategoryId;
    final subCategoryId = _effectiveSubCategoryId(
      categoryId,
      _visibleSubCategoriesFor(categoryId),
    );
    final scope = _activeModuleTab == _HomeCirclesModuleTab.mine
        ? CircleDiscoveryFeedScope.mine
        : CircleDiscoveryFeedScope.recommended;
    final key = _feedPageKey(
      scope: scope,
      categoryId: categoryId,
      subCategoryId: subCategoryId,
    );
    if (_loadingFeedKeys.contains(key)) {
      return;
    }
    final previous = _feedPages[key];
    if (loadMore &&
        (previous == null || (previous.nextCursor?.isEmpty ?? true))) {
      return;
    }
    if (!loadMore &&
        previous != null &&
        DateTime.now().difference(previous.loadedAt) <
            const Duration(seconds: 60)) {
      if (mounted) {
        setState(() {
          _circleFeedItems = previous.items;
          _hubCircleDtos = previous.circles;
          _isBootstrapping = false;
          _pageErrorSemantic = null;
        });
      }
      return;
    }
    _loadingFeedKeys.add(key);
    if (mounted && !loadMore && previous == null) {
      setState(() {
        _isBootstrapping = true;
        _pageErrorSemantic = null;
      });
    }

    try {
      // Mine 在入口层经 AuthGate 限制；只在已登录的实际切换后发送第二个 scope。
      if (scope == CircleDiscoveryFeedScope.mine) {
        final persona = await ref.read(activePersonaContextProvider.future);
        if (persona.personaId.trim().isEmpty) {
          return;
        }
      }
      final page = await ref
          .read(circlesListDiscoveryFeedQueryProvider)
          .listDiscoveryFeed(
            CircleDiscoveryFeedQuery(
              category: categoryId,
              subCategory: subCategoryId,
              scope: scope,
              cursor: loadMore ? previous?.nextCursor : null,
              limit: 20,
            ),
          );
      final circleMapper = ref.read(circleProjectionMapperProvider);
      final currentCircles = loadMore
          ? <CircleDto>[...?previous?.circles]
          : <CircleDto>[];
      final currentItems = loadMore
          ? <CircleHubFeedPostEntry>[...?previous?.items]
          : <CircleHubFeedPostEntry>[];
      final circlesById = <String, CircleDto>{
        for (final circle in currentCircles) circle.id: circle,
      };
      final itemsByPlacementId = <String, CircleHubFeedPostEntry>{
        for (final entry in currentItems) entry.placementId: entry,
      };
      for (final circle in page.circles) {
        final dto = circleMapper.toDto(circle);
        circlesById[dto.id] = dto;
      }
      for (final projection in page.items) {
        final entry = CircleHubFeedPostEntry.fromProjection(
          projection: projection,
        );
        itemsByPlacementId[entry.placementId] = entry;
      }
      final resolved = _CirclesHubFeedPage(
        circles: circlesById.values.toList(growable: false),
        items: itemsByPlacementId.values.toList(growable: false),
        loadedAt: DateTime.now(),
        nextCursor: page.nextCursor,
      );
      _feedPages[key] = resolved;
      if (mounted && requestGeneration == _bootstrapGeneration) {
        setState(() {
          _circleFeedItems = resolved.items;
          _hubCircleDtos = resolved.circles;
          _isBootstrapping = false;
          _pageErrorSemantic = null;
        });
      }
    } catch (error) {
      if (mounted && requestGeneration == _bootstrapGeneration) {
        setState(() {
          if (!loadMore) {
            _circleFeedItems = <CircleHubFeedPostEntry>[];
            _hubCircleDtos = <CircleDto>[];
          }
          _isBootstrapping = false;
          _pageErrorSemantic = runtimeErrorSemantic(
            context,
            error: error,
            category: UiErrorCategory.pageLoad,
            scope: UiErrorScope.page,
          );
        });
      }
    } finally {
      _loadingFeedKeys.remove(key);
    }
  }

  List<Map<String, String>> get _allCategories {
    return resolveCircleCategoryTabEntries(_categoryConfig)
        .map(
          (entry) => <String, String>{
            'id': entry.key,
            'label': entry.value.label.isNotEmpty
                ? entry.value.label
                : entry.key,
          },
        )
        .toList(growable: false);
  }

  List<String> get _visibleCategoryIds =>
      _allCategories.map((entry) => entry['id']!).toList(growable: false);

  String get _effectiveActiveCategoryId {
    final visibleCategoryIds = _visibleCategoryIds;
    if (visibleCategoryIds.isEmpty) {
      return _allCategories.isNotEmpty ? _allCategories.first['id']! : '';
    }
    return visibleCategoryIds.contains(_activeCategoryId)
        ? _activeCategoryId
        : visibleCategoryIds.first;
  }

  List<MapEntry<String, CircleCategoryTabConfigDto>> get _visibleCategories {
    return _visibleCategoryIds
        .map((id) {
          final config =
              _categoryConfig[id] ??
              CircleCategoryTabDefaults.remoteStyleFallback[id];
          if (config == null) {
            return null;
          }
          return MapEntry(id, config);
        })
        .whereType<MapEntry<String, CircleCategoryTabConfigDto>>()
        .toList(growable: false);
  }

  List<String> _visibleSubCategoriesFor(String categoryId) {
    final config =
        _categoryConfig[categoryId] ??
        CircleCategoryTabDefaults.remoteStyleFallback[categoryId];
    if (config == null) {
      return const <String>[];
    }
    return config.subCategories
        .where((item) => item.trim().isNotEmpty)
        .toList(growable: false);
  }

  String _effectiveSubCategoryId(
    String categoryId,
    List<String> subCategories,
  ) {
    if (subCategories.isEmpty) {
      return '';
    }
    final selected = _activeSubCategoryIdsByCategory[categoryId]?.trim();
    if (selected != null && subCategories.contains(selected)) {
      return selected;
    }
    return subCategories.first;
  }

  void _setActiveSubCategory(String categoryId, String subCategoryId) {
    setState(() {
      _activeSubCategoryIdsByCategory[categoryId] = subCategoryId;
    });
    unawaited(_loadActiveFeed());
  }

  void _handleCategorySwipeDragEnd(DragEndDetails details) {
    final direction = TabSwipeSwitchRegion.directionFromDragEnd(details);
    if (direction == null) {
      return;
    }
    _handleCategorySwipe(direction);
  }

  void _handleCategorySwipe(TabSwipeDirection direction) {
    if (!_isCategoryBarVisible()) {
      widget.onPrimaryOverflowSwipe?.call(direction);
      return;
    }
    final visibleCategoryIds = _visibleCategoryIds;
    final currentIndex = visibleCategoryIds.indexOf(_effectiveActiveCategoryId);
    if (currentIndex < 0) {
      widget.onPrimaryOverflowSwipe?.call(direction);
      return;
    }
    final nextIndex = currentIndex + direction.delta;
    if (nextIndex < 0 || nextIndex >= visibleCategoryIds.length) {
      widget.onPrimaryOverflowSwipe?.call(direction);
      return;
    }
    setState(() {
      _activeCategoryId = visibleCategoryIds[nextIndex];
    });
    unawaited(_loadActiveFeed());
  }

  bool _isCategoryBarVisible() {
    final renderObject = _categoryBarKey.currentContext?.findRenderObject();
    if (renderObject is! RenderBox ||
        !renderObject.attached ||
        !renderObject.hasSize) {
      return false;
    }
    final top = renderObject.localToGlobal(Offset.zero).dy;
    final bottom = top + renderObject.size.height;
    return bottom > 0 && top < MediaQuery.sizeOf(context).height;
  }

  List<CircleDto> _moduleCirclesFor(_HomeCirclesModuleTab _, String _) {
    // scope/category/sort 已由聚合读模型冻结；客户端只截断首屏 rail，不重排或重过滤。
    return _hubCircleDtos
        .take(_maxHomeCircleRailItems - 1)
        .toList(growable: false);
  }

  List<_HomeCircleStoryItem> _moduleStoriesFor(
    _HomeCirclesModuleTab tab,
    String categoryId,
  ) {
    final circleById = <String, CircleDto>{
      for (final circle in _hubCircleDtos) circle.id: circle,
    };
    final pool = _filteredLevelOnePosts(tab, categoryId)
        .map((entry) {
          final circleId = entry.circleId;
          final sourceCircle = circleById[circleId];
          final circleName = sourceCircle?.name ?? '';
          final title = entry.title.isNotEmpty
              ? entry.title
              : (entry.bodyText.isNotEmpty ? entry.bodyText : circleName);
          return _HomeCircleStoryItem(
            id: entry.postId,
            title: title,
            subtitle: circleName,
            imageUrl: entry.coverUrl.isNotEmpty
                ? entry.coverUrl
                : sourceCircle?.coverUrl ?? '',
            circleId: circleId,
            categoryId: sourceCircle?.category ?? 'all',
            typeLabel: hubCircleStoryTypeLabel(entry.post),
            isMine: tab == _HomeCirclesModuleTab.mine,
            feedEntry: entry,
          );
        })
        .toList(growable: false);
    return pool.take(3).toList(growable: false);
  }

  List<CircleHubFeedPostEntry> _filteredLevelOnePosts(
    _HomeCirclesModuleTab _,
    String _, {
    String? subCategoryId,
  }) => _circleFeedItems;

  bool _supportsViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }

  bool _isVideoPost(PostBaseDto post) {
    return post.isVideoLike;
  }

  Future<void> _openCircleFeedViewer(
    BuildContext context,
    CircleHubFeedPostEntry tapped,
    List<CircleHubFeedPostEntry> sourceItems,
  ) async {
    final viewerEntries = sourceItems
        .where((item) => _supportsViewer(item.post))
        .toList(growable: false);
    if (viewerEntries.isEmpty) return;
    final tappedDto = tapped.post;
    if (!_supportsViewer(tappedDto)) return;
    final viewerDtos = viewerEntries
        .map((entry) => entry.post)
        .toList(growable: false);
    final mediaRows = circleHubMediaViewerRowsByPostId(viewerEntries);
    final initialIndex = viewerDtos
        .indexWhere((item) => item.id == tappedDto.id)
        .clamp(0, viewerDtos.length - 1);
    final interactionSnapshot = buildMediaViewerInteractionSnapshot(
      posts: viewerDtos,
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
        workId: tappedDto.id,
        filter: _isVideoPost(tappedDto)
            ? 'video'
            : (tappedDto.isArticleLike ? 'article' : 'image'),
        source: 'circle',
        index: '$initialIndex',
      ),
      extra: MediaViewerExtra(
        posts: viewerDtos
            .map(ContentSurfaceViewMapper.fromDto)
            .toList(growable: false),
        dtoPosts: viewerDtos,
        initialIndex: initialIndex,
        source: 'circle',
        circleId: tapped.circleId.isEmpty ? null : tapped.circleId,
        rawPostsById: mediaRows,
        interactionSnapshot: interactionSnapshot,
        referralSource: ReferralSource.circlePost,
        feedRequestId: navFeedRequestId,
      ),
    );
    if (result is MediaViewerResult) {
      applyMediaViewerResultToInteractionState(ref, result);
      setState(() {
        CircleHubFeedPostEntry.applyResultToList(_circleFeedItems, result);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(effectiveIsDarkProvider);
    if (_isBootstrapping) {
      return Material(
        type: MaterialType.transparency,
        child: SafeArea(
          top: false,
          bottom: false,
          child: AppRequestFeedback.section(),
        ),
      );
    }
    if (_pageErrorSemantic != null) {
      return Material(
        type: MaterialType.transparency,
        child: SafeArea(
          top: false,
          bottom: false,
          child: AppPageErrorState(
            semantic: ensureRetryUiErrorSemantic(_pageErrorSemantic!),
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                await _loadActiveFeed();
              }
            },
          ),
        ),
      );
    }
    final categories = _visibleCategories;
    final effectiveActiveCategoryId = _effectiveActiveCategoryId;
    final activeSubCategories = _visibleSubCategoriesFor(
      effectiveActiveCategoryId,
    );
    final effectiveActiveSubCategoryId = _effectiveSubCategoryId(
      effectiveActiveCategoryId,
      activeSubCategories,
    );
    final activeCategory = categories.firstWhere(
      (entry) => entry.key == effectiveActiveCategoryId,
      orElse: () => categories.first,
    );
    if (effectiveActiveCategoryId != _activeCategoryId) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) return;
        setState(() {
          _activeCategoryId = effectiveActiveCategoryId;
        });
      });
    }
    final circles = _moduleCirclesFor(
      _activeModuleTab,
      effectiveActiveCategoryId,
    );
    final stories = _moduleStoriesFor(
      _activeModuleTab,
      effectiveActiveCategoryId,
    );
    final levelOnePosts = _filteredLevelOnePosts(
      _activeModuleTab,
      effectiveActiveCategoryId,
      subCategoryId: effectiveActiveSubCategoryId,
    );
    final activeScope = _activeModuleTab == _HomeCirclesModuleTab.mine
        ? CircleDiscoveryFeedScope.mine
        : CircleDiscoveryFeedScope.recommended;
    final activeFeedKey = _feedPageKey(
      scope: activeScope,
      categoryId: effectiveActiveCategoryId,
      subCategoryId: effectiveActiveSubCategoryId,
    );
    final activeFeedPage = _feedPages[activeFeedKey];
    final isLoadingMore = _loadingFeedKeys.contains(activeFeedKey);
    final hasMore = activeFeedPage?.nextCursor?.isNotEmpty ?? false;

    return Material(
      type: MaterialType.transparency,
      child: SafeArea(
        top: false,
        bottom: false,
        child: Stack(
          children: [
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                _CirclesHubTopBar(
                  isDark: isDark,
                  onSearchTap: () => GlobalSearchLauncher.open(
                    context,
                    initialScope: GlobalSearchScope.circles.searchScope,
                  ),
                  onAssistantTap: () =>
                      GlobalAssistantLauncher.open(context, ref),
                ),
                KeyedSubtree(
                  key: _categoryBarKey,
                  child: _CirclesPrimaryCategoryTabBar(
                    isDark: isDark,
                    categories: categories,
                    activeCategoryId: effectiveActiveCategoryId,
                    onCategoryTap: (index) {
                      final nextCategoryId = categories[index].key;
                      if (nextCategoryId == effectiveActiveCategoryId) {
                        return;
                      }
                      setState(() {
                        _activeCategoryId = nextCategoryId;
                      });
                      unawaited(_loadActiveFeed());
                    },
                    onHorizontalDragEnd: _handleCategorySwipeDragEnd,
                  ),
                ),
                Expanded(
                  child: TabSwipeSwitchRegion(
                    onSwipe: _handleCategorySwipe,
                    child: CustomScrollView(
                      key: TestKeys.homeCirclesScrollView,
                      controller: _scrollController,
                      physics: const BouncingScrollPhysics(
                        parent: AlwaysScrollableScrollPhysics(),
                      ),
                      slivers: [
                        SliverToBoxAdapter(
                          child: _CirclesGlobalHeader(
                            isDark: isDark,
                            activeModuleTab: _activeModuleTab,
                            circles: circles,
                            stories: stories,
                            onStoryTap: (item, items) => _openCircleFeedViewer(
                              context,
                              item.feedEntry,
                              items
                                  .map((entry) => entry.feedEntry)
                                  .toList(growable: false),
                            ),
                            onModuleTabChanged: (nextTab) {
                              if (nextTab == _activeModuleTab) return;
                              if (nextTab == _HomeCirclesModuleTab.mine &&
                                  !AuthGate.isAuthenticated(ref)) {
                                runWhenLoggedIn(
                                  ref,
                                  context,
                                  AuthGateReason.followingFeed,
                                  () async {
                                    if (!mounted) return;
                                    setState(() {
                                      _activeModuleTab = nextTab;
                                    });
                                    await _loadActiveFeed();
                                  },
                                  dismissFallback: AppRoutePaths.home,
                                  dismissPolicy:
                                      LoginDismissPolicy.safeFallback,
                                );
                                return;
                              }
                              setState(() {
                                _activeModuleTab = nextTab;
                              });
                              unawaited(_loadActiveFeed());
                            },
                            onSeeMoreTap: () {
                              final uri = Uri(
                                path: AppRoutePaths.circles,
                                queryParameters: <String, String>{
                                  'category': effectiveActiveCategoryId,
                                },
                              );
                              context.push(uri.toString());
                            },
                          ),
                        ),
                        SliverToBoxAdapter(
                          child: HomeCirclesEntityBridgeStrip(
                            isDark: isDark,
                            onEntityTap: (query) {
                              context.push(
                                AppRoutePaths.suggestHomepage(query: query),
                              );
                            },
                          ),
                        ),
                        if (activeSubCategories.isNotEmpty)
                          SliverPersistentHeader(
                            pinned: true,
                            delegate: _StickyTabBarDelegate(
                              extent: _CirclesSubCategoryBar.extent(context),
                              child: _CirclesSubCategoryBar(
                                isDark: isDark,
                                categoryId: effectiveActiveCategoryId,
                                subCategories: activeSubCategories,
                                activeSubCategoryId:
                                    effectiveActiveSubCategoryId,
                                onSubCategoryTap: (subCategoryId) {
                                  _setActiveSubCategory(
                                    effectiveActiveCategoryId,
                                    subCategoryId,
                                  );
                                },
                              ),
                            ),
                          ),
                        HomeCirclesCategoryTab(
                          key: ValueKey(
                            'home-circles-category-$effectiveActiveCategoryId',
                          ),
                          categoryId: effectiveActiveCategoryId,
                          posts: levelOnePosts,
                          onPostTap: (tapped, sourceItems) =>
                              _openCircleFeedViewer(
                                context,
                                tapped,
                                sourceItems,
                              ),
                          label: activeCategory.value.label.isNotEmpty
                              ? activeCategory.value.label
                              : effectiveActiveCategoryId,
                        ),
                        if (hasMore || isLoadingMore)
                          SliverToBoxAdapter(
                            child: Padding(
                              padding: const EdgeInsets.all(
                                AppSpacing.containerMd,
                              ),
                              child: Center(
                                child: isLoadingMore
                                    ? AppRequestFeedback.inline()
                                    : const SizedBox.shrink(),
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
