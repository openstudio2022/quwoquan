import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// 创作 Tab：统一承载 `全部 / 图片 / 视频 / 文字` 的内容筛选。
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
  List<UserProfileSubTabConfig> get _creationFilters =>
      UserProfileUIConfig.creationSubTabs;

  @override
  Widget build(BuildContext context) {
    final notifier = ref.read(profileNotifierProvider(widget.userId));
    final state = ref.watch(profileNotifierProvider(widget.userId)).state;
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final filtered = state.creations
        .where((post) => _matchesCreationFilter(post, state.activeSubTab))
        .toList(growable: false);
    final isLoading = state.isLoading && state.creations.isEmpty;

    if (widget.inlineScroll) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _buildCreationFilters(notifier, state),
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
                AppSpacing.intraGroupSm,
                AppSpacing.feedContentHorizontal(context),
                AppSpacing.interGroupLg,
              ),
              child: MasonryGridView.count(
                crossAxisCount: 2,
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
        _buildCreationFilters(notifier, state),
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
                        AppSpacing.containerMd,
                        AppSpacing.feedContentHorizontal(context),
                        AppSpacing.interGroupLg,
                      ),
                      sliver: SliverMasonryGrid.count(
                        crossAxisCount: 2,
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

  Widget _buildCreationFilters(ProfileNotifier notifier, ProfileState state) {
    final activeIndex = _creationFilters.indexWhere(
      (filter) => _creationSubTabForId(filter.id) == state.activeSubTab,
    );
    return SizedBox(
      key: const ValueKey<String>('profile-works-secondary-tabs'),
      child: SecondaryCapsuleTabBar(
        key: widget.secondaryTabBarKey,
        isDark: widget.isDark,
        tabs: _creationFilters
            .map(
              (filter) => UITextConstants.contentLabelForKey(filter.labelKey),
            )
            .toList(growable: false),
        activeIndex: activeIndex < 0 ? 0 : activeIndex,
        onTap: (index) => notifier.setSubTab(
          _creationSubTabForId(_creationFilters[index].id),
        ),
        variant: SecondaryCapsuleTabBarVariant.iosProfile,
        onHorizontalDragEnd: widget.onSecondaryHorizontalDragEnd,
      ),
    );
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

  CreationSubTab _creationSubTabForId(String id) {
    switch (id) {
      case 'micro':
        return CreationSubTab.micro;
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

  bool _matchesCreationFilter(PostBaseDto post, CreationSubTab tab) {
    switch (tab) {
      case CreationSubTab.moment:
      case CreationSubTab.micro:
        return post.identity == 'moment';
      case CreationSubTab.work:
        return post.identity == 'work';
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
      case CreationSubTab.moment:
      case CreationSubTab.micro:
        return isMine ? '还没有点滴' : 'Ta 还没有点滴';
      case CreationSubTab.work:
        return isMine ? '还没有作品' : 'Ta 还没有作品';
      case CreationSubTab.image:
        return isMine ? '还没有图片内容' : 'Ta 还没有图片内容';
      case CreationSubTab.video:
        return isMine ? '还没有视频内容' : 'Ta 还没有视频内容';
      case CreationSubTab.article:
        return isMine ? '还没有文字内容' : 'Ta 还没有文字内容';
      case CreationSubTab.all:
        return isMine ? '还没有创作内容' : 'Ta 还没有创作内容';
    }
  }

  void _onPostTap(BuildContext context, PostBaseDto post) {
    if (post.identity == 'work' && post.displayFormat == 'note') {
      context.push(AppRoutePaths.articleDetail(id: post.id));
      return;
    }

    final state = ref.read(profileNotifierProvider(widget.userId)).state;
    final filtered = state.creations
        .where((p) => _matchesCreationFilter(p, state.activeSubTab))
        .toList(growable: false);

    final initialIndex = filtered
        .indexWhere((p) => p.id == post.id)
        .clamp(0, filtered.length - 1);
    final postViews = filtered.map(PostSummaryView.fromDto).toList();
    final isMoment = post.identity == 'moment';

    if (post.displayFormat == 'video') {
      context.push(
        '/video-viewer/$initialIndex',
        extra: MediaViewerExtra(
          posts: postViews,
          dtoPosts: filtered,
          initialIndex: initialIndex,
          category: isMoment ? 'profile_moment' : 'profile',
          source: isMoment ? 'profile_moment' : 'profile',
        ),
      );
      return;
    }

    context.push(
      '/media-viewer/photo/$initialIndex',
      extra: MediaViewerExtra(
        posts: postViews,
        dtoPosts: filtered,
        initialIndex: initialIndex,
        category: isMoment ? 'profile_moment' : 'profile',
        initialImageIndex: 0,
        source: isMoment ? 'profile_moment' : 'profile',
      ),
    );
  }
}

/// 瀑布流卡片：与圈子 post 保持同一结构，
/// 仅底部元信息改为「赞 + 转 + 评」。
class _WorksPostCard extends StatelessWidget {
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
    return post.identity == 'moment' ? '点滴' : '作品';
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
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
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
      footer: Row(
        children: [
          Expanded(
            child: Align(
              alignment: Alignment.centerLeft,
              child: PostCardMetric(
                icon: CupertinoIcons.heart,
                label: '${post.likeCount}',
                color: fgSecondary,
                textStyle: metaTextStyle,
              ),
            ),
          ),
          Expanded(
            child: Align(
              alignment: Alignment.center,
              child: PostCardMetric(
                icon: CupertinoIcons.arrowshape_turn_up_right,
                label: '${post.shareCount}',
                color: fgSecondary,
                textStyle: metaTextStyle,
              ),
            ),
          ),
          Expanded(
            child: Align(
              alignment: Alignment.centerRight,
              child: PostCardMetric(
                icon: CupertinoIcons.chat_bubble,
                label: '${post.commentCount}',
                color: fgSecondary,
                textStyle: metaTextStyle,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
