import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/navigation/tab_swipe_switch_region.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_config_dto.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_category_tab_defaults.dart';
import 'package:quwoquan_app/cloud/runtime/generated/circle/circle_dto.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_media_viewer_wiring.dart';
import 'package:quwoquan_app/ui/circle/services/home_circles_hub_wire.dart';
import 'package:quwoquan_app/ui/circle/widgets/circle_media_image.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/ui/circle/widgets/home_circles_category_tab.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:shared_preferences/shared_preferences.dart';

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

double _homeCircleChannelTileHeight(BuildContext context) {
  final labelHeight = _measureSingleLineTextHeight(
    context,
    const TextStyle(
      fontSize: AppTypography.base,
      fontWeight: AppTypography.medium,
    ),
  );
  final adaptiveHeight = labelHeight + (AppSpacing.containerSm * 2);
  return adaptiveHeight > AppSpacing.bottomNavHeight
      ? adaptiveHeight
      : AppSpacing.bottomNavHeight;
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
  static const String _channelPrefsKey = 'home_circles.selected_channels.v1';
  static const List<String> _fixedCategoryOrder = <String>['all'];

  String _activeCategoryId = 'all';
  _HomeCirclesModuleTab _activeModuleTab = _HomeCirclesModuleTab.recommended;
  bool _isChannelPanelOpen = false;
  String? _draggingChannelId;
  List<String>? _selectedCategoryIds;
  final GlobalKey _categoryBarKey = GlobalKey();
  late List<CircleHubFeedPostEntry> _circleFeedItems;
  Map<String, CircleCategoryTabConfigDto> _categoryConfig =
      CircleCategoryTabDefaults.remoteStyleFallback;
  List<CircleDto> _hubCircleDtos = [];

  @override
  void initState() {
    super.initState();
    _circleFeedItems = [];
    unawaited(_bootstrapHubData());
    unawaited(_restoreChannelSelection());
  }

  Future<void> _bootstrapHubData() async {
    final repo = ref.read(circleRepositoryProvider);
    try {
      final feed = await repo.listHomeCircleDiscoveryFeed(limit: 200);
      if (!mounted) {
        return;
      }
      setState(() {
        _circleFeedItems =
            feed.map(CircleHubFeedPostEntry.fromPostDto).toList(growable: true);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _circleFeedItems = [];
      });
    }

    try {
      final cfg = await repo.getCircleCategoryConfig();
      if (!mounted) {
        return;
      }
      setState(() {
        _categoryConfig = Map<String, CircleCategoryTabConfigDto>.from(cfg);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _categoryConfig = Map<String, CircleCategoryTabConfigDto>.from(
          CircleCategoryTabDefaults.remoteStyleFallback,
        );
      });
    }

    try {
      final circlesMaps = await repo.listCircles(limit: 500);
      if (!mounted) {
        return;
      }
      setState(() {
        _hubCircleDtos = List<CircleDto>.from(circlesMaps);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _hubCircleDtos = [];
      });
    }
  }

  List<Map<String, String>> get _allCategories {
    final config = _categoryConfig;
    final list = <Map<String, String>>[];
    final seen = <String>{};

    void addCategory(String id, String label) {
      if (!seen.add(id)) return;
      list.add({'id': id, 'label': label});
    }

    addCategory('all', config['all']?.label ?? '推荐');
    for (final entry in config.entries) {
      if (_fixedCategoryOrder.contains(entry.key)) continue;
      addCategory(
        entry.key,
        entry.value.label.isNotEmpty ? entry.value.label : entry.key,
      );
    }
    return list;
  }

  Map<String, String> get _categoryLabelMap {
    return {for (final item in _allCategories) item['id']!: item['label']!};
  }

  List<String> get _fixedCategoryIds {
    final allIds = _allCategories.map((entry) => entry['id']!).toSet();
    return _fixedCategoryOrder.where(allIds.contains).toList(growable: false);
  }

  List<String> get _manageableAllCategoryIds {
    final fixedSet = _fixedCategoryIds.toSet();
    return _allCategories
        .map((entry) => entry['id']!)
        .where((id) => !fixedSet.contains(id))
        .toList(growable: false);
  }

  List<String> get _defaultSelectedCategoryIds =>
      _manageableAllCategoryIds.toList(growable: false);

  List<String> _normalizedSelectedCategoryIds(List<String>? source) {
    final allIds = _manageableAllCategoryIds.toSet();
    final selected = <String>[];
    for (final id in source ?? _defaultSelectedCategoryIds) {
      if (allIds.contains(id) && !selected.contains(id)) {
        selected.add(id);
      }
    }
    if (selected.isEmpty) {
      selected.addAll(_defaultSelectedCategoryIds);
    }
    return selected;
  }

  List<String> get _manageableSelectedCategoryIds =>
      _normalizedSelectedCategoryIds(_selectedCategoryIds);

  List<String> get _visibleCategoryIds => <String>[
    ..._fixedCategoryIds,
    ..._manageableSelectedCategoryIds,
  ];

  String get _effectiveActiveCategoryId {
    final visibleCategoryIds = _visibleCategoryIds;
    if (visibleCategoryIds.isEmpty) {
      return 'all';
    }
    return visibleCategoryIds.contains(_activeCategoryId)
        ? _activeCategoryId
        : visibleCategoryIds.first;
  }

  List<String> get _unselectedCategoryIds {
    final selectedSet = _manageableSelectedCategoryIds.toSet();
    return _manageableAllCategoryIds
        .where((id) => !selectedSet.contains(id))
        .toList(growable: false);
  }

  List<MapEntry<String, CircleCategoryTabConfigDto>> get _visibleCategories {
    final config = _categoryConfig;
    return _visibleCategoryIds
        .where(config.containsKey)
        .map((id) => MapEntry(id, config[id]!))
        .toList(growable: false);
  }

  Future<void> _restoreChannelSelection() async {
    final prefs = await SharedPreferences.getInstance();
    final stored = prefs.getStringList(_channelPrefsKey);
    final normalized = _normalizedSelectedCategoryIds(stored);
    if (!mounted) return;
    setState(() {
      _selectedCategoryIds = normalized;
      if (!_visibleCategoryIds.contains(_activeCategoryId)) {
        _activeCategoryId = _visibleCategoryIds.first;
      }
    });
  }

  Future<void> _persistChannelSelection() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setStringList(_channelPrefsKey, _manageableSelectedCategoryIds);
  }

  void _applySelectedCategoryIds(
    List<String> nextIds, {
    required bool persist,
  }) {
    final normalized = _normalizedSelectedCategoryIds(nextIds);
    setState(() {
      _selectedCategoryIds = normalized;
      if (!_fixedCategoryIds.contains(_activeCategoryId) &&
          !normalized.contains(_activeCategoryId)) {
        _activeCategoryId = _visibleCategoryIds.first;
      }
    });
    if (persist) {
      unawaited(_persistChannelSelection());
    }
  }

  void _moveToUnselected(String id) {
    final selected = List<String>.from(_manageableSelectedCategoryIds);
    if (!selected.contains(id) || selected.length <= 1) return;
    selected.remove(id);
    _applySelectedCategoryIds(selected, persist: true);
  }

  void _moveToSelected(String id) {
    final selected = List<String>.from(_manageableSelectedCategoryIds);
    if (selected.contains(id)) return;
    selected.add(id);
    _applySelectedCategoryIds(selected, persist: true);
  }

  void _reorderSelectedBefore(String sourceId, String targetId) {
    if (sourceId == targetId) return;
    final selected = List<String>.from(_manageableSelectedCategoryIds);
    final sourceIndex = selected.indexOf(sourceId);
    final targetIndex = selected.indexOf(targetId);
    if (sourceIndex < 0 || targetIndex < 0) return;
    final removed = selected.removeAt(sourceIndex);
    final nextIndex = sourceIndex < targetIndex ? targetIndex - 1 : targetIndex;
    selected.insert(nextIndex, removed);
    _applySelectedCategoryIds(selected, persist: true);
  }

  void _toggleChannelPanel() {
    setState(() {
      _isChannelPanelOpen = !_isChannelPanelOpen;
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
    if (_isChannelPanelOpen) {
      return;
    }
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
    if (categoryId == 'all') {
      return modeFiltered;
    }
    final categoryFiltered = modeFiltered
        .where((entry) {
          final circleId = entry.wireCircleId;
          final circle = circleById[circleId];
          return circle?.category == categoryId;
        })
        .toList(growable: false);
    if (categoryFiltered.isNotEmpty || !fallbackToAllWhenEmpty) {
      return categoryFiltered;
    }
    return modeFiltered;
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
    final viewerDtos = viewerEntries
        .map((e) => e.dto)
        .toList(growable: false);
    final mediaRaws = circleHubMediaViewerRawsByPostId(viewerEntries);
    final initialIndex = viewerDtos
        .indexWhere((item) => item.id == tappedDto.id)
        .clamp(0, viewerDtos.length - 1);
    final relationshipState = ref.read(userRelationshipStateProvider);
    final postInteractionState = ref.read(postInteractionStateProvider);
    final result = await context.push<Object?>(
      _isVideoPost(tappedDto)
          ? AppRoutePaths.videoViewer(index: '$initialIndex')
          : AppRoutePaths.mediaViewer(
              category: 'circle',
              index: '$initialIndex',
            ),
      extra: MediaViewerExtra(
        posts: viewerDtos
            .map(
              (dto) => PostSummaryView.fromDto(
                dto,
                surfaceId: PostReadSurfaceId.immersive,
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
        interactionSnapshot: MediaViewerInteractionSnapshot(
          followingUsers: Set<String>.from(
            relationshipState.followingProfileIds,
          ),
          likedPosts: Set<String>.from(postInteractionState.likedPostIds),
          savedPosts: Set<String>.from(postInteractionState.savedPostIds),
          postLikesCount: {
            for (final e in viewerEntries)
              e.dto.id: postInteractionState.likeCountFor(
                e.dto.id,
                fallback: e.hubEntry.wireLikeCount,
              ),
          },
          postBookmarksCount: {
            for (final e in viewerEntries)
              e.dto.id: postInteractionState.bookmarkCountFor(
                e.dto.id,
                fallback: e.hubEntry.wireBookmarkCount,
              ),
          },
          postSharesCount: {
            for (final e in viewerEntries)
              e.dto.id: postInteractionState.shareCountFor(
                e.dto.id,
                fallback: e.hubEntry.wireShareCount,
              ),
          },
        ),
      ),
    );
    if (result is MediaViewerResult) {
      ref
          .read(userRelationshipStateProvider.notifier)
          .applyViewerResult(result);
      ref.read(postInteractionStateProvider.notifier).applyViewerResult(result);
      setState(() {
        CircleHubFeedPostEntry.applyResultToList(_circleFeedItems, result);
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(effectiveIsDarkProvider);
    final categories = _visibleCategories;
    final effectiveActiveCategoryId = _effectiveActiveCategoryId;
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
      fallbackToAllWhenEmpty: true,
    );

    return Stack(
      children: [
        TabSwipeSwitchRegion(
          onSwipe: _handleCategorySwipe,
          child: CustomScrollView(
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            slivers: [
              SliverPersistentHeader(
                floating: true,
                delegate: _StickyTabBarDelegate(
                  extent: AppSpacing.subTabNavigationHeight,
                  child: _HomeCirclesCategoryCapsuleBar(
                    tabBarKey: _categoryBarKey,
                    isDark: isDark,
                    categories: categories,
                    activeCategoryId: effectiveActiveCategoryId,
                    onCategoryTap: (index) {
                      final nextCategoryId = categories[index].key;
                      if (nextCategoryId == effectiveActiveCategoryId) return;
                      setState(() {
                        _activeCategoryId = nextCategoryId;
                      });
                    },
                    onHorizontalDragEnd: _handleCategorySwipeDragEnd,
                    onChannelSelectorTap: _toggleChannelPanel,
                  ),
                ),
              ),
              SliverToBoxAdapter(
                child: _CirclesGlobalHeader(
                  isDark: isDark,
                  activeModuleTab: _activeModuleTab,
                  circles: circles,
                  stories: stories,
                  onStoryTap: (item, items) => _openCircleFeedViewer(
                    context,
                    item.feedEntry,
                    items.map((entry) => entry.feedEntry).toList(growable: false),
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
              HomeCirclesCategoryTab(
                key: ValueKey(
                  'home-circles-category-$effectiveActiveCategoryId',
                ),
                categoryId: effectiveActiveCategoryId,
                posts: levelOnePosts,
                onPostTap: (tapped, sourceItems) =>
                    _openCircleFeedViewer(context, tapped, sourceItems),
                label: activeCategory.value.label.isNotEmpty
                    ? activeCategory.value.label
                    : effectiveActiveCategoryId,
                subCategories: activeCategory.value.subCategories,
              ),
            ],
          ),
        ),
        if (_isChannelPanelOpen)
          Positioned.fill(
            child: _HomeCirclesChannelPanel(
              isDark: isDark,
              categoryLabelMap: _categoryLabelMap,
              selectedIds: _manageableSelectedCategoryIds,
              unselectedIds: _unselectedCategoryIds,
              draggingChannelId: _draggingChannelId,
              onClose: _toggleChannelPanel,
              onMoveToSelected: _moveToSelected,
              onMoveToUnselected: _moveToUnselected,
              onReorderSelectedBefore: _reorderSelectedBefore,
              onDragStarted: (id) {
                setState(() {
                  _draggingChannelId = id;
                });
              },
              onDragEnded: () {
                if (!mounted) return;
                setState(() {
                  _draggingChannelId = null;
                });
              },
            ),
          ),
      ],
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
    final bgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final horizontal = AppSpacing.feedContentHorizontal(context);
    final circleCardWidth = _circleCardWidth(context);

    return Container(
      color: bgPrimary,
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.interGroupSm,
        horizontal,
        AppSpacing.interGroupMd,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                UITextConstants.circlesRecommendedTitle,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  fontWeight: AppTypography.medium,
                  color: fgSecondary.withValues(alpha: 0.78),
                ),
              ),
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
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: AppSpacing.intraGroupSm),
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

class _HomeCirclesCategoryCapsuleBar extends StatelessWidget {
  const _HomeCirclesCategoryCapsuleBar({
    this.tabBarKey,
    required this.isDark,
    required this.categories,
    required this.activeCategoryId,
    required this.onCategoryTap,
    this.onHorizontalDragEnd,
    required this.onChannelSelectorTap,
  });

  final Key? tabBarKey;
  final bool isDark;
  final List<MapEntry<String, CircleCategoryTabConfigDto>> categories;
  final String activeCategoryId;
  final ValueChanged<int> onCategoryTap;
  final GestureDragEndCallback? onHorizontalDragEnd;
  final VoidCallback onChannelSelectorTap;

  @override
  Widget build(BuildContext context) {
    final tabs = categories
        .map(
          (entry) =>
              entry.value.label.isNotEmpty ? entry.value.label : entry.key,
        )
        .toList(growable: false);
    final activeIndex = categories.indexWhere(
      (entry) => entry.key == activeCategoryId,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    return SecondaryCapsuleTabBar(
      key: tabBarKey,
      isDark: isDark,
      tabs: tabs,
      activeIndex: activeIndex < 0 ? 0 : activeIndex,
      onTap: onCategoryTap,
      onHorizontalDragEnd: onHorizontalDragEnd,
      fontSize: AppTypography.smPlus,
      trailing: Padding(
        padding: EdgeInsets.only(
          right: AppSpacing.topBarTrailingButtonInset(context),
        ),
        child: SizedBox(
          width: AppSpacing.minInteractiveSize,
          height: AppSpacing.minInteractiveSize,
          child: CupertinoButton(
            padding: EdgeInsets.zero,
            onPressed: onChannelSelectorTap,
            child: Icon(
              CupertinoIcons.line_horizontal_3_decrease,
              size: AppSpacing.iconMedium,
              color: fgSecondary,
            ),
          ),
        ),
      ),
      showTrailingDivider: true,
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
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    final bgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
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
            color: bgPrimary,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor.withValues(alpha: 0.12)),
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
                  child: CircleMediaImage(
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
    final bgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final borderColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.borderPrimary,
    );
    return SizedBox(
      width: width,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onTap,
        child: Container(
          decoration: BoxDecoration(
            color: bgPrimary,
            borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            border: Border.all(color: borderColor.withValues(alpha: 0.12)),
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

class _HomeCirclesChannelPanel extends StatelessWidget {
  const _HomeCirclesChannelPanel({
    required this.isDark,
    required this.categoryLabelMap,
    required this.selectedIds,
    required this.unselectedIds,
    required this.draggingChannelId,
    required this.onClose,
    required this.onMoveToSelected,
    required this.onMoveToUnselected,
    required this.onReorderSelectedBefore,
    required this.onDragStarted,
    required this.onDragEnded,
  });

  final bool isDark;
  final Map<String, String> categoryLabelMap;
  final List<String> selectedIds;
  final List<String> unselectedIds;
  final String? draggingChannelId;
  final VoidCallback onClose;
  final ValueChanged<String> onMoveToSelected;
  final ValueChanged<String> onMoveToUnselected;
  final void Function(String sourceId, String targetId) onReorderSelectedBefore;
  final ValueChanged<String> onDragStarted;
  final VoidCallback onDragEnded;

  @override
  Widget build(BuildContext context) {
    final bg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onClose,
      child: ColoredBox(
        color: bg.withValues(alpha: 0.98),
        child: SafeArea(
          bottom: false,
          child: SingleChildScrollView(
            physics: const BouncingScrollPhysics(
              parent: AlwaysScrollableScrollPhysics(),
            ),
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {},
              child: Padding(
                padding: EdgeInsets.fromLTRB(
                  AppSpacing.feedContentHorizontal(context),
                  AppSpacing.containerMd,
                  AppSpacing.feedContentHorizontal(context),
                  AppSpacing.containerMd +
                      MediaQuery.viewPaddingOf(context).bottom +
                      AppSpacing.bottomNavHeight,
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text(
                          UITextConstants.circleMyChannels,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupSm),
                        Text(
                          UITextConstants.circleDragToSort,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: fgSecondary,
                          ),
                        ),
                        const Spacer(),
                        CupertinoButton(
                          padding: EdgeInsets.zero,
                          onPressed: onClose,
                          child: Text(
                            UITextConstants.done,
                            style: TextStyle(
                              fontSize: AppTypography.base,
                              fontWeight: AppTypography.medium,
                              color: AppColors.primaryColor,
                            ),
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: AppSpacing.interGroupSm),
                    _HomeCirclesChannelGrid(
                      isDark: isDark,
                      categoryLabelMap: categoryLabelMap,
                      channelIds: selectedIds,
                      canRemove: true,
                      draggingChannelId: draggingChannelId,
                      onTapIcon: onMoveToUnselected,
                      onDragStarted: onDragStarted,
                      onDragEnded: onDragEnded,
                      onReorderSelectedBefore: onReorderSelectedBefore,
                    ),
                    SizedBox(height: AppSpacing.interGroupLg),
                    Row(
                      children: [
                        Text(
                          UITextConstants.circleAllChannels,
                          style: TextStyle(
                            fontSize: AppTypography.lg,
                            fontWeight: AppTypography.semiBold,
                            color: fgPrimary,
                          ),
                        ),
                        SizedBox(width: AppSpacing.intraGroupSm),
                        Text(
                          UITextConstants.circleTapToAdd,
                          style: TextStyle(
                            fontSize: AppTypography.sm,
                            color: fgSecondary,
                          ),
                        ),
                      ],
                    ),
                    SizedBox(height: AppSpacing.interGroupSm),
                    _HomeCirclesChannelGrid(
                      isDark: isDark,
                      categoryLabelMap: categoryLabelMap,
                      channelIds: unselectedIds,
                      canRemove: false,
                      draggingChannelId: draggingChannelId,
                      onTapIcon: onMoveToSelected,
                      onDragStarted: onDragStarted,
                      onDragEnded: onDragEnded,
                      onReorderSelectedBefore: onReorderSelectedBefore,
                    ),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _HomeCirclesChannelGrid extends StatelessWidget {
  const _HomeCirclesChannelGrid({
    required this.isDark,
    required this.categoryLabelMap,
    required this.channelIds,
    required this.canRemove,
    required this.draggingChannelId,
    required this.onTapIcon,
    required this.onDragStarted,
    required this.onDragEnded,
    required this.onReorderSelectedBefore,
  });

  final bool isDark;
  final Map<String, String> categoryLabelMap;
  final List<String> channelIds;
  final bool canRemove;
  final String? draggingChannelId;
  final ValueChanged<String> onTapIcon;
  final ValueChanged<String> onDragStarted;
  final VoidCallback onDragEnded;
  final void Function(String sourceId, String targetId) onReorderSelectedBefore;

  @override
  Widget build(BuildContext context) {
    final spacing = AppSpacing.intraGroupSm;
    final panelTileHeight = _homeCircleChannelTileHeight(context);
    return LayoutBuilder(
      builder: (context, constraints) {
        final totalSpacing = spacing * 3;
        final tileWidth = (constraints.maxWidth - totalSpacing) / 4;
        return Wrap(
          spacing: spacing,
          runSpacing: spacing,
          children: channelIds
              .map((id) {
                final label = categoryLabelMap[id] ?? id;
                final tile = _HomeCirclesChannelTile(
                  isDark: isDark,
                  width: tileWidth,
                  height: panelTileHeight,
                  label: label,
                  canRemove: canRemove,
                  isDragging: draggingChannelId == id,
                  onIconTap: () => onTapIcon(id),
                );
                if (!canRemove) return tile;
                return SizedBox(
                  width: tileWidth,
                  height: panelTileHeight,
                  child: DragTarget<String>(
                    onWillAcceptWithDetails: (details) => details.data != id,
                    onAcceptWithDetails: (details) {
                      onReorderSelectedBefore(details.data, id);
                    },
                    builder: (context, candidateData, rejectedData) {
                      return LongPressDraggable<String>(
                        data: id,
                        onDragStarted: () => onDragStarted(id),
                        onDragEnd: (_) => onDragEnded(),
                        feedback: ColoredBox(
                          color: AppColors.transparent,
                          child: _HomeCirclesChannelTile(
                            isDark: isDark,
                            width: tileWidth,
                            height: panelTileHeight,
                            label: label,
                            canRemove: true,
                            isDragging: false,
                            onIconTap: () {},
                          ),
                        ),
                        childWhenDragging: Opacity(opacity: 0.2, child: tile),
                        child: tile,
                      );
                    },
                  ),
                );
              })
              .toList(growable: false),
        );
      },
    );
  }
}

class _HomeCirclesChannelTile extends StatelessWidget {
  const _HomeCirclesChannelTile({
    required this.isDark,
    required this.width,
    required this.height,
    required this.label,
    required this.canRemove,
    required this.isDragging,
    required this.onIconTap,
  });

  final bool isDark;
  final double width;
  final double height;
  final String label;
  final bool canRemove;
  final bool isDragging;
  final VoidCallback onIconTap;

  @override
  Widget build(BuildContext context) {
    final bg = canRemove
        ? AppColorsFunctional.getColor(isDark, ColorType.backgroundSecondary)
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final borderColor = canRemove
        ? AppColors.transparent
        : AppColorsFunctional.getColor(
            isDark,
            ColorType.borderPrimary,
          ).withValues(alpha: 0.5);
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final iconBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundTertiary,
    );

    return SizedBox(
      width: width,
      height: height,
      child: Opacity(
        opacity: isDragging ? 0.45 : 1,
        child: Stack(
          clipBehavior: Clip.none,
          children: [
            Container(
              width: width,
              height: height,
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.containerSm,
                vertical: AppSpacing.intraGroupXs,
              ),
              decoration: BoxDecoration(
                color: bg,
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                border: Border.all(color: borderColor),
              ),
              child: Center(
                child: Text(
                  canRemove ? label : '+ $label',
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: AppTypography.base,
                    color: fg,
                    fontWeight: AppTypography.medium,
                  ),
                ),
              ),
            ),
            if (canRemove)
              Positioned(
                top: -AppSpacing.intraGroupXs,
                right: -AppSpacing.intraGroupXs,
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onIconTap,
                  child: Container(
                    width: AppSpacing.minInteractiveSize / 2,
                    height: AppSpacing.minInteractiveSize / 2,
                    decoration: BoxDecoration(
                      color: iconBg,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      CupertinoIcons.xmark,
                      size: AppSpacing.iconSmall,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                  ),
                ),
              )
            else
              Positioned.fill(
                child: GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: onIconTap,
                  child: const SizedBox.expand(),
                ),
              ),
          ],
        ),
      ),
    );
  }
}
