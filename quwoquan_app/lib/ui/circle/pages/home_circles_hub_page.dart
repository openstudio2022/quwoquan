import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
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
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_media_viewer_wiring.dart';
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_wire.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_entity_bridge_strip.dart';
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

@Deprecated('Use CirclesHubPage instead.')
class HomeCirclesHubPage extends CirclesHubPage {
  const HomeCirclesHubPage({super.key, super.onPrimaryOverflowSwipe});
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

class _CirclesHubPageState extends ConsumerState<CirclesHubPage> {
  static const Set<String> _myCircleIds = <String>{
    'c-photo-owner',
    'c-tech-admin',
    'c1',
    'c2',
    'c3',
    'c-human-1',
  };

  String _activeCategoryId = 'campus';
  _HomeCirclesModuleTab _activeModuleTab = _HomeCirclesModuleTab.recommended;
  final Map<String, String> _activeSubCategoryIdsByCategory =
      <String, String>{};
  final GlobalKey _categoryBarKey = GlobalKey();
  late List<CircleHubFeedPostEntry> _circleFeedItems;
  Map<String, CircleCategoryTabConfigDto> _categoryConfig =
      CircleCategoryTabDefaults.remoteStyleFallback;
  List<CircleDto> _hubCircleDtos = [];
  bool _isBootstrapping = true;
  UiErrorSemantic? _pageErrorSemantic;

  @override
  void initState() {
    super.initState();
    _circleFeedItems = [];
    unawaited(_bootstrapHubData());
  }

