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
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_media_viewer_wiring.dart';
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_wire.dart';
import 'package:quwoquan_app/components/media/app_media_image.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_entity_bridge_strip.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/core/widgets/global_surface_actions.dart';

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
        category: 'circle',
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

class _CirclesGlobalHeader extends StatelessWidget {
  const _CirclesGlobalHeader({
    required this.isDark,
    required this.activeModuleTab,
    required this.circles,
    required this.stories,
    required this.onStoryTap,
    required this.onModuleTabChanged,
    required this.onSeeMoreTap,
  });

  final bool isDark;
  final _HomeCirclesModuleTab activeModuleTab;
  final List<CircleDto> circles;
  final List<_HomeCircleStoryItem> stories;
  final void Function(
    _HomeCircleStoryItem item,
    List<_HomeCircleStoryItem> items,
  )
  onStoryTap;
  final ValueChanged<_HomeCirclesModuleTab> onModuleTabChanged;
  final VoidCallback onSeeMoreTap;

  double _circleCardWidth(BuildContext context) {
    return AppSpacing.responsiveValue(
      context,
      compact: AppSpacing.bottomNavHeight * 1.7,
      regular: AppSpacing.bottomNavHeight * 1.9,
      expanded: AppSpacing.bottomNavHeight * 2.1,
    );
  }

  double _circleRailHeight(BuildContext context) {
    final cardWidth = _circleCardWidth(context);
    final coverHeight = cardWidth / _homeCircleCoverAspectRatio;
    final titleHeight = _measureSingleLineTextHeight(
      context,
      _homeCircleRailTitleTextStyle(),
    );
    final metaHeight = _measureSingleLineTextHeight(
      context,
      _homeCircleRailMetaTextStyle(),
    );
    final verticalPadding = AppSpacing.intraGroupXs * 2;
    final contentSpacing =
        AppSpacing.intraGroupXs + (AppSpacing.intraGroupXs / 2);
    return coverHeight +
        verticalPadding +
        contentSpacing +
        titleHeight +
        metaHeight +
        1;
  }

  @override
  Widget build(BuildContext context) {
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);
    final circleCardWidth = _circleCardWidth(context);

    return Container(
      color: cardSurface,
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.containerXs,
        horizontal,
        AppSpacing.containerSm,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  UITextConstants.circlesRecommendedTitle,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.iosFootnote,
                    fontWeight: AppTypography.medium,
                    color: fgSecondary.withValues(alpha: 0.78),
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
              SizedBox(width: AppSpacing.intraGroupSm),
              CupertinoButton(
                onPressed: onSeeMoreTap,
                padding: EdgeInsets.zero,
                minimumSize: Size.zero,
                child: Text(
                  UITextConstants.seeMore,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColors.primaryColor,
                    fontWeight: AppTypography.medium,
                    decoration: TextDecoration.none,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          SizedBox(
            height: _circleRailHeight(context),
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              // 即使暂无推荐圈子也保留「查看全部」卡，避免空轨导致测试/首屏无法触达广场入口。
              itemCount: circles.length + 1,
              separatorBuilder: (context, index) =>
                  SizedBox(width: AppSpacing.intraGroupMd),
              itemBuilder: (context, index) {
                if (index == circles.length) {
                  return _HomeCircleViewAllCard(
                    width: circleCardWidth,
                    isDark: isDark,
                    onTap: onSeeMoreTap,
                  );
                }
                final circle = circles[index];
                return _HomeCircleRailCard(
                  circle: circle,
                  width: circleCardWidth,
                  isDark: isDark,
                  onTap: () =>
                      context.push(AppRoutePaths.circleDetail(id: circle.id)),
                );
              },
            ),
          ),
        ],
      ),
    );
  }
}

class _StickyTabBarDelegate extends SliverPersistentHeaderDelegate {
  const _StickyTabBarDelegate({required this.child, required this.extent});

  final Widget child;
  final double extent;

  @override
  Widget build(
    BuildContext context,
    double shrinkOffset,
    bool overlapsContent,
  ) {
    return child;
  }

  @override
  double get maxExtent => extent;

