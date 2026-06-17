import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/content/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/widgets/intersection_reason_chip.dart';

/// 记录 Tab：统一承载 `全部 / 图片 / 视频 / 长文` 的内容筛选。
class ProfileWorksTab extends ConsumerStatefulWidget {
  const ProfileWorksTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
    this.inlineScroll = false,
    this.secondaryTabBarKey,
    this.onSecondaryHorizontalDragEnd,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;

  @override
  ConsumerState<ProfileWorksTab> createState() => _ProfileWorksTabState();
}

class _ProfileWorksTabState extends ConsumerState<ProfileWorksTab> {
  final LayerLink _filterLayerLink = LayerLink();
  OverlayEntry? _filterOverlay;

  List<UserProfileSubTabConfig> get _creationFilters =>
      UserProfileUIConfig.creationSubTabs;

  @override
  void dispose() {
    _hideCreationFilterMenu();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final filtered = state.creations
        .where((post) => _matchesCreationFilter(post, state.activeSubTab))
        .toList(growable: false);
    final isLoading = state.isLoading && state.creations.isEmpty;

    if (widget.inlineScroll) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildCreationFilters(
            notifier,
            state,
            totalCount: state.creations.length,
          ),
          if (isLoading)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
              child: Center(child: CupertinoActivityIndicator()),
            )
          else if (filtered.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
              child: _buildEmptyState(
                context,
                title: _emptyStateTitle(state.activeSubTab),
                color: fgSecondary,
              ),
            )
          else
            Padding(
              key: const ValueKey<String>('profile-works-grid'),
              padding: EdgeInsets.fromLTRB(
                AppSpacing.feedContentHorizontal(context),
                AppSpacing.intraGroupXs,
                AppSpacing.feedContentHorizontal(context),
                AppSpacing.interGroupLg,
              ),
              child: MasonryGridView.count(
                crossAxisCount: AppSpacing.responsiveGridColumns(context),
                mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                itemCount: filtered.length,
                shrinkWrap: true,
                primary: false,
                padding: EdgeInsets.zero,
                physics: const NeverScrollableScrollPhysics(),
                itemBuilder: (context, index) {
                  final post = filtered[index];
                  return _WorksPostCard(
                    post: post,
                    isDark: widget.isDark,
                    onTap: () => _onPostTap(context, post),
                  );
                },
              ),
            ),
        ],
      );
    }

    return Column(
      children: [
        _buildCreationFilters(
          notifier,
          state,
          totalCount: state.creations.length,
        ),
        Expanded(
          child: isLoading
              ? Center(child: CupertinoActivityIndicator())
              : filtered.isEmpty
              ? Center(
                  child: _buildEmptyState(
                    context,
                    title: _emptyStateTitle(state.activeSubTab),
                    color: fgSecondary,
                  ),
                )
              : CustomScrollView(
                  physics: const BouncingScrollPhysics(
                    parent: AlwaysScrollableScrollPhysics(),
                  ),
                  slivers: [
                    SliverPadding(
                      padding: EdgeInsets.fromLTRB(
                        AppSpacing.feedContentHorizontal(context),
                        AppSpacing.intraGroupXs,
                        AppSpacing.feedContentHorizontal(context),
                        AppSpacing.interGroupLg,
                      ),
                      sliver: SliverMasonryGrid.count(
                        crossAxisCount: AppSpacing.responsiveGridColumns(
                          context,
                        ),
                        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                        childCount: filtered.length,
                        itemBuilder: (context, index) {
                          final post = filtered[index];
                          return _WorksPostCard(
                            post: post,
                            isDark: widget.isDark,
                            onTap: () => _onPostTap(context, post),
                          );
                        },
                      ),
                    ),
                  ],
                ),
        ),
      ],
    );
  }

  static const Key creationFilterButtonKey = ValueKey<String>(
    'profile-works-filter-button',
  );

  /// 二级过滤（全部/图片/视频/长文）：左侧记录总数，右侧收敛为单一图标入口，
  /// 点击后在入口下方展示菜单；横滑切换语义保留。
  Widget _buildCreationFilters(
    ProfileNotifier notifier,
    ProfileState state, {
    required int totalCount,
  }) {
    final accent = AppColors.iosAccent(context);
    return Padding(
      key: const ValueKey<String>('profile-works-secondary-tabs'),
      padding: EdgeInsets.fromLTRB(
        AppSpacing.feedContentHorizontal(context),
        0,
        AppSpacing.feedContentHorizontal(context),
        0,
      ),
      child: GestureDetector(
        key: widget.secondaryTabBarKey,
        behavior: HitTestBehavior.opaque,
        onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
        child: Row(
          children: <Widget>[
            Expanded(
              child: Text(
                UITextConstants.profileRecordsTotal(totalCount),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosSecondaryLabel(context),
                  letterSpacing: -0.04,
                ),
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            CompositedTransformTarget(
              link: _filterLayerLink,
              child: Semantics(
                button: true,
                label: UITextConstants.profileWorksFilterTitle,
                child: CupertinoButton(
                  key: creationFilterButtonKey,
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.containerXs,
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  minimumSize: Size.square(AppSpacing.minInteractiveSize),
                  onPressed: () => _toggleCreationFilterMenu(notifier, state),
                  child: Icon(
                    CupertinoIcons.line_horizontal_3_decrease,
                    size: AppSpacing.iconSmall,
                    color: state.activeSubTab == CreationSubTab.all
                        ? AppColors.iosSecondaryLabel(context)
                        : accent,
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _toggleCreationFilterMenu(ProfileNotifier notifier, ProfileState state) {
    if (_filterOverlay != null) {
      _hideCreationFilterMenu();
      return;
    }
    final overlay = Overlay.of(context);
    _filterOverlay = OverlayEntry(
      builder: (overlayContext) => Stack(
        children: <Widget>[
          Positioned.fill(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onTap: _hideCreationFilterMenu,
              child: const SizedBox.expand(),
            ),
          ),
          CompositedTransformFollower(
            link: _filterLayerLink,
            showWhenUnlinked: false,
            targetAnchor: Alignment.bottomRight,
            followerAnchor: Alignment.topRight,
            offset: Offset(0, AppSpacing.intraGroupXs),
            child: _CreationFilterMenu(
              filters: _creationFilters,
              activeSubTab: state.activeSubTab,
              onSelected: (selected) {
                _hideCreationFilterMenu();
                if (selected != state.activeSubTab) {
                  notifier.setSubTab(selected);
                }
              },
              resolveSubTab: _creationSubTabForId,
            ),
          ),
        ],
      ),
    );
    overlay.insert(_filterOverlay!);
  }

  void _hideCreationFilterMenu() {
    _filterOverlay?.remove();
    _filterOverlay = null;
  }

  Widget _buildEmptyState(
    BuildContext context, {
    required String title,
    required Color color,
  }) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Container(
          width: AppSpacing.avatarUserLg,
          height: AppSpacing.avatarUserLg,
          decoration: BoxDecoration(
            color: AppColors.iosFill(context),
            shape: BoxShape.circle,
          ),
          child: Icon(
            CupertinoIcons.photo_on_rectangle,
            size: AppSpacing.iconMedium,
            color: color,
          ),
        ),
        SizedBox(height: AppSpacing.containerSm),
        Text(
          title,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            color: color,
          ),
        ),
      ],
    );
  }

  CreationSubTab _creationSubTabForId(String id) => creationSubTabFromId(id);

  bool _matchesCreationFilter(PostBaseDto post, CreationSubTab tab) {
    switch (tab) {
      case CreationSubTab.image:
        return post.displayFormat == 'image';
      case CreationSubTab.video:
        return post.displayFormat == 'video';
      case CreationSubTab.article:
        return post.displayFormat == 'note';
      case CreationSubTab.all:
        return true;
    }
  }

  String _emptyStateTitle(CreationSubTab filter) {
    final isMine = widget.mode == ProfileMode.mine;
    switch (filter) {
      case CreationSubTab.image:
        return isMine
            ? UITextConstants.profileCreationEmptyImageMine
            : UITextConstants.profileCreationEmptyImageOther;
      case CreationSubTab.video:
        return isMine
            ? UITextConstants.profileCreationEmptyVideoMine
            : UITextConstants.profileCreationEmptyVideoOther;
      case CreationSubTab.article:
        return isMine
            ? UITextConstants.profileCreationEmptyTextMine
            : UITextConstants.profileCreationEmptyTextOther;
      case CreationSubTab.all:
        return isMine
            ? UITextConstants.profileCreationEmptyAllMine
            : UITextConstants.profileCreationEmptyAllOther;
    }
  }

  Future<void> _onPostTap(BuildContext context, PostBaseDto post) async {
    final state = ref.read(profileNotifierProvider(widget.userId));
    final filtered = state.creations
        .where((p) => _matchesCreationFilter(p, state.activeSubTab))
        .toList(growable: false);

    final initialIndex = filtered
        .indexWhere((p) => p.id == post.id)
        .clamp(0, filtered.length - 1);
    final postViews = filtered
        .map((dto) => ContentSurfaceViewMapper.fromDto(dto, wire: dto.toMap()))
        .toList();
    final isMoment = post.identity == 'moment';
    final interactionSnapshot = buildMediaViewerInteractionSnapshot(
      posts: filtered,
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
        workId: post.id,
        filter: post.isVideoLike
            ? 'video'
            : (post.isArticleLike ? 'article' : 'image'),
        source: isMoment ? 'profile_moment' : 'profile',
        index: '$initialIndex',
      ),
      extra: MediaViewerExtra(
        posts: postViews,
        dtoPosts: filtered,
        initialIndex: initialIndex,
        category: isMoment ? 'profile_moment' : 'profile',
        initialImageIndex: 0,
        source: isMoment ? 'profile_moment' : 'profile',
        interactionSnapshot: interactionSnapshot,
        referralSource: ReferralSource.authorProfile,
        feedRequestId: navFeedRequestId,
      ),
    );
    if (result is MediaViewerResult) {
      applyMediaViewerResultToInteractionState(ref, result);
    }
  }
}

class _CreationFilterMenu extends StatelessWidget {
  const _CreationFilterMenu({
    required this.filters,
    required this.activeSubTab,
    required this.onSelected,
    required this.resolveSubTab,
  });

  final List<UserProfileSubTabConfig> filters;
  final CreationSubTab activeSubTab;
  final ValueChanged<CreationSubTab> onSelected;
  final CreationSubTab Function(String id) resolveSubTab;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = isDark
        ? AppColors.iosSystemSurfaceDark
        : AppColors.white.withValues(alpha: 0.98);
    final primary = AppColors.iosAccent(context);
    final foreground = AppColors.iosLabel(context);
    final secondary = AppColors.iosSecondaryLabel(context);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
        boxShadow: <BoxShadow>[
          BoxShadow(
            color: AppColors.black.withValues(alpha: isDark ? 0.32 : 0.12),
            blurRadius: AppSpacing.containerMd,
            offset: Offset(0, AppSpacing.intraGroupXs),
          ),
        ],
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: <Widget>[
            for (final filter in filters)
              _CreationFilterMenuItem(
                key: ValueKey<String>(
                  'profile-works-filter-option-${filter.id}',
                ),
                icon: _iconForFilter(filter.id),
                label: UITextConstants.contentLabelForKey(filter.labelKey),
                selected: resolveSubTab(filter.id) == activeSubTab,
                primary: primary,
                foreground: foreground,
                secondary: secondary,
                onTap: () => onSelected(resolveSubTab(filter.id)),
              ),
          ],
        ),
      ),
    );
  }

  IconData _iconForFilter(String id) {
    switch (id) {
      case 'video':
        return CupertinoIcons.video_camera;
      case 'image':
        return CupertinoIcons.photo;
      case 'article':
        return CupertinoIcons.doc_text;
      case 'all':
      default:
        return CupertinoIcons.square_grid_2x2;
    }
  }
}