  Future<void> _bootstrapHubData() async {
    final repo = ref.read(circleRepositoryProvider);
    if (mounted) {
      setState(() {
        _isBootstrapping = true;
        _pageErrorSemantic = null;
      });
    }
    Object? bootstrapError;
    var nextFeedItems = <CircleHubFeedPostEntry>[];
    var nextCategoryConfig = Map<String, CircleCategoryTabConfigDto>.from(
      CircleCategoryTabDefaults.remoteStyleFallback,
    );
    var nextCircleDtos = <CircleDto>[];
    await Future.wait<void>([
      () async {
        try {
          final feed = await repo.listHomeCircleDiscoveryFeed(limit: 200);
          nextFeedItems = feed
              .map(CircleHubFeedPostEntry.fromPostDto)
              .toList(growable: true);
        } catch (error) {
          bootstrapError ??= error;
          nextFeedItems = <CircleHubFeedPostEntry>[];
        }
      }(),
      () async {
        try {
          final cfg = await repo.getCircleCategoryConfig().timeout(
            const Duration(seconds: 2),
            onTimeout: () => Map<String, CircleCategoryTabConfigDto>.from(
              CircleCategoryTabDefaults.remoteStyleFallback,
            ),
          );
          nextCategoryConfig = Map<String, CircleCategoryTabConfigDto>.from(
            cfg,
          );
        } catch (_) {
          nextCategoryConfig = Map<String, CircleCategoryTabConfigDto>.from(
            CircleCategoryTabDefaults.remoteStyleFallback,
          );
        }
      }(),
      () async {
        try {
          final circlesMaps = await repo.listCircles(limit: 500);
          nextCircleDtos = List<CircleDto>.from(circlesMaps);
        } catch (error) {
          bootstrapError ??= error;
          nextCircleDtos = <CircleDto>[];
        }
      }(),
    ]);

    if (!mounted) {
      return;
    }
    setState(() {
      _circleFeedItems = nextFeedItems;
      _categoryConfig = nextCategoryConfig;
      _hubCircleDtos = nextCircleDtos;
      _isBootstrapping = false;
      _pageErrorSemantic = bootstrapError == null
          ? null
          : runtimeErrorSemantic(
              context,
              error: bootstrapError!,
              category: UiErrorCategory.pageLoad,
              scope: UiErrorScope.page,
            );
    });
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
      return _allCategories.isNotEmpty ? _allCategories.first['id']! : 'campus';
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

  bool _isMyCircleId(String circleId) => _myCircleIds.contains(circleId);

  List<CircleDto> _moduleCirclesFor(
    _HomeCirclesModuleTab tab,
    String categoryId,
  ) {
    final isMineMode = tab == _HomeCirclesModuleTab.mine;
    final source =
        _hubCircleDtos
            .where((circle) {
              if (!isMineMode) {
                return true;
              }
              return _isMyCircleId(circle.id);
            })
            .toList(growable: true)
          ..sort((left, right) {
            return right.memberCount.compareTo(left.memberCount);
          });
    if (categoryId == 'all') {
      return source.take(_maxHomeCircleRailItems - 1).toList(growable: false);
    }
    final categoryFiltered = source
        .where((circle) => circle.category == categoryId)
        .toList(growable: false);
    final fallbackPool = categoryFiltered.isNotEmpty
        ? categoryFiltered
        : source;
    return fallbackPool
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
    final pool =
        _filteredLevelOnePosts(tab, categoryId, fallbackToAllWhenEmpty: true)
            .map((entry) {
              final item = entry.raw;
              final circleId = entry.wireCircleId;
              final sourceCircle = circleById[circleId];
              final circleName = sourceCircle?.name ?? '';
              final feedEntry = mergeCircleStoryEntry(
                Map<String, Object?>.from(item),
                circleName,
              );
              final title =
                  item['title']?.toString() ??
                  item['body']?.toString() ??
                  circleName;
              return _HomeCircleStoryItem(
                id:
                    item['postId']?.toString() ??
                    item['id']?.toString() ??
                    circleId,
                title: title,
                subtitle: circleName,
                imageUrl:
                    item['coverUrl']?.toString() ??
                    item['thumbnailUrl']?.toString() ??
                    sourceCircle?.coverUrl ??
                    '',
                circleId: circleId,
                categoryId: sourceCircle?.category ?? 'all',
                typeLabel: hubCircleStoryTypeLabel(feedEntry.raw),
                isMine: _isMyCircleId(circleId),
                feedEntry: feedEntry,
              );
            })
            .toList(growable: false);
    final isMineMode = tab == _HomeCirclesModuleTab.mine;
    final modeFiltered = pool.where(
      (item) => isMineMode ? item.isMine : !item.isMine,
    );
    final ordered = modeFiltered.toList(growable: false);
    if (categoryId == 'all') {
      return ordered.take(3).toList(growable: false);
    }
    final categoryFiltered = ordered
        .where((item) => item.categoryId == categoryId)
        .toList(growable: false);
    final fallbackPool = categoryFiltered.isNotEmpty
        ? categoryFiltered
        : ordered;
    return fallbackPool.take(3).toList(growable: false);
  }

  List<CircleHubFeedPostEntry> _filteredLevelOnePosts(
    _HomeCirclesModuleTab tab,
    String categoryId, {
    String? subCategoryId,
    bool fallbackToAllWhenEmpty = false,
  }) {
    final circleById = <String, CircleDto>{
      for (final circle in _hubCircleDtos) circle.id: circle,
    };
    final isMineMode = tab == _HomeCirclesModuleTab.mine;
    final modeFiltered = _circleFeedItems
        .where((entry) {
          final circleId = entry.wireCircleId;
          return isMineMode
              ? _isMyCircleId(circleId)
              : !_isMyCircleId(circleId);
        })
        .toList(growable: false);
    final categoryFiltered = modeFiltered
        .where((entry) {
          final circleId = entry.wireCircleId;
          final circle = circleById[circleId];
          return circle?.category == categoryId;
        })
        .toList(growable: false);
    final scopedByCategory = categoryId == 'all'
        ? modeFiltered
        : (categoryFiltered.isNotEmpty || !fallbackToAllWhenEmpty
              ? categoryFiltered
              : modeFiltered);
    final resolvedSubCategory = subCategoryId?.trim() ?? '';
    if (resolvedSubCategory.isEmpty) {
      return scopedByCategory;
    }
    final subCategoryFiltered = scopedByCategory
        .where((entry) => entry.wireSubCategory == resolvedSubCategory)
        .toList(growable: false);
    if (subCategoryFiltered.isNotEmpty || !fallbackToAllWhenEmpty) {
      return subCategoryFiltered;
    }
    return scopedByCategory;
  }

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
        .map((item) => (hubEntry: item, dto: item.tryResolveDto()))
        .where((e) => e.dto != null && _supportsViewer(e.dto!))
        .map((e) => (hubEntry: e.hubEntry, dto: e.dto!))
        .toList(growable: false);
    if (viewerEntries.isEmpty) return;
    final tappedDto = tapped.tryResolveDto();
    if (tappedDto == null || !_supportsViewer(tappedDto)) return;
    final viewerDtos = viewerEntries.map((e) => e.dto).toList(growable: false);
    final mediaRaws = circleHubMediaViewerRawsByPostId(viewerEntries);
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
            .map(
              (dto) => ContentSurfaceViewMapper.fromDto(
                dto,
                wire: mediaRaws[dto.id]?.toDynamicMap() ?? dto.toMap(),
              ),
            )
            .toList(growable: false),
        dtoPosts: viewerDtos,
        initialIndex: initialIndex,
        source: 'circle',
        circleId: tapped.wireCircleId.isEmpty ? null : tapped.wireCircleId,
        rawPostsById: mediaRaws,
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
      return const Material(
        type: MaterialType.transparency,
        child: SafeArea(
          top: false,
          bottom: false,
          child: Center(child: CupertinoActivityIndicator()),
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
            semantic: _pageErrorSemantic!,
            onAction: (action) async {
              if (action.type == UiErrorActionType.retry ||
                  action.type == UiErrorActionType.resubmit) {
                await _bootstrapHubData();
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
      fallbackToAllWhenEmpty: true,
    );

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
                    },
                    onHorizontalDragEnd: _handleCategorySwipeDragEnd,
                  ),
                ),
                Expanded(
                  child: TabSwipeSwitchRegion(
                    onSwipe: _handleCategorySwipe,
                    child: CustomScrollView(
                      key: TestKeys.homeCirclesScrollView,
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
                              setState(() {
                                _activeModuleTab = nextTab;
                              });
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
