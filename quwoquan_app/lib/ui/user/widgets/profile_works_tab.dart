import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/user/generated/user_profile_ui_config.g.dart';
import 'package:quwoquan_app/components/navigation/secondary_capsule_tab_bar.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

/// 创作 Tab：统一承载 `全部 / 微趣 / 图片 / 视频 / 文字` 的内容筛选。
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
                mainAxisSpacing: AppSpacing.interGroupSm,
                crossAxisSpacing: AppSpacing.interGroupSm,
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
                        mainAxisSpacing: AppSpacing.interGroupSm,
                        crossAxisSpacing: AppSpacing.interGroupSm,
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
          width: 56,
          height: 56,
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
        return isMine ? '还没有图片作品' : 'Ta 还没有图片作品';
      case CreationSubTab.video:
        return isMine ? '还没有视频作品' : 'Ta 还没有视频作品';
      case CreationSubTab.article:
        return isMine ? '还没有文章作品' : 'Ta 还没有文章作品';
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

/// 瀑布流卡片：与圈子页 _DiscoveryPostCard 一致的结构。
/// 媒体图片（伪随机宽高比） → 标题（max 2行） → 作者头像 + 昵称 + 赞数。
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
    final hash = post.id.hashCode;
    const ratios = [1.0, 4 / 3, 3 / 4, 1 / 1, 9 / 16];
    final ratio = ratios[hash.abs() % ratios.length];
    return ratio.clamp(9.0 / 16.0, 16.0 / 9.0);
  }

  String get _coverUrl {
    final map = post.toMap();
    final urls = map['imageUrls'];
    return (map['coverUrl'] ??
            map['thumbnailUrl'] ??
            (urls is List && urls.isNotEmpty ? urls[0] : null) ??
            '')
        .toString();
  }

  String get _title {
    final map = post.toMap();
    final title = map['title']?.toString();
    final body = map['body']?.toString();
    if (title != null && title.isNotEmpty) return title;
    if (body != null && body.isNotEmpty) {
      return body.length > 40 ? '${body.substring(0, 40)}…' : body;
    }
    return post.identity == 'moment' ? '点滴' : '作品';
  }

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.14);
    final surface = AppColors.iosGroupedSurface(context);
    final gridMetaFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.iosFootnote,
      regular: AppTypography.iosFootnote,
      expanded: AppTypography.iosSubheadline,
    );

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.zero,
      onPressed: onTap,
      child: Container(
        decoration: BoxDecoration(
          color: surface,
          borderRadius: BorderRadius.circular(AppSpacing.radiusTwenty),
          border: Border.all(color: separator, width: AppSpacing.hairline),
          boxShadow: <BoxShadow>[
            BoxShadow(
              color: Colors.black.withValues(alpha: isDark ? 0.16 : 0.04),
              blurRadius: 20,
              offset: const Offset(0, 8),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: <Widget>[
            AspectRatio(
              aspectRatio: _imageAspectRatio,
              child: ClipRRect(
                borderRadius: BorderRadius.vertical(
                  top: Radius.circular(AppSpacing.radiusTwenty),
                ),
                child: Stack(
                  fit: StackFit.expand,
                  children: <Widget>[
                    _coverUrl.isNotEmpty
                        ? CachedNetworkImage(
                            imageUrl: _coverUrl,
                            fit: BoxFit.cover,
                            placeholder: (context, url) => ColoredBox(
                              color: fgSecondary.withValues(alpha: 0.12),
                            ),
                            errorWidget: (context, url, error) => ColoredBox(
                              color: fgSecondary.withValues(alpha: 0.12),
                            ),
                          )
                        : ColoredBox(
                            color: fgSecondary.withValues(alpha: 0.12),
                          ),
                    if (post.type == 'video')
                      Positioned(
                        top: AppSpacing.intraGroupSm,
                        right: AppSpacing.intraGroupSm,
                        child: Container(
                          width: 32,
                          height: 32,
                          decoration: BoxDecoration(
                            color: Colors.black.withValues(alpha: 0.36),
                            shape: BoxShape.circle,
                          ),
                          child: const Icon(
                            CupertinoIcons.play_fill,
                            color: CupertinoColors.white,
                            size: AppSpacing.iconSmall,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ),
            Padding(
              padding: EdgeInsets.fromLTRB(
                AppSpacing.containerSm,
                AppSpacing.containerSm,
                AppSpacing.containerSm,
                AppSpacing.containerSm,
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    _title,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.semiBold,
                      color: fgPrimary,
                      letterSpacing: -0.18,
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  Row(
                    children: <Widget>[
                      CircleAvatar(
                        radius: 14,
                        backgroundImage: post.avatarUrl.isNotEmpty
                            ? NetworkImage(post.avatarUrl)
                            : null,
                        backgroundColor: AppColors.iosFill(context),
                        child: post.avatarUrl.isEmpty
                            ? Icon(
                                CupertinoIcons.person_crop_circle_fill,
                                size: AppSpacing.iconSmall,
                                color: fgSecondary,
                              )
                            : null,
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      Expanded(
                        child: Text(
                          post.displayName,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: gridMetaFontSize,
                            color: fgSecondary,
                          ),
                        ),
                      ),
                      SizedBox(width: AppSpacing.intraGroupXs),
                      Flexible(
                        child: FittedBox(
                          fit: BoxFit.scaleDown,
                          alignment: Alignment.centerRight,
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: <Widget>[
                              Icon(
                                CupertinoIcons.heart,
                                size: AppSpacing.iconSmall,
                                color: fgSecondary,
                              ),
                              SizedBox(width: AppSpacing.xs),
                              Text(
                                '${post.likeCount}',
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(
                                  fontSize: gridMetaFontSize,
                                  color: fgSecondary,
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
          ],
        ),
      ),
    );
  }
}