class _CreationFilterMenuItem extends StatelessWidget {
  const _CreationFilterMenuItem({
    super.key,
    required this.icon,
    required this.label,
    required this.selected,
    required this.primary,
    required this.foreground,
    required this.secondary,
    required this.onTap,
  });

  final IconData icon;
  final String label;
  final bool selected;
  final Color primary;
  final Color foreground;
  final Color secondary;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final itemColor = selected ? primary : foreground;
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupXs,
      ),
      minimumSize: const Size(
        AppSpacing.minInteractiveSize * 3,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onTap,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(icon, size: AppSpacing.iconSmall, color: itemColor),
          SizedBox(width: AppSpacing.intraGroupSm),
          SizedBox(
            width: AppSpacing.minInteractiveSize,
            child: Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: selected
                    ? AppTypography.semiBold
                    : AppTypography.medium,
                color: itemColor,
                letterSpacing: -0.08,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupMd),
          Icon(
            CupertinoIcons.check_mark,
            size: AppSpacing.iconXSmall,
            color: selected ? primary : secondary.withValues(alpha: 0),
          ),
        ],
      ),
    );
  }
}

/// 瀑布流卡片：与圈子 post 保持同一结构，
/// 仅底部元信息改为「赞 + 转 + 评」。
class _WorksPostCard extends ConsumerWidget {
  const _WorksPostCard({
    required this.post,
    required this.isDark,
    required this.onTap,
  });