  @override
  double get minExtent => extent;

  @override
  bool shouldRebuild(covariant _StickyTabBarDelegate oldDelegate) {
    return oldDelegate.child != child || oldDelegate.extent != extent;
  }
}

class _CirclesPrimaryCategoryTabBar extends StatelessWidget {
  const _CirclesPrimaryCategoryTabBar({
    required this.isDark,
    required this.categories,
    required this.activeCategoryId,
    required this.onCategoryTap,
    this.onHorizontalDragEnd,
  });

  final bool isDark;
  final List<MapEntry<String, CircleCategoryTabConfigDto>> categories;
  final String activeCategoryId;
  final ValueChanged<int> onCategoryTap;
  final GestureDragEndCallback? onHorizontalDragEnd;

  @override
  Widget build(BuildContext context) {
    final tabs = categories
        .map(
          (entry) => TabItem(
            id: entry.key,
            label: entry.value.label.isNotEmpty ? entry.value.label : entry.key,
          ),
        )
        .toList(growable: false);

    return CenteredScrollableTabBar(
      tabs: tabs,
      activeTab: activeCategoryId,
      onTabChange: (tabId) {
        final nextIndex = categories.indexWhere((entry) => entry.key == tabId);
        if (nextIndex < 0) {
          return;
        }
        onCategoryTap(nextIndex);
      },
      isDark: isDark,
      onHorizontalDragEnd: onHorizontalDragEnd,
      leftAlignedCompactMode: true,
    );
  }
}

class _CirclesSubCategoryBar extends StatelessWidget {
  const _CirclesSubCategoryBar({
    required this.isDark,
    required this.categoryId,
    required this.subCategories,
    required this.activeSubCategoryId,
    required this.onSubCategoryTap,
  });

  final bool isDark;
  final String categoryId;
  final List<String> subCategories;
  final String activeSubCategoryId;
  final ValueChanged<String> onSubCategoryTap;

  static double extent(BuildContext context) {
    final verticalPadding = AppSpacing.secondaryTabBarVerticalPadding(context);
    final chipVerticalPadding = AppSpacing.secondaryTabChipVerticalPadding(
      context,
    );
    final painter = TextPainter(
      text: TextSpan(
        text: 'Hg',
        style: TextStyle(
          fontSize: AppTypography.secondaryTabLabelResponsive(context),
          fontWeight: AppTypography.secondaryTabSelectedWeight,
        ),
      ),
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
      maxLines: 1,
    )..layout();
    final measuredBarHeight =
        painter.height + (verticalPadding * 2) + (chipVerticalPadding * 2);
    final barHeight = measuredBarHeight > AppSpacing.subTabNavigationHeight
        ? measuredBarHeight
        : AppSpacing.subTabNavigationHeight;
    return barHeight + AppSpacing.xs + AppSpacing.containerXs;
  }

  @override
  Widget build(BuildContext context) {
    final activeIndex = subCategories.indexWhere(
      (subCategory) => subCategory == activeSubCategoryId,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);

    return Container(
      key: ValueKey<String>('circles-sub-category-$categoryId'),
      color: AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary),
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.xs,
        horizontal,
        AppSpacing.containerXs,
      ),
      child: SecondaryCapsuleTabBar(
        isDark: isDark,
        tabs: subCategories,
        activeIndex: activeIndex < 0 ? 0 : activeIndex,
        onTap: (index) {
          if (index < 0 || index >= subCategories.length) {
            return;
          }
          onSubCategoryTap(subCategories[index]);
        },
        horizontalPadding: 0,
        variant: SecondaryCapsuleTabBarVariant.inlineMuted,
      ),
    );
  }
}

class _HomeCircleRailCard extends StatelessWidget {
  const _HomeCircleRailCard({
    required this.circle,
    required this.width,
    required this.isDark,
    required this.onTap,
  });

