import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import 'package:quwoquan_app/cloud/services/behavior/behavior_repository.dart';
import 'package:quwoquan_app/core/providers/feed_session_provider.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_secondary_tab_bar.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/discovery/services/media_viewer_interaction_bridge.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/components/content/intersection_reason_chip.dart';

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
    this.suppressFailure = false,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;
  final bool inlineScroll;
  final GlobalKey? secondaryTabBarKey;
  final GestureDragEndCallback? onSecondaryHorizontalDragEnd;
  final bool suppressFailure;

  @override
  ConsumerState<ProfileWorksTab> createState() => _ProfileWorksTabState();
}

class _ProfileWorksTabState extends ConsumerState<ProfileWorksTab> {
  List<UserProfileSubTabConfig> get _creationFilters =>
      UserProfileUIConfig.creationSubTabs;

  @override
  Widget build(BuildContext context) {
    final notifier = ref.read(profileNotifierProvider(widget.userId).notifier);
    final state = ref.watch(profileNotifierProvider(widget.userId));
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final filtered = state.creations
        .where((post) => _matchesCreationFilter(post, state.activeSubTab))
        .toList(growable: false);
    final isLoading = state.isWorksLoading && state.creations.isEmpty;
    final blockingFailure = state.creations.isEmpty ? state.worksFailure : null;
    final retainedFailure = state.creations.isNotEmpty
        ? state.worksFailure
        : null;
    final failureSemantic = state.worksFailure == null
        ? null
        : runtimeErrorSemantic(
            context,
            error: state.worksFailure!,
            category: UiErrorCategory.sectionLoad,
            scope: UiErrorScope.section,
          );

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
            AppRequestFeedback.section(showSlowHint: state.isWorksSlow)
          else if (blockingFailure != null && !widget.suppressFailure)
            AppSectionErrorState(
              semantic: failureSemantic!,
              onAction: (action) =>
                  _handleFailureAction(context, notifier, action),
            )
          else if (blockingFailure != null)
            const SizedBox.shrink()
          else if (filtered.isEmpty)
            Padding(
              padding: EdgeInsets.symmetric(vertical: AppSpacing.interGroupXl),
              child: _buildEmptyState(
                context,
                title: _emptyStateTitle(state.activeSubTab),
                icon: _emptyStateIcon(state.activeSubTab),
                color: fgSecondary,
              ),
            )
          else
            Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: <Widget>[
                if (retainedFailure != null && !widget.suppressFailure)
                  AppTransientErrorNotice(
                    semantic: failureSemantic!,
                    onAction: (action) =>
                        _handleFailureAction(context, notifier, action),
                  ),
                GestureDetector(
                  key: const ValueKey<String>('profile-works-grid'),
                  behavior: HitTestBehavior.translucent,
                  onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
                  child: Padding(
                    padding: EdgeInsets.fromLTRB(
                      AppSpacing.feedContentHorizontal(context),
                      0,
                      AppSpacing.feedContentHorizontal(context),
                      AppSpacing.interGroupLg,
                    ),
                    child: GridView.builder(
                      shrinkWrap: true,
                      primary: false,
                      padding: EdgeInsets.zero,
                      physics: const NeverScrollableScrollPhysics(),
                      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
                        crossAxisCount: AppSpacing.responsiveGridColumns(
                          context,
                        ),
                        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
                        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
                        mainAxisExtent: _inlineGridMainAxisExtent(context),
                      ),
                      itemCount: filtered.length,
                      itemBuilder: (context, index) {
                        final post = filtered[index];
                        return _WorksPostCard(
                          post: post,
                          isDark: widget.isDark,
                          onTap: () => _onPostTap(context, post),
                          onHorizontalDragEnd:
                              widget.onSecondaryHorizontalDragEnd,
                        );
                      },
                    ),
                  ),
                ),
              ],
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
              ? AppRequestFeedback.section(showSlowHint: state.isWorksSlow)
              : blockingFailure != null && !widget.suppressFailure
              ? AppSectionErrorState(
                  semantic: failureSemantic!,
                  onAction: (action) =>
                      _handleFailureAction(context, notifier, action),
                )
              : blockingFailure != null
              ? const SizedBox.shrink()
              : filtered.isEmpty
              ? Center(
                  child: _buildEmptyState(
                    context,
                    title: _emptyStateTitle(state.activeSubTab),
                    icon: _emptyStateIcon(state.activeSubTab),
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
                        0,
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
                            onHorizontalDragEnd:
                                widget.onSecondaryHorizontalDragEnd,
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

  Future<void> _handleFailureAction(
    BuildContext context,
    ProfileNotifier notifier,
    UiErrorAction action,
  ) async {
    if (action.type == UiErrorActionType.retry ||
        action.type == UiErrorActionType.resubmit) {
      await notifier.reloadWorks();
      return;
    }
    if (action.type == UiErrorActionType.login) {
      await requireLogin(
        ref,
        context,
        AuthGateReason.generic,
        redirect: GoRouterState.of(context).uri.toString(),
        dismissFallback: AppRoutePaths.home,
      );
      return;
    }
    if (action.type == UiErrorActionType.dismiss) {
      if (context.canPop()) {
        context.pop();
      } else {
        context.go(AppRoutePaths.home);
      }
    }
  }

  double _inlineGridMainAxisExtent(BuildContext context) {
    final columns = AppSpacing.responsiveGridColumns(context);
    if (columns <= 1) {
      return AppSpacing.threeHundredTwenty + AppSpacing.twoHundredTwenty;
    }
    return AppSpacing.threeHundredTwenty + AppSpacing.buttonHeight * 2;
  }

  /// 二级过滤（全部/图片/视频/长文）：与互动页同源的横滑二级页签，
  /// 记录总数放到二级页签「下方」。
  Widget _buildCreationFilters(
    ProfileNotifier notifier,
    ProfileState state, {
    required int totalCount,
  }) {
    final selectedFilterId = _creationFilters
        .firstWhere(
          (filter) => _creationSubTabForId(filter.id) == state.activeSubTab,
          orElse: () => _creationFilters.first,
        )
        .id;

    return Column(
      key: const ValueKey<String>('profile-works-secondary-tabs'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: <Widget>[
        ProfileSecondaryTabBar(
          tabs: _creationFilters
              .map(
                (filter) => ProfileSecondaryTabItem(
                  id: filter.id,
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                ),
              )
              .toList(growable: false),
          selectedId: selectedFilterId,
          onSelected: (id) => notifier.setSubTab(_creationSubTabForId(id)),
          isDark: widget.isDark,
          scrollKey: widget.secondaryTabBarKey,
          onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
        ),
        Padding(
          padding: EdgeInsets.fromLTRB(
            AppSpacing.containerMd,
            AppSpacing.zero,
            AppSpacing.containerMd,
            AppSpacing.intraGroupXs,
          ),
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
      ],
    );
  }

  Widget _buildEmptyState(
    BuildContext context, {
    required String title,
    required IconData icon,
    required Color color,
  }) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Container(
          width: AppSpacing.avatarUserMd,
          height: AppSpacing.avatarUserMd,
          decoration: BoxDecoration(
            color: AppColors.iosSecondaryFill(context).withValues(alpha: 0.72),
            shape: BoxShape.circle,
          ),
          child: Icon(icon, size: AppSpacing.iconSmall, color: color),
        ),
        SizedBox(height: AppSpacing.containerSm),
        Text(
          title,
          style: TextStyle(fontSize: AppTypography.iosFootnote, color: color),
        ),
      ],
    );
  }

  CreationSubTab _creationSubTabForId(String id) => creationSubTabFromId(id);

  bool _matchesCreationFilter(ContentPostViewData post, CreationSubTab tab) {
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
            ? ProfileText.profileCreationEmptyImageMine
            : ProfileText.profileCreationEmptyImageOther;
      case CreationSubTab.video:
        return isMine
            ? ProfileText.profileCreationEmptyVideoMine
            : ProfileText.profileCreationEmptyVideoOther;
      case CreationSubTab.article:
        return isMine
            ? ProfileText.profileCreationEmptyTextMine
            : ProfileText.profileCreationEmptyTextOther;
      case CreationSubTab.all:
        return isMine
            ? ProfileText.profileCreationEmptyAllMine
            : ProfileText.profileCreationEmptyAllOther;
    }
  }

