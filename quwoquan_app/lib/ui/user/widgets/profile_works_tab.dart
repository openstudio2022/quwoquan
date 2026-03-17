import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/content/generated/content_ui_config.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';

/// 创作 Tab：统一承载 `全部 / 点滴 / 作品`。
class ProfileWorksTab extends ConsumerStatefulWidget {
  const ProfileWorksTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  @override
  ConsumerState<ProfileWorksTab> createState() => _ProfileWorksTabState();
}

class _ProfileWorksTabState extends ConsumerState<ProfileWorksTab> {
  List<IdentityFilterConfig> get _identityFilters =>
      ContentUIConfig.creationIdentityFilters;

  List<WorkFormatFilterConfig> get _workFormatFilters =>
      ContentUIConfig.workFormatFilters;

  @override
  Widget build(BuildContext context) {
    final notifier = ref.read(profileNotifierProvider(widget.userId));
    final state = ref.watch(profileNotifierProvider(widget.userId)).state;
    final fg = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final filtered = state.creations
        .where(
          (post) =>
              _matchesIdentityFilter(post, state.activeSubTab) &&
              _matchesWorkFormat(
                post,
                state.activeSubTab,
                state.activeWorkFormat,
              ),
        )
        .toList(growable: false);

    return Column(
      children: [
        _buildIdentityFilters(notifier, state, fg, fgSecondary),
        if (state.activeSubTab == CreationSubTab.work) ...[
          SizedBox(height: AppSpacing.sm),
          _buildWorkFormatFilters(notifier, state, fg, fgSecondary),
        ],
        Expanded(
          child: filtered.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        CupertinoIcons.photo_on_rectangle,
                        size: AppSpacing.xl * 2,
                        color: fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.md),
                      Text(
                        _emptyStateTitle(
                          state.activeSubTab,
                          state.activeWorkFormat,
                        ),
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          color: fgSecondary,
                        ),
                      ),
                    ],
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

  Widget _buildIdentityFilters(
    ProfileNotifier notifier,
    ProfileState state,
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
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: _FilterChipButton(
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                  selected: state.activeSubTab == tab,
                  foregroundColor: fg,
                  secondaryColor: fgSecondary,
                  onPressed: () => notifier.setSubTab(tab),
                ),
              );
            })
            .toList(growable: false),
      ),
    );
  }

  Widget _buildWorkFormatFilters(
    ProfileNotifier notifier,
    ProfileState state,
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
              return Padding(
                padding: EdgeInsets.only(right: AppSpacing.sm),
                child: _FilterChipButton(
                  label: UITextConstants.contentLabelForKey(filter.labelKey),
                  selected: state.activeWorkFormat == format,
                  foregroundColor: fg,
                  secondaryColor: fgSecondary,
                  onPressed: () => notifier.setWorkFormat(format),
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

  bool _matchesIdentityFilter(PostBaseDto post, CreationSubTab tab) {
    switch (tab) {
      case CreationSubTab.moment:
        return post.identity == 'moment';
      case CreationSubTab.work:
        return post.identity == 'work';
      case CreationSubTab.all:
        return true;
    }
  }

  bool _matchesWorkFormat(
    PostBaseDto post,
    CreationSubTab activeSubTab,
    CreationWorkFormat format,
  ) {
    if (activeSubTab != CreationSubTab.work ||
        format == CreationWorkFormat.all) {
      return true;
    }
    switch (format) {
      case CreationWorkFormat.image:
        return post.displayFormat == 'image';
      case CreationWorkFormat.video:
        return post.displayFormat == 'video';
      case CreationWorkFormat.note:
        return post.displayFormat == 'note';
      case CreationWorkFormat.all:
        return true;
    }
  }

  String _emptyStateTitle(
    CreationSubTab filter,
    CreationWorkFormat activeWorkFormat,
  ) {
    final isMine = widget.mode == ProfileMode.mine;
    switch (filter) {
      case CreationSubTab.moment:
        return isMine ? '还没有点滴' : 'Ta 还没有点滴';
      case CreationSubTab.work:
        switch (activeWorkFormat) {
          case CreationWorkFormat.image:
            return isMine ? '还没有图片作品' : 'Ta 还没有图片作品';
          case CreationWorkFormat.video:
            return isMine ? '还没有视频作品' : 'Ta 还没有视频作品';
          case CreationWorkFormat.note:
            return isMine ? '还没有笔记作品' : 'Ta 还没有笔记作品';
          case CreationWorkFormat.all:
            return isMine ? '还没有作品' : 'Ta 还没有作品';
        }
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
        .where(
          (p) =>
              _matchesIdentityFilter(p, state.activeSubTab) &&
              _matchesWorkFormat(
                p,
                state.activeSubTab,
                state.activeWorkFormat,
              ),
        )
        .toList(growable: false);
        
    final initialIndex = filtered.indexWhere((p) => p.id == post.id).clamp(0, filtered.length - 1);
    final postViews = filtered.map(PostSummaryView.fromDto).toList();
    final isMoment = post.identity == 'moment';

    if (post.displayFormat == 'video') {
      context.push(
        '/video-viewer/$initialIndex',
        extra: MediaViewerExtra(
          posts: postViews,
          initialIndex: initialIndex,
          category: isMoment ? 'profile_moment' : 'profile',
        ),
      );
      return;
    }
    
    context.push(
      '/media-viewer/photo/$initialIndex',
      extra: MediaViewerExtra(
        posts: postViews,
        initialIndex: initialIndex,
        category: isMoment ? 'profile_moment' : 'profile',
        initialImageIndex: 0,
      ),
    );
  }
}

class _FilterChipButton extends StatelessWidget {
  const _FilterChipButton({
    required this.label,
    required this.selected,
    required this.foregroundColor,
    required this.secondaryColor,
    required this.onPressed,
  });

  final String label;
  final bool selected;
  final Color foregroundColor;
  final Color secondaryColor;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerSm,
        vertical: AppSpacing.intraGroupSm,
      ),
      minimumSize: Size.zero,
      borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
      color: selected ? AppColors.primaryColor.withValues(alpha: 0.12) : null,
      onPressed: onPressed,
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border.all(
            color: selected
                ? AppColors.primaryColor.withValues(alpha: 0.45)
                : secondaryColor.withValues(alpha: 0.2),
          ),
          borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        ),
        child: Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.intraGroupSm,
          ),
          child: Text(
            label,
            style: TextStyle(
              color: selected ? foregroundColor : secondaryColor,
              fontWeight: AppTypography.semiBold,
              fontSize: AppTypography.sm,
            ),
          ),
        ),
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
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final gridMetaFontSize = AppTypography.responsive(
      context,
      compact: AppTypography.sm,
      regular: AppTypography.base,
      expanded: AppTypography.base,
    );

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            AspectRatio(
              aspectRatio: _imageAspectRatio,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
                child: Stack(
                  fit: StackFit.expand,
                  children: [
                    _coverUrl.isNotEmpty
                        ? CachedNetworkImage(
                            imageUrl: _coverUrl,
                            fit: BoxFit.cover,
                            placeholder: (_, __) => Container(
                              color: fgSecondary.withValues(alpha: 0.15),
                            ),
                            errorWidget: (_, __, ___) => Container(
                              color: fgSecondary.withValues(alpha: 0.15),
                            ),
                          )
                        : Container(color: fgSecondary.withValues(alpha: 0.15)),
                    if (post.type == 'video')
                      Positioned(
                        top: AppSpacing.intraGroupSm,
                        right: AppSpacing.intraGroupSm,
                        child: Icon(
                          Icons.play_circle_fill,
                          color: Colors.white,
                          size: AppSpacing.iconLarge - AppSpacing.xs,
                        ),
                      ),
                  ],
                ),
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupSm),
            Text(
              _title,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(fontSize: gridMetaFontSize, color: fgPrimary),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Row(
              children: [
                CircleAvatar(
                  radius: AppSpacing.intraGroupMd,
                  backgroundImage: post.avatarUrl.isNotEmpty
                      ? NetworkImage(post.avatarUrl)
                      : null,
                  backgroundColor: fgSecondary.withValues(alpha: 0.2),
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
                Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.heart,
                      size: gridMetaFontSize,
                      color: fgSecondary,
                    ),
                    Text(
                      ' ${post.likeCount}',
                      style: TextStyle(
                        fontSize: gridMetaFontSize,
                        color: fgSecondary,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
