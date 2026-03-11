import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/models/profile_tab.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

/// 作品 Tab：二级 SubTab 筛选 + 圈子页同款两列瀑布流不等高布局。
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

class _ProfileWorksTabState extends ConsumerState<ProfileWorksTab>
    with SingleTickerProviderStateMixin {
  late TabController _subTabController;

  static const _subTabs = [
    CreationSubTab.all,
    CreationSubTab.image,
    CreationSubTab.video,
    CreationSubTab.article,
  ];

  static const _subTabLabels = {
    CreationSubTab.all: '全部',
    CreationSubTab.image: '图片',
    CreationSubTab.video: '视频',
    CreationSubTab.article: '文章',
  };

  static const _subTabTypeMap = {
    CreationSubTab.image: 'photo',
    CreationSubTab.video: 'video',
    CreationSubTab.article: 'article',
  };

  @override
  void initState() {
    super.initState();
    _subTabController = TabController(length: _subTabs.length, vsync: this);
    _subTabController.addListener(_onSubTabChanged);
  }

  @override
  void dispose() {
    _subTabController.removeListener(_onSubTabChanged);
    _subTabController.dispose();
    super.dispose();
  }

  void _onSubTabChanged() {
    if (_subTabController.indexIsChanging) return;
    final notifier = ref.read(profileNotifierProvider(widget.userId));
    notifier.setSubTab(_subTabs[_subTabController.index]);
  }

  @override
  Widget build(BuildContext context) {
    final state = ref.watch(profileNotifierProvider(widget.userId)).state;
    final fg =
        AppColorsFunctional.getColor(widget.isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(
      widget.isDark,
      ColorType.foregroundSecondary,
    );
    final primary = AppColors.primaryColor;

    final works = state.creations
        .where((p) => p.type != 'moment')
        .toList(growable: false);

    final activeSubTab = state.activeSubTab;
    final filtered = works.where((p) {
      if (activeSubTab == CreationSubTab.all) return true;
      final mapped = _subTabTypeMap[activeSubTab];
      return p.type == mapped;
    }).toList(growable: false);

    return Column(
      children: [
        Container(
          color: AppColorsFunctional.getColor(
            widget.isDark,
            ColorType.backgroundPrimary,
          ),
          child: TabBar(
            controller: _subTabController,
            labelColor: fg,
            unselectedLabelColor: fgSecondary,
            labelStyle: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.semiBold,
            ),
            unselectedLabelStyle: TextStyle(
              fontSize: AppTypography.base,
              fontWeight: AppTypography.normal,
            ),
            indicatorColor: primary,
            indicatorSize: TabBarIndicatorSize.label,
            tabs: _subTabs
                .map((t) => Tab(child: Text(_subTabLabels[t] ?? '')))
                .toList(),
          ),
        ),
        Expanded(
          child: filtered.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.photo_library_outlined,
                        size: AppSpacing.xl * 2,
                        color: fgSecondary,
                      ),
                      SizedBox(height: AppSpacing.md),
                      Text(
                        widget.mode == ProfileMode.mine
                            ? '还没有作品'
                            : 'Ta 还没有作品',
                        style: TextStyle(
                          fontSize: AppTypography.md,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                )
              : CustomScrollView(
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

  void _onPostTap(BuildContext context, PostBaseDto post) {
    context.push(AppRoutePaths.articleDetail(id: post.id));
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
    return '作品';
  }

  @override
  Widget build(BuildContext context) {
    final fgPrimary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
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
                        : Container(
                            color: fgSecondary.withValues(alpha: 0.15),
                          ),
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
              style: TextStyle(
                fontSize: gridMetaFontSize,
                color: fgPrimary,
              ),
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