  final CircleDto circle;
  final double width;
  final bool isDark;
  final VoidCallback onTap;

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
    final borderColor =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final titleStyle = _homeCircleRailTitleTextStyle().copyWith(
      color: fgPrimary,
    );
    final metaStyle = _homeCircleRailMetaTextStyle().copyWith(
      color: fgSecondary,
    );
    return SizedBox(
      width: width,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: cardSurface,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: isDark ? 0.16 : 0.05),
                blurRadius: AppSpacing.md,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          padding: EdgeInsets.all(AppSpacing.intraGroupXs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.max,
            children: [
              ClipRRect(
                borderRadius: BorderRadius.circular(
                  AppSpacing.contentPreviewCornerRadius,
                ),
                child: AspectRatio(
                  aspectRatio: _homeCircleCoverAspectRatio,
                  child: AppMediaImage(
                    imageSource: circle.coverUrl ?? '',
                    fit: BoxFit.cover,
                  ),
                ),
              ),
              SizedBox(height: AppSpacing.intraGroupXs),
              Expanded(
                child: Align(
                  alignment: Alignment.centerLeft,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        circle.name,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: titleStyle,
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs / 2),
                      Text(
                        '${circle.memberCount} ${UITextConstants.circleMembers}',
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: metaStyle,
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HomeCircleViewAllCard extends StatelessWidget {
  const _HomeCircleViewAllCard({
    required this.width,
    required this.isDark,
    required this.onTap,
  });

  final double width;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final cardSurface = SettingsSemanticConstants.conversationSheetCardSurface(
      isDark,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final borderColor =
        SettingsSemanticConstants.conversationSheetCardBorderColor(isDark);
    return SizedBox(
      width: width,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: cardSurface,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor),
            boxShadow: [
              BoxShadow(
                color: AppColors.black.withValues(alpha: isDark ? 0.16 : 0.05),
                blurRadius: AppSpacing.md,
                offset: const Offset(0, 8),
              ),
            ],
          ),
          padding: EdgeInsets.all(AppSpacing.intraGroupXs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Expanded(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    color: AppColors.primaryColor.withValues(alpha: 0.08),
                    borderRadius: BorderRadius.circular(
                      AppSpacing.contentPreviewCornerRadius,
                    ),
                  ),
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        CupertinoIcons.square_grid_2x2,
                        size: AppSpacing.iconMedium,
                        color: AppColors.primaryColor,
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs),
                      Text(
                        UITextConstants.homeCirclesViewAll,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.semiBold,
                          color: fgPrimary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _HomeCircleStoryItem {
  _HomeCircleStoryItem({
    required this.id,
    required this.title,
    required this.subtitle,
    required this.imageUrl,
    required this.circleId,
    required this.categoryId,
    required this.typeLabel,
    required this.isMine,
    required this.feedEntry,
  });

  final String id;
  final String title;
  final String subtitle;
  final String imageUrl;
  final String circleId;
  final String categoryId;
  final String typeLabel;
  final bool isMine;
  final CircleHubFeedPostEntry feedEntry;
}

class _CirclesHubTopBar extends StatelessWidget {
  const _CirclesHubTopBar({
    required this.isDark,
    required this.onSearchTap,
    required this.onAssistantTap,
  });

  final bool isDark;
  final VoidCallback onSearchTap;
  final VoidCallback onAssistantTap;

  @override
  Widget build(BuildContext context) {
    final chromeBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final fieldBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);
    final topInset = AppSpacing.appChromeTopSafeInset(
      MediaQuery.viewPaddingOf(context).top,
      context,
    );

    return Container(
      color: chromeBackground,
      padding: EdgeInsets.only(top: topInset),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            height: AppSpacing.appChromeTopBarHeight(context),
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontal),
              child: Row(
                children: [
                  Expanded(
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: Size.zero,
                      onPressed: onSearchTap,
                      child: IgnorePointer(
                        child: AppSearchField(
                          placeholder: UITextConstants.circlesSearchHint,
                          backgroundColor: fieldBackground,
                          elevated: false,
                        ),
                      ),
                    ),
                  ),
                  SizedBox(width: AppSpacing.intraGroupSm),
                  GlobalAssistantEntryButton(
                    semanticLabel: UITextConstants.assistantEntryXiaoqu,
                    onTap: onAssistantTap,
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