  final PostBaseDto post;
  final bool isDark;
  final VoidCallback onTap;

  double get _imageAspectRatio {
    final ratio = post.aspectRatio;
    if (ratio != null && ratio > 0) {
      return ratio.clamp(9.0 / 16.0, 16.0 / 9.0);
    }
    if (post.isVideoLike) {
      return 9 / 16;
    }
    if (post.hasVisualMedia) {
      return 3 / 4;
    }
    return 1.0;
  }

  String get _coverUrl {
    return post.primaryVisualUrl;
  }

  String get _headlineText {
    final title = post.normalizedTitle;
    final body = post.normalizedBody;
    if (title.isNotEmpty) return title;
    if (body.isNotEmpty) return body;
    return UITextConstants.profileTabCreations;
  }

  String get _supportingText {
    final title = post.normalizedTitle;
    final body = post.normalizedBody;
    if (title.isEmpty || body.isEmpty || title == body) {
      return '';
    }
    return body;
  }

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    ref.watch(postInteractionStateProvider);
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final likeCount = effectivePostLikeCount(
      ref,
      post.id,
      fallback: post.likeCount,
    );
    final metaTextStyle = TextStyle(
      fontSize: AppTypography.iosCaption1,
      color: fgSecondary,
    );
    return PostPreviewCard(
      isDark: isDark,
      title: _headlineText,
      supportingText: _supportingText,
      coverUrl: _coverUrl,
      mediaAspectRatio: _imageAspectRatio,
      showVideoBadge: post.isVideoLike,
      onTap: onTap,
      header: IntersectionReasonChip.fromReasons(
        post.intersectionReasons,
        isDark: isDark,
      ),
      footer: Row(
        children: [
          Expanded(
            child: Text(
              post.displayName.isNotEmpty
                  ? post.displayName
                  : UITextConstants.profileTabCreations,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: metaTextStyle.copyWith(fontWeight: AppTypography.medium),
            ),
          ),
          SizedBox(width: AppSpacing.intraGroupSm),
          PostCardMetric(
            icon: CupertinoIcons.heart,
            label: '$likeCount',
            color: fgSecondary,
            textStyle: metaTextStyle,
          ),
        ],
      ),
    );
  }
}