  IconData _emptyStateIcon(CreationSubTab filter) {
    switch (filter) {
      case CreationSubTab.image:
        return CupertinoIcons.photo_on_rectangle;
      case CreationSubTab.video:
        return CupertinoIcons.play_rectangle;
      case CreationSubTab.article:
        return CupertinoIcons.doc_text;
      case CreationSubTab.all:
        return CupertinoIcons.square_stack_3d_up;
    }
  }

  Future<void> _onPostTap(
    BuildContext context,
    ContentPostViewData post,
  ) async {
    final state = ref.read(profileNotifierProvider(widget.userId));
    final filtered = state.creations
        .where((p) => _matchesCreationFilter(p, state.activeSubTab))
        .toList(growable: false);

    final initialIndex = filtered
        .indexWhere((p) => p.id == post.id)
        .clamp(0, filtered.length - 1);
    final postViews = filtered.map(ContentSurfaceViewMapper.fromDto).toList();
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

/// 瀑布流卡片：与圈子 post 保持同一结构，
/// 仅底部元信息改为「赞 + 转 + 评」。
class _WorksPostCard extends ConsumerWidget {
  const _WorksPostCard({
    required this.post,
    required this.isDark,
    required this.onTap,
    this.onHorizontalDragEnd,
  });

  final ContentPostViewData post;
  final bool isDark;
  final VoidCallback onTap;
  final GestureDragEndCallback? onHorizontalDragEnd;

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
    return ProfileText.profileTabCreations;
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
      onHorizontalDragEnd: onHorizontalDragEnd,
      header: IntersectionReasonChip.fromReasons(
        post.intersectionReasons,
        isDark: isDark,
        // N5：用户主页作品卡 → 交集句对象片段点击精确归因为作者主页（非推荐流）。
        referralSource: ReferralSource.authorProfile,
        contextObjectName: _headlineText.trim().isNotEmpty
            ? _headlineText.trim()
            : _supportingText.trim(),
        contextObjectTarget: IntersectionTarget(
          objectType: 'post',
          objectId: post.id,
          objectKind: 'content',
          routeId: 'workBrowser',
        ),
      ),
      footer: Row(
        children: [
          Expanded(
            child: Text(
              post.displayName.isNotEmpty
                  ? post.displayName
                  : ProfileText.profileTabCreations,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: metaTextStyle.copyWith(fontWeight: AppTypography.regular),
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
