import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/components/post/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/ui/circle/models/circle_hub_feed_post_entry.dart';

class HomeCirclesCategoryTab extends ConsumerWidget {
  final String categoryId;
  final String label;
  final List<String> subCategories;
  final List<CircleHubFeedPostEntry> posts;
  final void Function(
    CircleHubFeedPostEntry tapped,
    List<CircleHubFeedPostEntry> sourceItems,
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
        crossAxisCount: AppSpacing.responsiveGridColumns(context),
        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
        childCount: posts.length,
        itemBuilder: (context, index) {
          final entry = posts[index];
          final title = entry.wireTitle;
          final body = entry.wireBodyText;
          final authorName = entry.wireAuthorDisplayName.trim().isEmpty
              ? UITextConstants.unknownUser
              : entry.wireAuthorDisplayName.trim();
          final coverUrl = entry.wireCoverUrl;
          final avatarUrl = entry.wireAuthorAvatarUrl;
          final likeCount = entry.wireLikeCount;
          final isLiked = entry.wireIsLiked;
          final aspectRatio = entry.wireCoverAspectRatio();

          final headline = title.isNotEmpty
              ? title
              : (body.isNotEmpty ? body : '帖子');
          final supportingText =
              title.isNotEmpty && body.isNotEmpty && title != body ? body : '';

          return PostPreviewCard(
            key: ValueKey('home-circle-grid-post-${entry.postIdForKey}'),
            isDark: isDark,
            title: headline,
            supportingText: supportingText,
            coverUrl: coverUrl,
            mediaAspectRatio: aspectRatio,
            showVideoBadge: entry.wireShowsVideoBadge,
            onTap: () => onPostTap(entry, posts),
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
