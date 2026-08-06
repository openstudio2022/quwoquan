import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_staggered_grid_view/flutter_staggered_grid_view.dart';
import 'package:quwoquan_app/content/content/post/presentation/post_preview_card.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_cached_network_image.dart';
import 'package:quwoquan_app/circle/circle_management/circle/domain/circle_hub_feed_post_entry.dart';

const Set<String> _visualPriorityCategoryIds = <String>{
  'travel',
  'photography',
};

@visibleForTesting
int resolveHomeCircleCategoryGridColumns(
  BuildContext context,
  String categoryId,
) {
  return AppSpacing.responsiveGridColumns(context);
}

class HomeCirclesCategoryTab extends ConsumerWidget {
  final String categoryId;
  final String label;
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
              '$label ${CommunityText.noData}',
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: fgSecondary,
              ),
            ),
          ),
        ),
      );
    }

    final horizontal = AppSpacing.feedContentHorizontal(context);

    return SliverPadding(
      key: ValueKey<String>('home-circles-category-$categoryId'),
      padding: EdgeInsets.fromLTRB(
        horizontal,
        AppSpacing.xs,
        horizontal,
        AppSpacing.containerXs,
      ),
      sliver: SliverMasonryGrid.count(
        crossAxisCount: resolveHomeCircleCategoryGridColumns(
          context,
          categoryId,
        ),
        mainAxisSpacing: AppSpacing.postPreviewGridSpacing,
        crossAxisSpacing: AppSpacing.postPreviewGridSpacing,
        childCount: posts.length,
        itemBuilder: (context, index) {
          final entry = posts[index];
          final title = entry.title;
          final body = entry.bodyText;
          final authorName = entry.authorDisplayName.isEmpty
              ? FoundationText.unknownUser
              : entry.authorDisplayName;
          final coverUrl = entry.coverUrl;
          final avatarUrl = entry.authorAvatarUrl;
          final likeCount = entry.likeCount;
          final isLiked = entry.isLiked;
          final aspectRatio = entry.coverAspectRatio;
          final inlineImageUrls = entry.showsVideoBadge
              ? const <String>[]
              : entry.imageUrls;
          final usesInlineImages =
              _visualPriorityCategoryIds.contains(
                categoryId.trim().toLowerCase(),
              ) &&
              inlineImageUrls.isNotEmpty;

          final headline = title.isNotEmpty
              ? title
              : (body.isNotEmpty ? body : '帖子');
          final supportingText =
              title.isNotEmpty && body.isNotEmpty && title != body ? body : '';

          return PostPreviewCard(
            key: ValueKey('home-circle-grid-post-${entry.postId}'),
            isDark: isDark,
            title: headline,
            supportingText: supportingText,
            coverUrl: coverUrl,
            mediaAspectRatio: aspectRatio,
            showVideoBadge: entry.showsVideoBadge,
            mediaContent: usesInlineImages
                ? _HomeCircleInlineImageCarousel(
                    imageUrls: inlineImageUrls,
                    isDark: isDark,
                  )
                : null,
            onTap: usesInlineImages ? () {} : () => onPostTap(entry, posts),
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

class _HomeCircleInlineImageCarousel extends StatefulWidget {
  const _HomeCircleInlineImageCarousel({
    required this.imageUrls,
    required this.isDark,
  });

  final List<String> imageUrls;
  final bool isDark;

  @override
  State<_HomeCircleInlineImageCarousel> createState() =>
      _HomeCircleInlineImageCarouselState();
}

class _HomeCircleInlineImageCarouselState
    extends State<_HomeCircleInlineImageCarousel> {
  late final PageController _controller;
  int _index = 0;

  @override
  void initState() {
    super.initState();
    _controller = PageController();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final urls = widget.imageUrls
        .map((url) => url.trim())
        .where((url) => url.isNotEmpty)
        .toList(growable: false);
    if (urls.isEmpty) {
      return const SizedBox.shrink();
    }
    return Stack(
      fit: StackFit.expand,
      children: [
        PageView.builder(
          controller: _controller,
          itemCount: urls.length,
          onPageChanged: (next) => setState(() => _index = next),
          itemBuilder: (context, index) {
            return AppCachedNetworkImage(
              imageUrl: urls[index],
              fit: BoxFit.cover,
            );
          },
        ),
        if (urls.length > 1)
          Positioned(
            left: 0,
            right: 0,
            bottom: AppSpacing.intraGroupSm,
            child: _HomeCircleCarouselDots(
              total: urls.length,
              activeIndex: _index,
              isDark: widget.isDark,
            ),
          ),
      ],
    );
  }
}

class _HomeCircleCarouselDots extends StatelessWidget {
  const _HomeCircleCarouselDots({
    required this.total,
    required this.activeIndex,
    required this.isDark,
  });

  final int total;
  final int activeIndex;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    final visibleTotal = total.clamp(1, 7).toInt();
    final active = total <= visibleTotal
        ? activeIndex
        : ((activeIndex / (total - 1)) * (visibleTotal - 1)).round();
    final color = isDark ? AppColors.white : AppColors.black;
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        for (var i = 0; i < visibleTotal; i++) ...[
          if (i > 0) const SizedBox(width: AppSpacing.xs),
          AnimatedContainer(
            duration: const Duration(milliseconds: 160),
            width: i == active ? AppSpacing.containerSm : AppSpacing.xs,
            height: AppSpacing.xs,
            decoration: BoxDecoration(
              color: color.withValues(alpha: i == active ? 0.86 : 0.42),
              borderRadius: BorderRadius.circular(AppSpacing.xs),
            ),
          ),
        ],
      ],
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
