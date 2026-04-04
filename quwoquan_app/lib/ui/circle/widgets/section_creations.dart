import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_tab.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
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
    this.inlineScroll = false,
  });

  final String circleId;
  final bool isDark;
  final CircleRole role;
  final bool inlineScroll;

  @override
  ConsumerState<SectionCreations> createState() => _SectionCreationsState();
}

class _SectionCreationsState extends ConsumerState<SectionCreations> {
  bool _isLoading = true;
  String? _error;
  List<Map<String, dynamic>> _feedItems = const [];
  String? _circleCategoryId;

  List<IdentityFilterConfig> get _identityFilters =>
      ContentUIConfig.creationIdentityFilters;

  List<WorkFormatFilterConfig> get _workFormatFilters =>
      ContentUIConfig.workFormatFilters;

  static const double _creationGridCoverAspectRatio = 0.92;
  static const ArticleDistributionProfileConfig
  _circleArticleDistributionProfile = ArticleDistributionProfileConfig(
    id: 'circle_dual_column_with_optional_cover',
    surface: 'circle_dual_column',
    layout: 'cover_top_title_summary_or_text_card',
    coverMode: 'optional_cover',
    summaryLineLimit: 3,
  );

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
      final circleState = ref.read(circleStateProvider(widget.circleId));
      final repo = ref.read(circleRepositoryProvider);
      final query = _feedQueryForState(circleState);
      final circleDetail = await repo.getCircle(widget.circleId);
      final items = await repo.getCircleFeed(
        widget.circleId,
        identity: query.identity,
        type: query.type,
        sort: circleState.sortMode.name,
      );
      if (mounted) {
        setState(() {
          _feedItems = items;
          _circleCategoryId = circleDetail.categoryId;
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
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.semiBold,
          ),
        ) *
        2;
    final summaryHeight =
        _measureSingleLineTextHeight(
          context,
          const TextStyle(fontSize: AppTypography.iosCaption1),
        ) *
        3;
    final metaTextHeight = _measureSingleLineTextHeight(
      context,
      const TextStyle(fontSize: AppTypography.iosCaption1),
    );
    final recommendationHeight =
        _measureSingleLineTextHeight(
          context,
          const TextStyle(
            fontSize: AppTypography.xs,
            fontWeight: AppTypography.semiBold,
          ),
        ) *
        2;
    final metaRowHeight = metaTextHeight > AppSpacing.iconSmall
        ? metaTextHeight
        : AppSpacing.iconSmall;
    return coverHeight +
        (AppSpacing.postPreviewCardPadding * 2) +
        AppSpacing.intraGroupSm +
        titleHeight +
        AppSpacing.xs +
        summaryHeight +
        AppSpacing.intraGroupXs +
        recommendationHeight +
        metaRowHeight +
        AppSpacing.sm;
  }

