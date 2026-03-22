import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
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
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
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
      padding: const EdgeInsets.all(AppSpacing.postPreviewSectionPadding),
      sliver: SliverMasonryGrid.count(
        crossAxisCount: 2,
        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
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

          final headline = title.isNotEmpty
              ? title
              : (body.isNotEmpty ? body : '帖子');
          final supportingText =
              title.isNotEmpty && body.isNotEmpty && title != body ? body : '';

          return PostPreviewCard(
            key: ValueKey(
              'home-circle-grid-post-${post['postId'] ?? post['id']}',
            ),
            isDark: isDark,
            title: headline,
            supportingText: supportingText,
            coverUrl: coverUrl,
            mediaAspectRatio: aspectRatio,
            showVideoBadge:
                (post['videoUrl']?.toString().trim() ?? '').isNotEmpty,
            onTap: () => onPostTap(post, posts),
            footer: Row(
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
                PostCardMetric(
                  icon: isLiked
                      ? CupertinoIcons.heart_fill
                      : CupertinoIcons.heart,
                  iconSize: AppSpacing.iconSmall,
                  label: '$likeCount',
                  color: fgSecondary,
                  iconColor: isLiked ? AppColors.worksLike : fgSecondary,
                ),
              ],
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
