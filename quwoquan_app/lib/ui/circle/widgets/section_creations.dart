import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/components/post/post_preview_list_tile.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/circle/models/circle_tab.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';
import 'package:quwoquan_app/ui/content/widgets/record_post_card.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';
import 'package:quwoquan_app/ui/circle/providers/circle_state_provider.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';

/// 圈子"创作"板块：SubTab 过滤 + 排序 + 二列网格。
///
/// 主数据为 [CircleHubFeedPostEntry]（含 [PostBaseDto] + 写回用 raw）；旧 Map 工具方法仅作
/// wire 兼容层，新逻辑应优先读 `entry.dto`。
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
  UiErrorSemantic? _errorSemantic;
  List<CircleHubFeedPostEntry> _feedEntries = const [];
  String? _circleCategoryId;

  List<UserProfileSubTabConfig> get _creationFilters =>
      UserProfileUIConfig.creationSubTabs;

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
      _errorSemantic = null;
    });
    try {
      final circleState = ref.read(circleStateProvider(widget.circleId));
      final repo = ref.read(circleRepositoryProvider);
      final query = _feedQueryForState(circleState);
      String? circleCategoryId;
      try {
        final circleDetail = await repo.getCircle(widget.circleId);
        circleCategoryId = circleDetail.categoryId;
      } catch (_) {
        // 频道推荐标签只是增强信息；未知圈子或详情缺失不应阻断作品区本体，
        // 否则空态场景会被误打成错误态。
        circleCategoryId = null;
      }
      final items = await repo.getCircleFeed(
        widget.circleId,
        identity: query.identity,
        type: query.type,
        sort: circleState.sortMode.name,
      );
      if (mounted) {
        setState(() {
          _feedEntries = items
              .map(CircleHubFeedPostEntry.fromPostDto)
              .toList(growable: false);
          _circleCategoryId = circleCategoryId;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorSemantic = runtimeErrorSemantic(
            context,
            error: e,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );
        });
      }
    }
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

    return LayoutBuilder(
      builder: (context, constraints) {
        final compactHeight = constraints.maxHeight < 320;
        final compactEmptyState =
            compactHeight &&
            !_isLoading &&
            _errorSemantic == null &&
            _feedEntries.isEmpty;
        final outerHorizontal = compactHeight
            ? AppSpacing.containerSm
            : AppSpacing.containerMd;
        final outerTop = compactHeight
            ? (compactEmptyState ? AppSpacing.zero : AppSpacing.intraGroupXs)
            : AppSpacing.containerSm;
        final outerBottom = compactHeight
            ? (compactEmptyState
                  ? AppSpacing.intraGroupXs
                  : AppSpacing.containerSm)
            : AppSpacing.containerLg;
        final sectionGap = compactHeight
            ? AppSpacing.intraGroupXs
            : AppSpacing.sm;
        final filterGap = compactHeight ? AppSpacing.xs : AppSpacing.sm;

        final filterSurface = _buildSurface(
          backgroundColor: bgSecondary,
          borderColor: borderColor,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              _buildCreationFilterRow(circleState, circleCtrl, fg, fgSecondary),
              if (_isAdminOrOwner && !compactHeight) ...[
                SizedBox(height: filterGap),
                _buildSortControls(circleState, circleCtrl, fg, fgSecondary),
                SizedBox(
                  height: compactHeight
                      ? AppSpacing.intraGroupXs
                      : AppSpacing.xs,
                ),
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
        );

        if (compactEmptyState) {
          return Padding(
            padding: EdgeInsets.fromLTRB(
              outerHorizontal,
              outerTop,
              outerHorizontal,
              outerBottom,
            ),
            child: contentSurface,
          );
        }

        final child = Column(
          mainAxisSize: MainAxisSize.max,
          children: [
            if (!compactEmptyState && compactHeight)
              Flexible(
                fit: FlexFit.loose,
                child: SingleChildScrollView(child: filterSurface),
              )
            else if (!compactEmptyState)
              filterSurface,
            if (!compactEmptyState) SizedBox(height: sectionGap),
            if (widget.inlineScroll)
              contentSurface
            else
              Flexible(fit: FlexFit.tight, child: contentSurface),
          ],
        );

        return Padding(
          padding: EdgeInsets.fromLTRB(
            outerHorizontal,
            outerTop,
            outerHorizontal,
            outerBottom,
          ),
          child: child,
        );
      },
    );
  }

  bool get _isAdminOrOwner =>
      widget.role == CircleRole.owner || widget.role == CircleRole.admin;

  ({String? identity, String? type}) _feedQueryForState(CircleState state) {
    switch (state.activeSubTab) {
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

  static const Key creationFilterButtonKey = ValueKey<String>(
    'circle-creations-filter-button',
  );

  /// 二级过滤（全部/图片/视频/文字）：与用户主页同范式，去胶囊横滑，
  /// 收敛为最右侧单一过滤入口（当前过滤名 + 漏斗图标），点击弹层选择。
  Widget _buildCreationFilterRow(
    CircleState circleState,
    CircleStateNotifier circleCtrl,
    Color fg,
    Color fgSecondary,
  ) {
    final activeFilter = _creationFilters.firstWhere(
      (filter) => _creationSubTabForId(filter.id) == circleState.activeSubTab,
      orElse: () => _creationFilters.first,
    );
    final activeLabel = UITextConstants.contentLabelForKey(
      activeFilter.labelKey,
    );
    final accent = AppColors.iosAccent(context);
    final isAll = circleState.activeSubTab == CreationSubTab.all;
    return Padding(
      padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: <Widget>[
          CupertinoButton(
            key: creationFilterButtonKey,
            padding: EdgeInsets.symmetric(
              horizontal: AppSpacing.containerSm,
              vertical: AppSpacing.intraGroupXs,
            ),
            minimumSize: Size.zero,
            onPressed: () => _openCreationFilterSheet(circleState, circleCtrl),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: <Widget>[
                Text(
                  activeLabel,
                  style: TextStyle(
                    fontSize: AppTypography.iosSubheadline,
                    fontWeight: AppTypography.medium,
                    color: isAll ? fg : accent,
                  ),
                ),
                SizedBox(width: AppSpacing.intraGroupXs),
                Icon(
                  CupertinoIcons.line_horizontal_3_decrease,
                  size: AppSpacing.iconSmall,
                  color: isAll ? fgSecondary : accent,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Future<void> _openCreationFilterSheet(
    CircleState circleState,
    CircleStateNotifier circleCtrl,
  ) async {
    final selected = await showCupertinoModalPopup<CreationSubTab>(
      context: context,
      builder: (sheetContext) => CupertinoActionSheet(
        title: Text(UITextConstants.profileWorksFilterTitle),
        actions: <Widget>[
          for (final filter in _creationFilters)
            CupertinoActionSheetAction(
              key: ValueKey<String>(
                'circle-creations-filter-option-${filter.id}',
              ),
              onPressed: () => Navigator.of(
                sheetContext,
              ).pop(_creationSubTabForId(filter.id)),
              child: Text(UITextConstants.contentLabelForKey(filter.labelKey)),
            ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(sheetContext).pop(),
          child: Text(UITextConstants.cancel),
        ),
      ),
    );
    if (selected != null && selected != circleState.activeSubTab) {
      circleCtrl.setSubTab(selected);
      _loadFeed();
    }
  }

  CreationSubTab _creationSubTabForId(String id) {
    switch (id) {
      case 'image':
        return CreationSubTab.image;
      case 'video':
        return CreationSubTab.video;
      case 'article':
        return CreationSubTab.article;
      default:
        return CreationSubTab.all;
    }
  }

  bool _matchesIdentityFilter(
    CircleHubFeedPostEntry entry,
    CreationSubTab tab,
  ) {
    switch (tab) {
      case CreationSubTab.image:
        return _entryDisplayFormat(entry) == 'image';
      case CreationSubTab.video:
        return _entryDisplayFormat(entry) == 'video';
      case CreationSubTab.article:
        return _entryDisplayFormat(entry) == 'note';
      case CreationSubTab.all:
        return true;
    }
  }

  bool _entryIsArticle(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) return d.type == 'article';
    return _rawIsArticle(entry.raw);
  }

  bool _entryIsVideo(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) return d.isVideoLike;
    return _rawIsVideo(entry.raw);
  }

  String _rawIdentity(Map<String, dynamic> item) {
    return (item['contentIdentity'] ??
            (item['type']?.toString() == 'micro' ? 'moment' : 'work'))
        .toString();
  }

  String _rawDisplayFormat(Map<String, dynamic> item) {
    final type = (item['type'] ?? '').toString();
    switch (type) {
      case 'image':
        return 'image';
      case 'video':
        return 'video';
      case 'article':
        return 'note';
      case 'micro':
        return 'micro';
      default:
        return type;
    }
  }

  String _entryIdentity(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) {
      if (d.identity == 'moment') return 'moment';
      return d.identity.isNotEmpty
          ? d.identity
          : (entry.raw['type']?.toString() == 'micro' ? 'moment' : 'work');
    }
    return _rawIdentity(entry.raw);
  }

  String _entryDisplayFormat(CircleHubFeedPostEntry entry) {
    final d = entry.dto;
    if (d != null) {
      switch (d.type) {
        case 'image':
          return 'image';
        case 'video':
          return 'video';
        case 'article':
          return 'note';
        case 'micro':
          return 'micro';
        default:
          return d.type;
      }
    }
    return _rawDisplayFormat(entry.raw);
  }

  String _entryArticleTemplate(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null && rp.articleTemplate.isNotEmpty) return rp.articleTemplate;
    return (entry.raw['articleTemplate'] ?? '').toString();
  }

  String _entryCoverUrl(CircleHubFeedPostEntry entry) => entry.wireCoverUrl;

  String _entryHeadlineText(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null && rp.title.isNotEmpty) return rp.title;
    return _rawHeadlineText(entry.raw);
  }

  String _entrySupportingText(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp == null) return _rawSupportingText(entry.raw);
    final headline = rp.title.isNotEmpty ? rp.title : _entryTypeLabel(entry);
    final summary = rp.body.trim();
    if (_entryIsArticle(entry) && summary.isNotEmpty && summary != headline) {
      return summary;
    }
    return _rawSupportingText(entry.raw);
  }

  int _entryLikeCount(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null) return rp.likeCount;
    return _rawLikeCount(entry.raw);
  }

  String _entryAuthorDisplayName(CircleHubFeedPostEntry entry) {
    return entry.wireAuthorDisplayName.trim();
  }

  String _entryId(CircleHubFeedPostEntry entry) {
    final rp = entry.tryReadPresentation();
    if (rp != null && rp.postId.isNotEmpty) return rp.postId;
    return entry.postIdForKey;
  }

  String _entryTypeLabel(CircleHubFeedPostEntry entry) {
    final identity = _entryIdentity(entry);
    if (identity == 'moment') {
      return UITextConstants.creationFilterMoment;
    }
    switch (_entryDisplayFormat(entry)) {
      case 'image':
        return UITextConstants.workFormatFilterImage;
      case 'video':
        return UITextConstants.workFormatFilterVideo;
      case 'note':
        return UITextConstants.creationSubText;
      default:
        return UITextConstants.homepageContentTypeDefault;
    }
  }

  Widget _entryArticleTemplateBadge(CircleHubFeedPostEntry entry) {
    return _rawArticleTemplateBadge(entry.raw);
  }

  String _entryArticleTemplateLabel(CircleHubFeedPostEntry entry) {
    final id = _entryArticleTemplate(entry);
    return articleTemplatePresetFromString(id.isNotEmpty ? id : null).label;
  }

  String _entryArticleRecommendationLabel(CircleHubFeedPostEntry entry) {
    return _rawArticleRecommendationLabel(entry.raw);
  }

  String _rawTypeLabel(Map<String, dynamic> item) {
    final identity = _rawIdentity(item);
    if (identity == 'moment') {
      return UITextConstants.creationFilterMoment;
    }
    switch (_rawDisplayFormat(item)) {
      case 'image':
        return UITextConstants.workFormatFilterImage;
      case 'video':
        return UITextConstants.workFormatFilterVideo;
      case 'note':
        return UITextConstants.creationSubText;
      default:
        return UITextConstants.homepageContentTypeDefault;
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
    if (_errorSemantic != null) {
      return _buildErrorCard();
    }

    final activeSubTab = circleState.activeSubTab;
    final filtered = _feedEntries
        .where((entry) => _matchesIdentityFilter(entry, activeSubTab))
        .toList(growable: true);

    if (activeSubTab == CreationSubTab.article) {
      filtered.sort((left, right) {
        final leftHasTemplate = _entryArticleTemplate(left).trim().isNotEmpty;
        final rightHasTemplate = _entryArticleTemplate(right).trim().isNotEmpty;
        if (leftHasTemplate != rightHasTemplate) {
          return leftHasTemplate ? -1 : 1;
        }
        final leftHasCover = _entryCoverUrl(left).isNotEmpty;
        final rightHasCover = _entryCoverUrl(right).isNotEmpty;
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
          final entry = filtered[index];
          return _buildListItem(
            entry,
            fgSecondary,
            onTap: () => _openMediaViewer(context, entry, filtered),
          );
        },
      );
    }

    return LayoutBuilder(
      builder: (context, constraints) {
        final columns = AppSpacing.responsiveGridColumns(
          context,
          availableWidth: constraints.maxWidth,
        );
        // 双列瀑布：与用户主页记录流同一范式，卡片高度随内容自适应。
        return MasonryGridView.count(
          physics: widget.inlineScroll
              ? const NeverScrollableScrollPhysics()
              : const BouncingScrollPhysics(),
          shrinkWrap: widget.inlineScroll,
          primary: false,
          padding: EdgeInsets.fromLTRB(
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewGridSpacing,
            AppSpacing.postPreviewSectionPadding,
          ),
          crossAxisCount: columns,
          mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
          crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
          itemCount: filtered.length,
          itemBuilder: (context, index) {
            final entry = filtered[index];
            return _buildGridItem(
              entry,
              fgSecondary,
              onTap: () => _openMediaViewer(context, entry, filtered),
            );
          },
        );
      },
    );
  }

  Future<void> _openMediaViewer(
    BuildContext context,
    CircleHubFeedPostEntry tapped,
    List<CircleHubFeedPostEntry> sourceItems,
  ) async {
    final tappedDto = _tryParsePost(tapped);
    if (tappedDto == null) return;
    if (!_supportsViewer(tappedDto)) return;

    final viewerEntries = sourceItems
        .where((e) {
          final d = _tryParsePost(e);
          return d != null && _supportsViewer(d);
        })
        .toList(growable: false);
    if (viewerEntries.isEmpty) return;

    final viewerDtos = viewerEntries
        .map((e) => _tryParsePost(e)!)
        .toList(growable: false);
    final initialIndex = viewerDtos
        .indexWhere((item) => item.id == tappedDto.id)
        .clamp(0, viewerDtos.length - 1);
    final rawPostsById = <String, MediaViewerPostWireRow>{
      for (final e in viewerEntries)
        _tryParsePost(e)!.id: MediaViewerPostWireRow.fromDynamicMap(
          Map<String, dynamic>.from(e.raw),
        ),
    };

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
              (dto) => ContentSurfaceViewMapper.fromDto(dto, wire: dto.toMap()),
            )
            .toList(growable: false),
        dtoPosts: viewerDtos,
        initialIndex: initialIndex,
        category: 'circle',
        source: 'circle',
        circleId: widget.circleId,
        rawPostsById: rawPostsById,
        interactionSnapshot: interactionSnapshot,
        referralSource: ReferralSource.circlePost,
        feedRequestId: navFeedRequestId,
      ),
    );
    if (result is MediaViewerResult) {
      _applyViewerResult(result);
    }
  }

  PostBaseDto? _tryParsePost(CircleHubFeedPostEntry entry) =>
      entry.tryResolveDto();

  bool _supportsViewer(PostBaseDto post) {
    return post.supportsUnifiedViewer;
  }

  bool _isVideoPost(PostBaseDto post) {
    return post.isVideoLike;
  }

  void _applyViewerResult(MediaViewerResult result) {
    applyMediaViewerResultToInteractionState(ref, result);
    setState(() {
      CircleHubFeedPostEntry.applyResultToList(_feedEntries, result);
    });
  }

  Widget _buildGridItem(
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_entryIsArticle(entry)) {
      return _buildArticleGridItem(entry, fgSecondary, onTap: onTap);
    }
    // 统一记录卡范式：封面 + 唯一交集句 + 标题 + 作者 + 点赞。
    final dto = entry.tryResolveDto();
    if (dto != null) {
      return RecordPostCard(
        key: ValueKey<String>('circle-record-grid-${_entryId(entry)}'),
        post: dto,
        isDark: widget.isDark,
        onTap: onTap,
        // N5：圈子记录卡 → 交集句对象片段点击精确归因为圈子内容（非推荐流）。
        referralSource: ReferralSource.circlePost,
      );
    }
    final typeLabel = _entryTypeLabel(entry);
    return PostPreviewCard(
      isDark: widget.isDark,
      title: _entryHeadlineText(entry),
      supportingText: '',
      coverUrl: _entryCoverUrl(entry),
      mediaAspectRatio: _creationGridCoverAspectRatio,
      showVideoBadge: _entryIsVideo(entry),
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
            label: '${_entryLikeCount(entry)}',
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
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    if (_entryIsArticle(entry)) {
      return _buildArticleListItem(entry, fgSecondary, onTap: onTap);
    }
    final typeLabel = _entryTypeLabel(entry);
    return PostPreviewListTile(
      isDark: widget.isDark,
      eyebrowText: typeLabel,
      title: _entryHeadlineText(entry),
      supportingText: _entrySupportingText(entry),
      coverUrl: _entryCoverUrl(entry),
      showVideoBadge: _entryIsVideo(entry),
      onTap: onTap,
      footer: Row(
        children: [
          PostCardMetric(
            icon: CupertinoIcons.heart_fill,
            label: '赞 ${_entryLikeCount(entry)}',
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
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    final recommendationLabel = _entryArticleRecommendationLabel(entry);
    final authorName = _entryAuthorDisplayName(entry);
    return PostPreviewCard(
      key: ValueKey<String>('circle-article-grid-${_entryId(entry)}'),
      isDark: widget.isDark,
      title: _entryHeadlineText(entry),
      supportingText: _entrySupportingText(entry),
      supportingTextMaxLines:
          _circleArticleDistributionProfile.summaryLineLimit,
      coverUrl: _entryCoverUrl(entry),
      mediaAspectRatio: _creationGridCoverAspectRatio,
      mediaOverlay: _entryArticleTemplateBadge(entry),
      header: IntersectionReasonChip.fromReasons(
        entry.dto?.intersectionReasons,
        isDark: widget.isDark,
        // N5：圈子文章卡 → 交集句对象片段点击精确归因为圈子内容（非推荐流）。
        referralSource: ReferralSource.circlePost,
      ),
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
                label: '${_entryLikeCount(entry)}',
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
    CircleHubFeedPostEntry entry,
    Color fgSecondary, {
    required VoidCallback onTap,
  }) {
    final recommendationLabel = _entryArticleRecommendationLabel(entry);
    final authorName = _entryAuthorDisplayName(entry);
    return PostPreviewListTile(
      key: ValueKey<String>('circle-article-list-${_entryId(entry)}'),
      isDark: widget.isDark,
      eyebrowText: recommendationLabel.isNotEmpty
          ? recommendationLabel
          : '笔记 · ${_entryArticleTemplateLabel(entry)}',
      eyebrowColor: AppColors.primaryColor,
      title: _entryHeadlineText(entry),
      supportingText: _entrySupportingText(entry),
      supportingTextMaxLines:
          _circleArticleDistributionProfile.summaryLineLimit,
      coverUrl: _entryCoverUrl(entry),
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
            label: '赞 ${_entryLikeCount(entry)}',
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

  bool _rawIsArticle(Map<String, dynamic> item) {
    return (item['contentType'] ?? item['type'] ?? '').toString() == 'article';
  }

  String _rawTitle(Map<String, dynamic> item) {
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
    return _rawTypeLabel(item);
  }

  String _rawHeadlineText(Map<String, dynamic> item) {
    final title = _rawTitle(item);
    if (title.isNotEmpty) {
      return title;
    }
    return _rawTypeLabel(item);
  }

  String _rawSupportingText(Map<String, dynamic> item) {
    final headline = _rawHeadlineText(item);
    final summary = (item['summary'] ?? '').toString().trim();
    if (_rawIsArticle(item) && summary.isNotEmpty && summary != headline) {
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

  Widget _rawArticleTemplateBadge(Map<String, dynamic> item) {
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
        articleTemplatePresetFromString(
          item['articleTemplate']?.toString(),
        ).label,
        style: TextStyle(
          color: AppColors.white,
          fontSize: AppTypography.xs,
          fontWeight: AppTypography.semiBold,
        ),
      ),
    );
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

  String _rawArticleRecommendationLabel(Map<String, dynamic> item) {
    final recommended = _recommendedArticleTemplatesForCircle();
    if (recommended.isEmpty) {
      return '';
    }
    final templateId = (item['articleTemplate'] ?? '').toString().trim();
    if (templateId.isNotEmpty && recommended.contains(templateId)) {
      return '讨论推荐 · ${articleTemplatePresetFromString(templateId).label}';
    }
    final labels = recommended
        .take(2)
        .map((value) => articleTemplatePresetFromString(value).label)
        .join(' / ');
    if (labels.isEmpty) {
      return '';
    }
    return '讨论推荐 · $labels';
  }

  int _rawLikeCount(Map<String, dynamic> item) {
    return (item['likeCount'] as num?)?.toInt() ??
        (item['likes'] as num?)?.toInt() ??
        0;
  }

  bool _rawIsVideo(Map<String, dynamic> item) {
    return (item['type'] ?? '').toString() == 'video' ||
        (item['videoUrl']?.toString().trim() ?? '').isNotEmpty;
  }

  Widget _buildEmpty(Color fgSecondary) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final ultraCompact = constraints.maxHeight < AppSpacing.buttonHeight;
        final compact = !ultraCompact && constraints.maxHeight < 220;
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
                    Flexible(child: text),
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

  Widget _buildErrorCard() {
    return AppSectionErrorCard(
      semantic: _errorSemantic!,
      margin: EdgeInsets.zero,
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry ||
            action.type == UiErrorActionType.resubmit) {
          await _loadFeed();
        }
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
            color: AppColors.black.withValues(
              alpha: widget.isDark ? 0.16 : 0.05,
            ),
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