  @override
  Widget build(BuildContext context) {
    final circleState = ref.watch(circleStateProvider(widget.circleId));
    final circleCtrl = ref.read(circleStateProvider(widget.circleId).notifier);
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

    final contentSurface = _buildSurface(
      backgroundColor: bgSecondary,
      borderColor: borderColor,
      padding: EdgeInsets.zero,
      child: _buildContent(circleState, fgSecondary),
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
                _buildIdentityFilterRow(circleState, circleCtrl, fg, fgSecondary),
                if (_isWorkLikeSubTab(circleState.activeSubTab)) ...[
                  SizedBox(height: AppSpacing.sm),
                  _buildWorkFormatFilterRow(circleState, circleCtrl, fg, fgSecondary),
                ],
                if (_isAdminOrOwner) ...[
                  SizedBox(height: AppSpacing.sm),
                  _buildSortControls(circleState, circleCtrl, fg, fgSecondary),
                  SizedBox(height: AppSpacing.xs),
                  _buildViewModeToggle(
                    circleState,
                    circleCtrl,
                    fgSecondary: fgSecondary,
                    borderColor: borderColor,
                    backgroundColor: bgTertiary,
                  ),
                ],
              ],
            ),
          ),
          SizedBox(height: AppSpacing.sm),
          if (widget.inlineScroll)
            contentSurface
          else
            Expanded(child: contentSurface),
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
    CircleState circleState,
    CircleStateNotifier circleCtrl,
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
              final selected = circleState.activeSubTab == tab;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: _CupertinoFilterChip(
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                  selected: selected,
                  fg: fg,
                  fgSecondary: fgSecondary,
                  onPressed: () {
                    circleCtrl.setSubTab(tab);
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
    CircleState circleState,
    CircleStateNotifier circleCtrl,
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
              final selected = circleState.activeWorkFormat == format;
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: _CupertinoFilterChip(
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                  selected: selected,
                  fg: fg,
                  fgSecondary: fgSecondary,
                  onPressed: () {
                    circleCtrl.setWorkFormat(format);
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
    CircleState circleState,
    CircleStateNotifier circleCtrl,
    Color fg,
    Color fgSecondary,
  ) {
    final activeSortMode = circleState.sortMode;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        children: CreationSortMode.values.map((mode) {
          final selected = mode == activeSortMode;
          return Padding(
            padding: EdgeInsets.only(right: AppSpacing.sm),
            child: GestureDetector(
              onTap: () {
                circleCtrl.setSortMode(mode);
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
                            ? AppColors.white.withValues(alpha: 0.1)
                            : AppColors.black.withValues(alpha: 0.06))
                      : null,
                  borderRadius: BorderRadius.circular(
                    AppSpacing.circularBorderRadius,
                  ),
                  border: Border.all(
                    color: widget.isDark
                        ? AppColors.white.withValues(alpha: 0.24)
                        : AppColors.black.withValues(alpha: 0.12),
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
    CircleState circleState,
    CircleStateNotifier circleCtrl, {
    required Color fgSecondary,
    required Color borderColor,
    required Color backgroundColor,
  }) {
    final activeMode = circleState.viewMode;
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
            onPressed: () => circleCtrl.setViewMode(CreationViewMode.grid),
          ),
          SizedBox(width: AppSpacing.xs),
          _ViewModeButton(
            icon: CupertinoIcons.rectangle_grid_1x2,
            tooltip: '列表视图',
            selected: activeMode == CreationViewMode.list,
            fgSecondary: fgSecondary,
            borderColor: borderColor,
            backgroundColor: backgroundColor,
            onPressed: () => circleCtrl.setViewMode(CreationViewMode.list),
          ),
        ],
      ),
    );
  }

  Widget _buildContent(CircleState circleState, Color fgSecondary) {
    if (_isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    if (_error != null) {
      return _buildErrorCard(fgSecondary);
    }

    final activeSubTab = circleState.activeSubTab;
    final activeWorkFormat = circleState.activeWorkFormat;
    final filtered = _feedItems
        .where((item) {
          return _matchesIdentityFilter(item, activeSubTab) &&
              _matchesWorkFormat(item, activeSubTab, activeWorkFormat);
        })
        .toList(growable: true);

    if (activeSubTab == CreationSubTab.article ||
        activeWorkFormat == CreationWorkFormat.note) {
      filtered.sort((left, right) {
        final leftHasTemplate = (left['articleTemplate'] ?? '')
            .toString()
            .trim()
            .isNotEmpty;
        final rightHasTemplate = (right['articleTemplate'] ?? '')
            .toString()
            .trim()
            .isNotEmpty;
        if (leftHasTemplate != rightHasTemplate) {
          return leftHasTemplate ? -1 : 1;
        }
        final leftHasCover = _itemCoverUrl(left).isNotEmpty;
        final rightHasCover = _itemCoverUrl(right).isNotEmpty;
        if (leftHasCover != rightHasCover) {
          return leftHasCover ? -1 : 1;
        }
        return 0;
      });
    }

    if (filtered.isEmpty) {
      return _buildEmpty(fgSecondary);
    }

    if (circleState.viewMode == CreationViewMode.list) {
      return ListView.separated(
        physics: widget.inlineScroll
            ? const NeverScrollableScrollPhysics()
            : const BouncingScrollPhysics(),
        shrinkWrap: widget.inlineScroll,
        padding: EdgeInsets.fromLTRB(
          AppSpacing.postPreviewGridSpacing,
          AppSpacing.postPreviewGridSpacing,
          AppSpacing.postPreviewGridSpacing,
          AppSpacing.postPreviewSectionPadding,
        ),
        itemCount: filtered.length,
        separatorBuilder: (_, _) =>
            SizedBox(height: AppSpacing.postPreviewGridSpacing),
        itemBuilder: (context, index) {
          final item = filtered[index];
          return _buildListItem(
            item,
            fgSecondary,
            onTap: () => _openMediaViewer(context, item, filtered),
          );
        },
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final itemWidth =
            (constraints.maxWidth -
                (AppSpacing.postPreviewGridSpacing * 2) -
                AppSpacing.postPreviewGridSpacing) /
            2;
        return GridView.builder(
          physics: widget.inlineScroll
              ? const NeverScrollableScrollPhysics()
              : const BouncingScrollPhysics(),
          shrinkWrap: widget.inlineScroll,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewSectionPadding,
          ),
          gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
            crossAxisCount: 2,
            mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
            crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
            mainAxisExtent: _gridItemMainAxisExtent(context, itemWidth),
          ),
          itemCount: filtered.length,
          itemBuilder: (context, index) {
            final item = filtered[index];
            return _buildGridItem(
              item,
              fgSecondary,
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
    final rawPostsById = <String, Map<String, Object?>>{
      for (final entry in viewerEntries)
        entry.dto!.id: Map<String, Object?>.from(entry.raw),
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
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_isArticleItem(item)) {
      return _buildArticleGridItem(item, fgSecondary, onTap: onTap);
    }
    final typeLabel = _itemTypeLabel(item);
    return PostPreviewCard(
      isDark: widget.isDark,
      title: _itemHeadlineText(item),
      supportingText: '',
      coverUrl: _itemCoverUrl(item),
      mediaAspectRatio: _creationGridCoverAspectRatio,
      showVideoBadge: _isVideoItem(item),
      mediaOverlay: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.intraGroupXs,
        ),
        decoration: BoxDecoration(
          color: AppColors.black.withValues(alpha: 0.32),
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Text(
          typeLabel,
          style: TextStyle(
            color: AppColors.white,
            fontSize: AppTypography.xs,
            fontWeight: AppTypography.semiBold,
          ),
        ),
      ),
      onTap: onTap,
      footer: Row(
        children: [
          PostCardMetric(
            icon: CupertinoIcons.heart_fill,
            label: '${_itemLikeCount(item)}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildListItem(
    Map<String, dynamic> item,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_isArticleItem(item)) {
      return _buildArticleListItem(item, fgSecondary, onTap: onTap);
    }
    final typeLabel = _itemTypeLabel(item);
    return PostPreviewListTile(
      isDark: widget.isDark,
      eyebrowText: typeLabel,
      title: _itemHeadlineText(item),
      supportingText: _itemSupportingText(item),
      coverUrl: _itemCoverUrl(item),
      showVideoBadge: _isVideoItem(item),
      onTap: onTap,
      footer: Row(
        children: [
          PostCardMetric(
            icon: CupertinoIcons.heart_fill,
            label: '赞 ${_itemLikeCount(item)}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: Icon(
        CupertinoIcons.chevron_forward,
        size: AppSpacing.iconSmall,
        color: fgSecondary,
      ),
    );
  }

  Widget _buildArticleGridItem(
    Map<String, dynamic> item,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    final recommendationLabel = _articleRecommendationLabel(item);
    final authorName = (item['authorNickname'] ?? item['displayName'] ?? '')
        .toString()
        .trim();
    return PostPreviewCard(
      key: ValueKey<String>('circle-article-grid-${_itemId(item)}'),
      isDark: widget.isDark,
      title: _itemHeadlineText(item),
      supportingText: _itemSupportingText(item),
      supportingTextMaxLines:
          _circleArticleDistributionProfile.summaryLineLimit,
      coverUrl: _itemCoverUrl(item),
      mediaAspectRatio: _creationGridCoverAspectRatio,
      mediaOverlay: _articleTemplateBadge(item),
      onTap: onTap,
      footer: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (recommendationLabel.isNotEmpty) ...[
            Text(
              recommendationLabel,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: AppColors.primaryColor,
                fontWeight: AppTypography.semiBold,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs / 2),
          ],
          Row(
            children: [
              Expanded(
                child: Text(
                  authorName,
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
                icon: CupertinoIcons.heart_fill,
                label: '${_itemLikeCount(item)}',
                color: fgSecondary,
                iconColor: AppColors.error.withValues(alpha: 0.9),
                textStyle: TextStyle(
                  fontSize: AppTypography.iosCaption1,
                  color: fgSecondary,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildArticleListItem(
    Map<String, dynamic> item,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    final recommendationLabel = _articleRecommendationLabel(item);
    final authorName = (item['authorNickname'] ?? item['displayName'] ?? '')
        .toString()
        .trim();
    return PostPreviewListTile(
      key: ValueKey<String>('circle-article-list-${_itemId(item)}'),
      isDark: widget.isDark,
      eyebrowText: recommendationLabel.isNotEmpty
          ? recommendationLabel
          : '笔记 · ${_articleTemplateLabel(item)}',
      eyebrowColor: AppColors.primaryColor,
      title: _itemHeadlineText(item),
      supportingText: _itemSupportingText(item),
      supportingTextMaxLines:
          _circleArticleDistributionProfile.summaryLineLimit,
      coverUrl: _itemCoverUrl(item),
      hideThumbnailWhenNoCover: true,
      onTap: onTap,
      footer: Row(
        children: [
          Expanded(
            child: Text(
              authorName,
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
            icon: CupertinoIcons.heart_fill,
            label: '赞 ${_itemLikeCount(item)}',
            color: fgSecondary,
            iconColor: AppColors.error.withValues(alpha: 0.9),
            textStyle: TextStyle(
              fontSize: AppTypography.iosCaption1,
              color: fgSecondary,
            ),
          ),
        ],
      ),
      trailing: Icon(
        CupertinoIcons.chevron_forward,
        size: AppSpacing.iconSmall,
        color: fgSecondary,
      ),
    );
  }

  String _itemCoverUrl(Map<String, dynamic> item) {
    final cover = (item['coverUrl'] ?? item['thumbnailUrl'] ?? '').toString();
    if (cover.isNotEmpty) return cover;
    final imageUrls = item['imageUrls'];
    if (imageUrls is List && imageUrls.isNotEmpty) {
      return imageUrls.first.toString();
    }
    return '';
  }

  String _itemId(Map<String, dynamic> item) {
    return (item['postId'] ?? item['id'] ?? '').toString();
  }

  bool _isArticleItem(Map<String, dynamic> item) {
    return (item['contentType'] ?? item['type'] ?? '').toString() == 'article';
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

  String _itemHeadlineText(Map<String, dynamic> item) {
    final title = _itemTitle(item);
    if (title.isNotEmpty) {
      return title;
    }
    return _itemTypeLabel(item);
  }

  String _itemSupportingText(Map<String, dynamic> item) {
    final headline = _itemHeadlineText(item);
    final summary = (item['summary'] ?? '').toString().trim();
    if (_isArticleItem(item) && summary.isNotEmpty && summary != headline) {
      return summary;
    }
    final body =
        (item['body'] ??
                item['description'] ??
                item['content'] ??
                item['caption'] ??
                '')
            .toString()
            .trim();
    if (body.isEmpty || body == headline) {
      return '';
    }
    return body;
  }

  Widget _articleTemplateBadge(Map<String, dynamic> item) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.intraGroupXs,
      ),
      decoration: BoxDecoration(
        color: AppColors.black.withValues(alpha: 0.32),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      ),
      child: Text(
        _articleTemplateLabel(item),
        style: TextStyle(
          color: AppColors.white,
          fontSize: AppTypography.xs,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
  }

  String _articleTemplateLabel(Map<String, dynamic> item) {
    return articleTemplatePresetFromString(
      item['articleTemplate']?.toString(),
    ).label;
  }

  List<String> _recommendedArticleTemplatesForCircle() {
    final categoryId = (_circleCategoryId ?? '').trim();
    if (categoryId.isEmpty) {
      return const <String>[];
    }
    for (final recommendation
        in ContentUIConfig.articleTemplateRecommendations) {
      if (recommendation.categoryId == categoryId) {
        return recommendation.recommendedArticleTemplates;
      }
    }
    return const <String>[];
  }

  String _articleRecommendationLabel(Map<String, dynamic> item) {
    final recommended = _recommendedArticleTemplatesForCircle();
    if (recommended.isEmpty) {
      return '';
    }
    final templateId = (item['articleTemplate'] ?? '').toString().trim();
    if (templateId.isNotEmpty && recommended.contains(templateId)) {
      return '频道推荐 · ${articleTemplatePresetFromString(templateId).label}';
    }
    final labels = recommended
        .take(2)
        .map((value) => articleTemplatePresetFromString(value).label)
        .join(' / ');
    if (labels.isEmpty) {
      return '';
    }
    return '频道推荐 · $labels';
  }

  int _itemLikeCount(Map<String, dynamic> item) {
    return (item['likeCount'] as num?)?.toInt() ??
        (item['likes'] as num?)?.toInt() ??
        0;
  }

  bool _isVideoItem(Map<String, dynamic> item) {
    return (item['type'] ?? '').toString() == 'video' ||
        (item['videoUrl']?.toString().trim() ?? '').isNotEmpty;
  }

  Widget _buildEmpty(Color fgSecondary) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final ultraCompact =
            constraints.maxHeight < AppSpacing.minInteractiveSize;
        final compact = !ultraCompact && constraints.maxHeight < 132;
        final horizontalPadding = compact
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final verticalPadding = ultraCompact
            ? 0.0
            : compact
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final iconContainerSize = compact
            ? AppSpacing.buttonHeightLg
            : AppSpacing.xl * 2;
        final iconSize = compact ? AppSpacing.iconMedium : AppSpacing.xl;
        final textStyle = TextStyle(
          fontSize: compact ? AppTypography.base : AppTypography.md,
          color: fgSecondary,
        );
        final text = Text(
          UITextConstants.circleNoCreations,
          style: textStyle,
          maxLines: ultraCompact ? 1 : 2,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
        );

        if (ultraCompact) {
          return Center(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
              child: text,
            ),
          );
        }

        final iconBubble = Container(
          width: iconContainerSize,
          height: iconContainerSize,
          decoration: BoxDecoration(
            color: fgSecondary.withValues(alpha: 0.08),
            shape: BoxShape.circle,
          ),
          child: Icon(
            CupertinoIcons.photo_on_rectangle,
            size: iconSize,
            color: fgSecondary,
          ),
        );

        if (compact) {
          final compactContentWidth =
              (constraints.maxWidth - (horizontalPadding * 2))
                  .clamp(0.0, double.infinity)
                  .toDouble();
          return Center(
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: horizontalPadding,
                vertical: verticalPadding,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: compactContentWidth),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    iconBubble,
                    SizedBox(width: AppSpacing.sm),
                    Expanded(child: text),
                  ],
                ),
              ),
            ),
          );
        }

        return Center(
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: horizontalPadding,
              vertical: verticalPadding,
            ),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                iconBubble,
                SizedBox(height: AppSpacing.md),
                text,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildErrorCard(Color fgSecondary) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final ultraCompact = constraints.maxHeight < AppSpacing.buttonHeightXs;
        final compact = !ultraCompact && constraints.maxHeight < 120;
        final horizontalPadding = compact
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final verticalPadding = ultraCompact
            ? 0.0
            : compact
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final iconSize = compact ? AppSpacing.iconMedium : AppSpacing.iconLarge;
        final text = Text(
          UITextConstants.loadFailed,
          style: TextStyle(
            color: fgSecondary,
            fontSize: compact ? AppTypography.sm : AppTypography.base,
          ),
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          textAlign: TextAlign.center,
        );

        if (ultraCompact) {
          return Center(
            child: Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontalPadding),
              child: text,
            ),
          );
        }

        if (compact) {
          final compactContentWidth =
              (constraints.maxWidth - (horizontalPadding * 2))
                  .clamp(0.0, double.infinity)
                  .toDouble();
          return Center(
            child: Padding(
              padding: EdgeInsets.symmetric(
                horizontal: horizontalPadding,
                vertical: verticalPadding,
              ),
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: compactContentWidth),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.exclamationmark_circle,
                      color: AppColors.error,
                      size: iconSize,
                    ),
                    SizedBox(width: AppSpacing.sm),
                    Expanded(child: text),
                  ],
                ),
              ),
            ),
          );
        }

        return Center(
          child: Padding(
            padding: EdgeInsets.symmetric(
              horizontal: horizontalPadding,
              vertical: verticalPadding,
            ),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(
                  CupertinoIcons.exclamationmark_circle,
                  color: AppColors.error,
                  size: iconSize,
                ),
                SizedBox(height: AppSpacing.sm),
                text,
                SizedBox(height: AppSpacing.sm),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
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
      },
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
            color: AppColors.black.withValues(alpha: widget.isDark ? 0.16 : 0.05),
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
