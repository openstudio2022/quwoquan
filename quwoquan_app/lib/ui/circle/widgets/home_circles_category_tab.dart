import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';

class HomeCirclesCategoryTab extends ConsumerWidget {
  final String categoryId;
  final String label;
  final List<String> subCategories;
  final List<Map<String, dynamic>> posts;
  final void Function(
    Map<String, dynamic> tapped,
    List<Map<String, dynamic>> sourceItems,
  )
  onPostTap;

  const HomeCirclesCategoryTab({
    super.key,
    required this.categoryId,
    required this.label,
    required this.subCategories,
    required this.posts,
    required this.onPostTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(effectiveIsDarkProvider);
    final cardBg = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
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
      ColorType.separatorSubtle,
    );

    if (posts.isEmpty) {
      return SliverToBoxAdapter(
        child: Padding(
          padding: const EdgeInsets.all(AppSpacing.containerMd),
          child: Container(
            padding: const EdgeInsets.all(AppSpacing.containerMd),
            decoration: BoxDecoration(
              color: cardBg,
              borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
            ),
            child: Text(
              '$label ${UITextConstants.noData}',
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: fgSecondary,
              ),
            ),
          ),
        ),
      );
    }

    return SliverPadding(
      padding: const EdgeInsets.all(AppSpacing.containerMd),
      sliver: SliverMasonryGrid.count(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.intraGroupMd,
        crossAxisSpacing: AppSpacing.intraGroupMd,
        childCount: posts.length,
        itemBuilder: (context, index) {
          final post = posts[index];
          final coverUrl = _coverUrlFor(post);
          final title = _titleFor(post);
          final body = _bodyFor(post);
          final authorName = _authorNameFor(post);
          final avatarUrl = _avatarUrlFor(post);
          final likeCount = _likeCountFor(post);
          final isLiked = (post['isLiked'] as bool?) ?? false;
          final aspectRatio = _coverAspectRatioFor(post);

          return CupertinoButton(
            key: ValueKey(
              'home-circle-grid-post-${post['postId'] ?? post['id']}',
            ),
            padding: EdgeInsets.zero,
            minimumSize: Size.zero,
            onPressed: () => onPostTap(post, posts),
            child: Container(
              decoration: BoxDecoration(
                color: cardBg,
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (coverUrl.isNotEmpty)
                    ClipRRect(
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(AppSpacing.borderRadius),
                      ),
                      child: AspectRatio(
                        aspectRatio: aspectRatio,
                        child: AppCachedNetworkImage(
                          imageUrl: coverUrl,
                          fit: BoxFit.cover,
                        ),
                      ),
                    ),
                  Padding(
                    padding: const EdgeInsets.all(AppSpacing.sm),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if (title.isNotEmpty)
                          Text(
                            title,
                            style: TextStyle(
                              fontSize: AppTypography.iosSubheadline,
                              fontWeight: AppTypography.semiBold,
                              color: fgPrimary,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        if (title.isNotEmpty && body.isNotEmpty)
                          const SizedBox(height: AppSpacing.intraGroupXs),
                        if (body.isNotEmpty)
                          Text(
                            body,
                            style: TextStyle(
                              fontSize: AppTypography.iosCaption1,
                              color: fgSecondary,
                              height: AppTypography.lineHeightRelaxed,
                            ),
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                        const SizedBox(height: AppSpacing.xs),
                        Row(
                          children: [
                            _AvatarBubble(
                              avatarUrl: avatarUrl,
                              fallbackColor: fgSecondary.withValues(alpha: 0.2),
                            ),
                            const SizedBox(width: AppSpacing.xs),
                            Expanded(
                              child: Text(
                                authorName,
                                style: TextStyle(
                                  fontSize: AppTypography.iosCaption1,
                                  color: fgSecondary,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                            Icon(
                              isLiked
                                  ? CupertinoIcons.heart_fill
                                  : CupertinoIcons.heart,
                              size: AppSpacing.iconSmall,
                              color: isLiked
                                  ? AppColors.worksLike
                                  : fgSecondary,
                            ),
                            const SizedBox(width: AppSpacing.intraGroupXs / 2),
                            Text(
                              '$likeCount',
                              style: TextStyle(
                                fontSize: AppTypography.iosCaption1,
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
        },
      ),
    );
  }

  static String _coverUrlFor(Map<String, dynamic> item) {
    final cover = (item['coverUrl'] ?? item['thumbnailUrl'] ?? '').toString();
    if (cover.isNotEmpty) return cover;
    final imageUrls = item['imageUrls'];
    if (imageUrls is List && imageUrls.isNotEmpty) {
      return imageUrls.first.toString();
    }
    return '';
  }

  static String _titleFor(Map<String, dynamic> item) {
    return (item['title'] ?? '').toString();
  }

  static String _bodyFor(Map<String, dynamic> item) {
    return (item['body'] ?? item['description'] ?? item['content'] ?? '')
        .toString();
  }

  static String _authorNameFor(Map<String, dynamic> item) {
    final authorName =
        (item['authorNickname'] ??
                item['displayName'] ??
                item['username'] ??
                item['authorId'] ??
                '')
            .toString();
    return authorName.isEmpty ? UITextConstants.unknownUser : authorName;
  }

  static String _avatarUrlFor(Map<String, dynamic> item) {
    return (item['authorAvatarUrl'] ?? item['avatarUrl'] ?? '').toString();
  }

  static int _likeCountFor(Map<String, dynamic> item) {
    return (item['likeCount'] as num?)?.toInt() ??
        (item['likes'] as num?)?.toInt() ??
        0;
  }

  static double _coverAspectRatioFor(Map<String, dynamic> item) {
    final width = (item['width'] as num?)?.toDouble();
    final height = (item['height'] as num?)?.toDouble();
    if (width != null && height != null && width > 0 && height > 0) {
      return width / height;
    }
    final hasVideo = (item['videoUrl']?.toString().trim() ?? '').isNotEmpty;
    if (hasVideo) return 9 / 16;
    final hasImage =
        item['imageUrls'] is List && (item['imageUrls'] as List).isNotEmpty;
    if (hasImage) return 3 / 4;
    return 1.0;
  }
}

class _AvatarBubble extends StatelessWidget {
  const _AvatarBubble({required this.avatarUrl, required this.fallbackColor});

  final String avatarUrl;
  final Color fallbackColor;

  @override
  Widget build(BuildContext context) {
    return ClipOval(
      child: SizedBox(
        width: AppSpacing.md,
        height: AppSpacing.md,
        child: avatarUrl.isEmpty
            ? DecoratedBox(decoration: BoxDecoration(color: fallbackColor))
            : AppCachedNetworkImage(imageUrl: avatarUrl, fit: BoxFit.cover),
      ),
    );
  }
}
