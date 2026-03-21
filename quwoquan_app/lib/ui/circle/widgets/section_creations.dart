import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_tab.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/circle/widgets/media_viewer_result_absorber.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

/// 圈子"创作"板块：SubTab 过滤 + 排序 + 二列网格
class SectionCreations extends ConsumerStatefulWidget {
  const SectionCreations({
    super.key,
    required this.circleId,
    required this.isDark,
    required this.role,
  });

  final String circleId;
  final bool isDark;
  final CircleRole role;

  @override
  ConsumerState<SectionCreations> createState() => _SectionCreationsState();
}

class _SectionCreationsState extends ConsumerState<SectionCreations> {
  bool _isLoading = true;
  String? _error;
  List<Map<String, dynamic>> _feedItems = const [];

  List<IdentityFilterConfig> get _identityFilters =>
      ContentUIConfig.creationIdentityFilters;

  List<WorkFormatFilterConfig> get _workFormatFilters =>
      ContentUIConfig.workFormatFilters;

  static const double _creationGridCoverAspectRatio = 0.92;

  static const _sortLabels = {
    CreationSortMode.latest: UITextConstants.circleSortLatest,
    CreationSortMode.hot: UITextConstants.circleSortHot,
    CreationSortMode.featured: UITextConstants.circleSortFeatured,
  };

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) => _loadFeed());
  }

  Future<void> _loadFeed() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final notifier = ref.read(circleStateProvider(widget.circleId));
      final repo = ref.read(circleRepositoryProvider);
      final query = _feedQueryForState(notifier.state);
      final items = await repo.getCircleFeed(
        widget.circleId,
        identity: query.identity,
        type: query.type,
        sort: notifier.state.sortMode.name,
      );
      if (mounted) {
        setState(() {
          _feedItems = items;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _error = e.toString();
        });
      }
    }
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

  double _gridItemMainAxisExtent(BuildContext context, double itemWidth) {
    final coverHeight = itemWidth / _creationGridCoverAspectRatio;
    final titleHeight =
        _measureSingleLineTextHeight(
          context,
          const TextStyle(
            fontSize: AppTypography.base,
            fontWeight: AppTypography.semiBold,
          ),
        ) *
        2;
    final metaTextHeight = _measureSingleLineTextHeight(
      context,
      const TextStyle(
        fontSize: AppTypography.sm,
        fontWeight: AppTypography.medium,
      ),
    );
    final metaRowHeight = metaTextHeight > AppSpacing.iconSmall
        ? metaTextHeight
        : AppSpacing.iconSmall;
    return coverHeight +
        (AppSpacing.containerSm * 2) +
        titleHeight +
        metaRowHeight +
        (AppSpacing.intraGroupXs * 2);
  }

  @override
  Widget build(BuildContext context) {
    final notifier = ref.watch(circleStateProvider(widget.circleId));
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final bgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundSecondary,
    );
    final bgTertiary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.backgroundTertiary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final borderColor = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.borderPrimary,
    );

    return Padding(
      padding: EdgeInsets.fromLTRB(
        AppSpacing.containerMd,
        AppSpacing.containerSm,
        AppSpacing.containerMd,
        AppSpacing.containerLg,
      ),
      child: Column(
        children: [
          _buildSurface(
            backgroundColor: bgSecondary,
            borderColor: borderColor,
            child: Column(
              children: [
                _buildIdentityFilterRow(notifier, fg, fgSecondary),
                if (_isWorkLikeSubTab(notifier.state.activeSubTab)) ...[
                  SizedBox(height: AppSpacing.sm),
                  _buildWorkFormatFilterRow(notifier, fg, fgSecondary),
                ],
                if (_isAdminOrOwner) ...[
                  SizedBox(height: AppSpacing.sm),
                  _buildSortControls(notifier, fg, fgSecondary),
                  SizedBox(height: AppSpacing.xs),
                  _buildViewModeToggle(
                    notifier,
                    fgSecondary: fgSecondary,
                    borderColor: borderColor,
                    backgroundColor: bgTertiary,
                  ),
                ],
              ],
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          Expanded(
            child: _buildSurface(
              backgroundColor: bgSecondary,
              borderColor: borderColor,
              padding: EdgeInsets.zero,
              child: _buildContent(
                notifier,
                fg,
                fgSecondary,
                bgSecondary,
                bgTertiary,
                borderColor,
              ),
            ),
          ),
        ],
      ),
    );
  }

  bool get _isAdminOrOwner =>
      widget.role == CircleRole.owner || widget.role == CircleRole.admin;

  bool _isWorkLikeSubTab(CreationSubTab tab) {
    switch (tab) {
      case CreationSubTab.work:
      case CreationSubTab.image:
      case CreationSubTab.video:
      case CreationSubTab.article:
        return true;
      case CreationSubTab.all:
      case CreationSubTab.moment:
      case CreationSubTab.micro:
        return false;
    }
  }

  ({String? identity, String? type}) _feedQueryForState(CircleState state) {
    switch (state.activeSubTab) {
      case CreationSubTab.moment:
        return (identity: 'moment', type: null);
      case CreationSubTab.micro:
        return (identity: 'moment', type: 'micro');
      case CreationSubTab.work:
        return (
          identity: 'work',
          type: _contentTypeForWorkFormat(state.activeWorkFormat),
        );
      case CreationSubTab.image:
        return (identity: 'work', type: 'image');
      case CreationSubTab.video:
        return (identity: 'work', type: 'video');
      case CreationSubTab.article:
        return (identity: 'work', type: 'article');
      case CreationSubTab.all:
        return (identity: null, type: null);
    }
  }

  Widget _buildIdentityFilterRow(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: _identityFilters
            .map((filter) {
              final tab = _creationSubTabForId(filter.id);
              final selected = notifier.state.activeSubTab == tab;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: _CupertinoFilterChip(
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                  selected: selected,
                  fg: fg,
                  fgSecondary: fgSecondary,
                  onPressed: () {
                    notifier.setSubTab(tab);
                    _loadFeed();
                  },
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }

  Widget _buildWorkFormatFilterRow(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: _workFormatFilters
            .map((filter) {
              final format = _creationWorkFormatForId(filter.id);
              final selected = notifier.state.activeWorkFormat == format;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: _CupertinoFilterChip(
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                  selected: selected,
                  fg: fg,
                  fgSecondary: fgSecondary,
                  onPressed: () {
                    notifier.setWorkFormat(format);
                    _loadFeed();
                  },
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }

  CreationSubTab _creationSubTabForId(String id) {
    switch (id) {
      case 'moment':
        return CreationSubTab.moment;
      case 'work':
        return CreationSubTab.work;
      default:
        return CreationSubTab.all;
    }
  }

  CreationWorkFormat _creationWorkFormatForId(String id) {
    switch (id) {
      case 'image':
        return CreationWorkFormat.image;
      case 'video':
        return CreationWorkFormat.video;
      case 'note':
        return CreationWorkFormat.note;
      default:
        return CreationWorkFormat.all;
    }
  }

  String? _contentTypeForWorkFormat(CreationWorkFormat format) {
    switch (format) {
      case CreationWorkFormat.image:
        return 'image';
      case CreationWorkFormat.video:
        return 'video';
      case CreationWorkFormat.note:
        return 'article';
      case CreationWorkFormat.all:
        return null;
    }
  }

  bool _matchesIdentityFilter(Map<String, dynamic> item, CreationSubTab tab) {
    switch (tab) {
      case CreationSubTab.moment:
        return _itemIdentity(item) == 'moment';
      case CreationSubTab.micro:
        return _itemIdentity(item) == 'moment' &&
            _itemDisplayFormat(item) == 'micro';
      case CreationSubTab.work:
        return _itemIdentity(item) == 'work';
      case CreationSubTab.image:
        return _itemIdentity(item) == 'work' &&
            _itemDisplayFormat(item) == 'image';
      case CreationSubTab.video:
        return _itemIdentity(item) == 'work' &&
            _itemDisplayFormat(item) == 'video';
      case CreationSubTab.article:
        return _itemIdentity(item) == 'work' &&
            _itemDisplayFormat(item) == 'note';
      case CreationSubTab.all:
        return true;
    }
  }

  bool _matchesWorkFormat(
    Map<String, dynamic> item,
    CreationSubTab activeSubTab,
    CreationWorkFormat format,
  ) {
    if (!_isWorkLikeSubTab(activeSubTab) || format == CreationWorkFormat.all) {
      return true;
    }
    switch (format) {
      case CreationWorkFormat.image:
        return _itemDisplayFormat(item) == 'image';
      case CreationWorkFormat.video:
        return _itemDisplayFormat(item) == 'video';
      case CreationWorkFormat.note:
        return _itemDisplayFormat(item) == 'note';
      case CreationWorkFormat.all:
        return true;
    }
  }

  String _itemIdentity(Map<String, dynamic> item) {
    return (item['contentIdentity'] ??
            (item['type']?.toString() == 'moment' ? 'moment' : 'work'))
        .toString();
  }

  String _itemDisplayFormat(Map<String, dynamic> item) {
    final type = (item['type'] ?? '').toString();
    switch (type) {
      case 'image':
        return 'image';
      case 'video':
        return 'video';
      case 'article':
        return 'note';
      case 'moment':
        return 'moment';
      default:
        return type;
    }
  }

  String _itemTypeLabel(Map<String, dynamic> item) {
    final identity = _itemIdentity(item);
    if (identity == 'moment') {
      return UITextConstants.creationFilterMoment;
    }
    switch (_itemDisplayFormat(item)) {
      case 'image':
        return UITextConstants.workFormatFilterImage;
      case 'video':
        return UITextConstants.workFormatFilterVideo;
      case 'note':
        return UITextConstants.workFormatFilterNote;
      default:
        return UITextConstants.creationFilterWork;
    }
  }

  Widget _buildSortControls(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
  ) {
    final activeSortMode = notifier.state.sortMode;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: CreationSortMode.values.map((mode) {
          final selected = mode == activeSortMode;
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.sm),
            child: GestureDetector(
              onTap: () {
                notifier.setSortMode(mode);
                _loadFeed();
              },
              child: Container(
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.md,
                  vertical: AppSpacing.sm,
                ),
                decoration: BoxDecoration(
                  color: selected
                      ? (widget.isDark
                            ? Colors.white.withValues(alpha: 0.1)
                            : Colors.black.withValues(alpha: 0.06))
                      : null,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.circularBorderRadius,
                  ),
                  border: Border.all(
                    color: widget.isDark ? Colors.white24 : Colors.black12,
                  ),
                ),
                child: Text(
                  _sortLabels[mode]!,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    fontWeight: AppTypography.extraBold,
                    color: selected ? fg : fgSecondary,
                  ),
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildViewModeToggle(
    CircleStateNotifier notifier, {
    required Color fgSecondary,
    required Color borderColor,
    required Color backgroundColor,
  }) {
    final activeMode = notifier.state.viewMode;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _ViewModeButton(
            icon: CupertinoIcons.square_grid_2x2,
            tooltip: '网格视图',
            selected: activeMode == CreationViewMode.grid,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            backgroundColor: backgroundColor,
            onPressed: () => notifier.setViewMode(CreationViewMode.grid),
          ),
          SizedBox(width: AppSpacing.xs),
          _ViewModeButton(
            icon: CupertinoIcons.rectangle_grid_1x2,
            tooltip: '列表视图',
            selected: activeMode == CreationViewMode.list,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            backgroundColor: backgroundColor,
            onPressed: () => notifier.setViewMode(CreationViewMode.list),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(
    CircleStateNotifier notifier,
    Color fg,
    Color fgSecondary,
    Color bgSecondary,
    Color bgTertiary,
    Color borderColor,
  ) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return _buildErrorCard(fgSecondary);
    }

    final activeSubTab = notifier.state.activeSubTab;
    final activeWorkFormat = notifier.state.activeWorkFormat;
    final filtered = _feedItems.where((item) {
      return _matchesIdentityFilter(item, activeSubTab) &&
          _matchesWorkFormat(item, activeSubTab, activeWorkFormat);
    }).toList();

    if (filtered.isEmpty) {
      return _buildEmpty(fgSecondary);
    }

    if (notifier.state.viewMode == CreationViewMode.list) {
      return ListView.separated(
        padding: EdgeInsets.fromLTRB(
          AppSpacing.containerSm,
          AppSpacing.containerSm,
          AppSpacing.containerSm,
          AppSpacing.containerMd,
        ),
        itemCount: filtered.length,
        separatorBuilder: (_, _) => SizedBox(height: AppSpacing.sm),
        itemBuilder: (context, index) {
          final item = filtered[index];
          return _buildListItem(
            item,
            fg,
            fgSecondary,
            backgroundColor: bgTertiary,
            borderColor: borderColor,
            onTap: () => _openMediaViewer(context, item, filtered),
          );
        },
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final itemWidth =
            (constraints.maxWidth -
                (AppSpacing.containerSm * 2) -
                AppSpacing.sm) /
            2;
        return GridView.builder(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerSm,
            AppSpacing.containerSm,
            AppSpacing.containerSm,
            AppSpacing.containerMd,
          ),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisSpacing: AppSpacing.sm,
            crossAxisSpacing: AppSpacing.sm,
            mainAxisExtent: _gridItemMainAxisExtent(context, itemWidth),
          ),
          itemCount: filtered.length,
          itemBuilder: (context, index) {
            final item = filtered[index];
            return _buildGridItem(
              item,
              fg,
              fgSecondary,
              backgroundColor: bgSecondary,
              borderColor: borderColor,
              onTap: () => _openMediaViewer(context, item, filtered),
            );
          },
        );
      },
    );
  }

  Future<void> _openMediaViewer(
    BuildContext context,
    Map<String, dynamic> tapped,
    List<Map<String, dynamic>> sourceItems,
  ) async {
    final tappedDto = _tryParsePost(tapped);
    if (tappedDto == null) return;
    if (!_supportsViewer(tappedDto)) return;

    final viewerEntries = sourceItems
        .map((item) => (raw: item, dto: _tryParsePost(item)))
        .where((entry) => entry.dto != null && _supportsViewer(entry.dto!))
        .toList(growable: false);
    if (viewerEntries.isEmpty) return;

    final viewerDtos = viewerEntries
        .map((entry) => entry.dto!)
        .toList(growable: false);
    final initialIndex = viewerDtos
        .indexWhere((item) => item.id == tappedDto.id)
        .clamp(0, viewerDtos.length - 1);
    final rawPostsById = <String, Map<String, dynamic>>{
      for (final entry in viewerEntries) entry.dto!.id: entry.raw,
    };

    final route = _isVideoPost(tappedDto)
        ? AppRoutePaths.videoViewer(index: '$initialIndex')
        : AppRoutePaths.mediaViewer(category: 'circle', index: '$initialIndex');
    final relationshipState = ref.read(userRelationshipStateProvider);
    final postInteractionState = ref.read(postInteractionStateProvider);
    final result = await context.push<Object?>(
      route,
      extra: MediaViewerExtra(
        posts: viewerDtos.map(PostSummaryView.fromDto).toList(growable: false),
        dtoPosts: viewerDtos,
        initialIndex: initialIndex,
        category: 'circle',
        source: 'circle',
        circleId: widget.circleId,
        rawPostsById: rawPostsById,
        interactionSnapshot: MediaViewerInteractionSnapshot(
          followingUsers: Set<String>.from(
            relationshipState.followingProfileIds,
          ),
          likedPosts: Set<String>.from(postInteractionState.likedPostIds),
          savedPosts: Set<String>.from(postInteractionState.savedPostIds),
          postLikesCount: {
            for (final entry in viewerEntries)
              entry.dto!.id: postInteractionState.likeCountFor(
                entry.dto!.id,
                fallback:
                    (entry.raw['likeCount'] as num?)?.toInt() ??
                    (entry.raw['likes'] as num?)?.toInt() ??
                    entry.dto!.likeCount,
              ),
          },
          postBookmarksCount: {
            for (final entry in viewerEntries)
              entry.dto!.id: postInteractionState.bookmarkCountFor(
                entry.dto!.id,
                fallback:
                    (entry.raw['favoriteCount'] as num?)?.toInt() ??
                    (entry.raw['bookmarkCount'] as num?)?.toInt() ??
                    entry.dto!.favoriteCount,
              ),
          },
          postSharesCount: {
            for (final entry in viewerEntries)
              entry.dto!.id: postInteractionState.shareCountFor(
                entry.dto!.id,
                fallback:
                    (entry.raw['shareCount'] as num?)?.toInt() ??
                    entry.dto!.shareCount,
              ),
          },
        ),
      ),
    );
    if (result is MediaViewerResult) {
      _applyViewerResult(result);
    }
  }

  PostBaseDto? _tryParsePost(Map<String, dynamic> item) {
    try {
      return postBaseDtoFromMap(item);
    } catch (_) {
      return null;
    }
  }

  bool _supportsViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }

  bool _isVideoPost(PostBaseDto post) {
    return post.isVideoLike;
  }

  void _applyViewerResult(MediaViewerResult result) {
    ref.read(userRelationshipStateProvider.notifier).applyViewerResult(result);
    ref.read(postInteractionStateProvider.notifier).applyViewerResult(result);
    setState(() {
      _feedItems = applyMediaViewerResultToFeedItems(_feedItems, result);
    });
  }

  Widget _buildGridItem(
    Map<String, dynamic> item,
    Color fg,
    Color fgSecondary, {
    required Color backgroundColor,
    required Color borderColor,
    required VoidCallback onTap,
  }) {
    final cover = (item['coverUrl'] ?? item['thumbnailUrl'] ?? '').toString();
    final imageUrls = item['imageUrls'];
    final resolvedCover = cover.isNotEmpty
        ? cover
        : (imageUrls is List && imageUrls.isNotEmpty
              ? imageUrls[0].toString()
              : '');
    final likeCount = item['likeCount'] ?? item['likes'] ?? 0;
    final typeLabel = _itemTypeLabel(item);
    final title = _itemTitle(item);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: borderColor.withValues(alpha: 0.14)),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withValues(
                alpha: widget.isDark ? 0.18 : 0.06,
              ),
              blurRadius: AppSpacing.md,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            ClipRRect(
              borderRadius: BorderRadius.vertical(
                top: Radius.circular(AppSpacing.largeBorderRadius),
              ),
              child: AspectRatio(
                aspectRatio: _creationGridCoverAspectRatio,
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    if (resolvedCover.isNotEmpty)
                      Image.network(
                        resolvedCover,
                        fit: BoxFit.cover,
                        errorBuilder: (_, _, _) => ColoredBox(
                          color: fgSecondary.withValues(alpha: 0.12),
                          child: Icon(CupertinoIcons.photo, color: fgSecondary),
                        ),
                      )
                    else
                      ColoredBox(
                        color: fgSecondary.withValues(alpha: 0.12),
                        child: Icon(CupertinoIcons.photo, color: fgSecondary),
                      ),
                    Positioned(
                      top: AppSpacing.sm,
                      left: AppSpacing.sm,
                      child: Container(
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.sm,
                          vertical: AppSpacing.intraGroupXs,
                        ),
                        decoration: BoxDecoration(
                          color: Colors.black.withValues(alpha: 0.32),
                          borderRadius: BorderRadius.circular(
                            AppSpacing.circularBorderRadius,
                          ),
                        ),
                        child: Text(
                          typeLabel,
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: AppTypography.xs,
                            fontWeight: AppTypography.semiBold,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.all(AppSpacing.containerSm),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      fontWeight: AppTypography.semiBold,
                      color: fg,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Row(
                    children: [
                      Icon(
                        CupertinoIcons.heart_fill,
                        size: AppSpacing.iconSmall,
                        color: AppColors.error.withValues(alpha: 0.9),
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      Text(
                        '$likeCount',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          fontWeight: AppTypography.medium,
                          color: fgSecondary,
                        ),
                      ),
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

  Widget _buildListItem(
    Map<String, dynamic> item,
    Color fg,
    Color fgSecondary, {
    required Color backgroundColor,
    required Color borderColor,
    required VoidCallback onTap,
  }) {
    final cover = (item['coverUrl'] ?? item['thumbnailUrl'] ?? '').toString();
    final likeCount = item['likeCount'] ?? item['likes'] ?? 0;
    final typeLabel = _itemTypeLabel(item);
    final title = _itemTitle(item);
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        padding: EdgeInsets.all(AppSpacing.containerSm),
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(color: borderColor.withValues(alpha: 0.12)),
        ),
        child: Row(
          children: [
            ClipRRect(
              borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              child: SizedBox(
                width: AppSpacing.followButtonWidth + AppSpacing.intraGroupMd,
                height: AppSpacing.followButtonWidth + AppSpacing.intraGroupMd,
                child: cover.isNotEmpty
                    ? Image.network(
                        cover,
                        fit: BoxFit.cover,
                        errorBuilder: (_, _, _) => Container(
                          color: fgSecondary.withValues(alpha: 0.1),
                          child: Icon(CupertinoIcons.photo, color: fgSecondary),
                        ),
                      )
                    : Container(
                        color: fgSecondary.withValues(alpha: 0.1),
                        child: Icon(CupertinoIcons.photo, color: fgSecondary),
                      ),
              ),
            ),
            SizedBox(width: AppSpacing.containerSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    typeLabel,
                    style: TextStyle(
                      fontSize: AppTypography.sm,
                      color: AppColors.primaryColor,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Text(
                    title,
                    style: TextStyle(
                      fontSize: AppTypography.base,
                      color: fg,
                      fontWeight: AppTypography.medium,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs),
                  Row(
                    children: [
                      Icon(
                        CupertinoIcons.heart_fill,
                        size: AppSpacing.iconSmall,
                        color: AppColors.error.withValues(alpha: 0.9),
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      Text(
                        '赞 $likeCount',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
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

  String _itemTitle(Map<String, dynamic> item) {
    final candidates = [
      item['title'],
      item['body'],
      item['caption'],
      item['summary'],
    ];
    for (final candidate in candidates) {
      final text = candidate?.toString().trim() ?? '';
      if (text.isNotEmpty) {
        return text;
      }
    }
    return _itemTypeLabel(item);
  }

  Widget _buildEmpty(Color fgSecondary) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Container(
              width: AppSpacing.xl * 2,
              height: AppSpacing.xl * 2,
              decoration: BoxDecoration(
                color: fgSecondary.withValues(alpha: 0.08),
                shape: BoxShape.circle,
              ),
              child: Icon(
                CupertinoIcons.photo_on_rectangle,
                size: AppSpacing.xl,
                color: fgSecondary,
              ),
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              UITextConstants.circleNoCreations,
              style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard(Color fgSecondary) {
    return Center(
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              CupertinoIcons.exclamationmark_circle,
              color: AppColors.error,
              size: AppSpacing.iconLarge,
            ),
            SizedBox(height: AppSpacing.sm),
            Text(
              UITextConstants.loadFailed,
              style: TextStyle(
                color: fgSecondary,
                fontSize: AppTypography.base,
              ),
            ),
            SizedBox(height: AppSpacing.sm),
            CupertinoButton(
              onPressed: _loadFeed,
              child: Text(
                UITextConstants.retry,
                style: TextStyle(
                  color: AppColors.primaryColor,
                  fontSize: AppTypography.base,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSurface({
    required Widget child,
    required Color backgroundColor,
    required Color borderColor,
    EdgeInsetsGeometry padding = const EdgeInsets.symmetric(
      vertical: AppSpacing.containerSm,
    ),
  }) {
    return Container(
      padding: padding,
      decoration: BoxDecoration(
        color: backgroundColor,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        border: Border.all(color: borderColor.withValues(alpha: 0.12)),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: widget.isDark ? 0.16 : 0.05),
            blurRadius: AppSpacing.md,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: child,
    );
  }
}

class _ViewModeButton extends StatelessWidget {
  const _ViewModeButton({
    required this.icon,
    required this.tooltip,
    required this.selected,
    required this.fgSecondary,
    required this.borderColor,
    required this.backgroundColor,
    required this.onPressed,
  });

  final IconData icon;
  final String tooltip;
  final bool selected;
  final Color fgSecondary;
  final Color borderColor;
  final Color backgroundColor;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Tooltip(
      message: tooltip,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.zero,
        onPressed: onPressed,
        child: Container(
          padding: EdgeInsets.all(AppSpacing.sm),
          decoration: BoxDecoration(
            color: selected
                ? AppColors.primaryColor.withValues(alpha: 0.12)
                : backgroundColor,
            borderRadius: BorderRadius.circular(
              AppSpacing.circularBorderRadius,
            ),
            border: Border.all(
              color: selected
                  ? AppColors.primaryColor.withValues(alpha: 0.24)
                  : borderColor.withValues(alpha: 0.12),
            ),
          ),
          child: Icon(
            icon,
            size: AppSpacing.iconSmall,
            color: selected ? AppColors.primaryColor : fgSecondary,
          ),
        ),
      ),
    );
  }
}

class _CupertinoFilterChip extends StatelessWidget {
  const _CupertinoFilterChip({
    required this.label,
    required this.selected,
    required this.fg,
    required this.fgSecondary,
    required this.onPressed,
  });

  final String label;
  final bool selected;
  final Color fg;
  final Color fgSecondary;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onPressed,
      child: DecoratedBox(
        decoration: BoxDecoration(
          color: selected
              ? AppColors.primaryColor.withValues(alpha: 0.12)
              : null,
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
          border: Border.all(
            color: selected
                ? AppColors.primaryColor.withValues(alpha: 0.45)
                : fgSecondary.withValues(alpha: 0.2),
          ),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? fg : fgSecondary,
              fontWeight: AppTypography.semiBold,
              fontSize: AppTypography.sm,
            ),
          ),
        ),
      ),
    );
  }
}
