import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/ui/content/post_summary_view.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/ui/user/models/profile_mode.dart';
import 'package:quwoquan_app/ui/user/providers/profile_state_provider.dart';

/// 微趣 Tab：微博风格单列社交信息流，展示方式与发现页微趣一致。
class ProfileMomentsTab extends ConsumerWidget {
  const ProfileMomentsTab({
    super.key,
    required this.mode,
    required this.userId,
    required this.isDark,
  });

  final ProfileMode mode;
  final String userId;
  final bool isDark;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final state = ref.watch(profileNotifierProvider(userId));
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );

    final moments = state.creations
        .where((post) => post.identity == 'moment')
        .toList(growable: false);

    if (moments.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(
              Icons.chat_bubble_outline,
              size: AppSpacing.xl * 2,
              color: fgSecondary,
            ),
            SizedBox(height: AppSpacing.md),
            Text(
              mode == ProfileMode.mine ? '还没有微趣' : 'Ta 还没有微趣',
              style: TextStyle(fontSize: AppTypography.md, color: fgSecondary),
            ),
          ],
        ),
      );
    }

    final dividerColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary);

    return ListView.builder(
      padding: EdgeInsets.only(
        top: AppSpacing.containerSm,
        bottom: AppSpacing.interGroupLg,
      ),
      itemCount: moments.length,
      itemBuilder: (context, index) {
        final dto = moments[index];
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.symmetric(
                horizontal: AppSpacing.feedContentHorizontal(context),
              ),
              child: _ProfileMomentCard(item: dto, isDark: isDark, userId: userId),
            ),
            if (index < moments.length - 1)
              Container(height: AppSpacing.sm, color: dividerColor),
          ],
        );
      },
    );
  }
}

class _ProfileMomentCard extends ConsumerStatefulWidget {
  const _ProfileMomentCard({
    required this.item,
    required this.isDark,
    required this.userId,
  });

  final PostBaseDto item;
  final bool isDark;
  final String userId;

  @override
  ConsumerState<_ProfileMomentCard> createState() => _ProfileMomentCardState();
}

class _ProfileMomentCardState extends ConsumerState<_ProfileMomentCard> {
  static const int _maxLines = 5;
  bool _isExpanded = false;

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final isDark = widget.isDark;
    final fg =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final bg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);
    final userId = widget.userId;

    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerMd),
      color: bg,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                radius: AppSpacing.avatarUserMd / 2,
                backgroundImage: item.avatarUrl.isNotEmpty
                    ? NetworkImage(item.avatarUrl)
                    : null,
                backgroundColor: AppColors.followingButtonOnDark,
              ),
              SizedBox(width: AppSpacing.intraGroupMd),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      item.displayName,
                      style: TextStyle(
                        fontSize: AppTypography.base,
                        fontWeight: AppTypography.semiBold,
                        color: fg,
                      ),
                    ),
                    SizedBox(height: AppSpacing.intraGroupXs / 2),
                    Text(
                      _timeAgo(item.createdAt),
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: muted,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
          if (item.normalizedBody.isNotEmpty) ...[
            SizedBox(height: AppSpacing.intraGroupSm),
            _ExpandableText(
              text: item.normalizedBody,
              maxLines: _maxLines,
              isDark: isDark,
              expanded: _isExpanded,
              onToggle: () => setState(() => _isExpanded = !_isExpanded),
            ),
          ],
          if (item.hasImages) ...[
            SizedBox(height: AppSpacing.interGroupSm),
            GestureDetector(
              onTap: () {
                final state = ref.read(profileNotifierProvider(userId));
                final moments = state.creations
                    .where((post) => post.identity == 'moment')
                    .toList();
                final initialIndex = moments.indexWhere((p) => p.id == item.id).clamp(0, moments.length - 1);
                final postViews = moments.map(PostSummaryView.fromDto).toList();
                
                context.push(
                  '/media-viewer/photo/$initialIndex',
                  extra: MediaViewerExtra(
                    posts: postViews,
                    dtoPosts: moments,
                    initialIndex: initialIndex,
                    category: 'moment',
                    initialImageIndex: 0,
                    source: 'profile_moment',
                  ),
                );
              },
              child: AbsorbPointer(child: _MomentImageGrid(urls: item.mediaImageUrls)),
            ),
          ],
          if (item.hasVideo && !item.hasImages) ...[
            SizedBox(height: AppSpacing.interGroupSm),
            GestureDetector(
              onTap: () {
                final state = ref.read(profileNotifierProvider(userId));
                final moments = state.creations
                    .where((post) => post.identity == 'moment')
                    .toList();
                final initialIndex = moments.indexWhere((p) => p.id == item.id).clamp(0, moments.length - 1);
                final postViews = moments.map(PostSummaryView.fromDto).toList();
                
                context.push(
                  '/video-viewer/$initialIndex',
                  extra: MediaViewerExtra(
                    posts: postViews,
                    dtoPosts: moments,
                    initialIndex: initialIndex,
                    category: 'moment',
                    source: 'profile_moment',
                  ),
                );
              },
              child: AbsorbPointer(child: _MomentVideoCard(dto: item, isDark: isDark)),
            ),
          ],
          SizedBox(height: AppSpacing.interGroupSm),
          _ActionRow(item: item, isDark: isDark),
        ],
      ),
    );
  }

  static String _timeAgo(DateTime t) {
    final delta = DateTime.now().difference(t).inHours;
    if (delta < 1) return '刚刚';
    if (delta < 24) return '$delta 小时前';
    return '${t.month}-${t.day}';
  }
}

// ── 可展开文字 ───────────────────────────────────────────────────────────────

class _ExpandableText extends StatelessWidget {
  const _ExpandableText({
    required this.text,
    required this.maxLines,
    required this.isDark,
    required this.expanded,
    required this.onToggle,
  });

  final String text;
  final int maxLines;
  final bool isDark;
  final bool expanded;
  final VoidCallback onToggle;

  @override
  Widget build(BuildContext context) {
    final fg =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final textStyle = TextStyle(
      fontSize: AppTypography.lg,
      color: fg,
      height: AppTypography.lineHeightRelaxed,
    );

    return LayoutBuilder(builder: (context, constraints) {
      final tp = TextPainter(
        text: TextSpan(text: text, style: textStyle),
        maxLines: maxLines,
        textDirection: TextDirection.ltr,
      )..layout(maxWidth: constraints.maxWidth);
      final isOverflow = tp.didExceedMaxLines;

      if (!isOverflow) {
        return Text(text, style: textStyle);
      }

      return Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            text,
            style: textStyle,
            maxLines: expanded ? null : maxLines,
            overflow: expanded ? null : TextOverflow.ellipsis,
          ),
          SizedBox(height: AppSpacing.intraGroupXs),
          GestureDetector(
            onTap: onToggle,
            child: Text(
              expanded ? '收起' : '展开',
              style: TextStyle(
                fontSize: AppTypography.sm,
                color: AppColors.primaryColor,
                fontWeight: AppTypography.medium,
              ),
            ),
          ),
        ],
      );
    });
  }
}

// ── 自适应图片宫格 ──────────────────────────────────────────────────────────

class _MomentImageGrid extends StatelessWidget {
  const _MomentImageGrid({required this.urls});

  final List<String> urls;

  @override
  Widget build(BuildContext context) {
    if (urls.isEmpty) return const SizedBox.shrink();
    if (urls.length == 1) return _singleImage(urls.first);
    if (urls.length == 2) return _doubleImages();
    return _nineGrid();
  }

  Widget _singleImage(String url) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: AspectRatio(aspectRatio: 4 / 3, child: _img(url)),
    );
  }

  Widget _doubleImages() {
    return Row(
      children: [
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.only(
              topLeft: Radius.circular(AppSpacing.borderRadius),
              bottomLeft: Radius.circular(AppSpacing.borderRadius),
            ),
            child: AspectRatio(aspectRatio: 1, child: _img(urls[0])),
          ),
        ),
        SizedBox(width: AppSpacing.xs),
        Expanded(
          child: ClipRRect(
            borderRadius: BorderRadius.only(
              topRight: Radius.circular(AppSpacing.borderRadius),
              bottomRight: Radius.circular(AppSpacing.borderRadius),
            ),
            child: AspectRatio(aspectRatio: 1, child: _img(urls[1])),
          ),
        ),
      ],
    );
  }

  Widget _nineGrid() {
    final count = urls.length.clamp(1, 9);
    final rows = (count / 3).ceil();
    final gap = AppSpacing.xs;

    return Column(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(rows, (row) {
        final start = row * 3;
        final end = (start + 3).clamp(0, count);
        return Padding(
          padding: EdgeInsets.only(top: row == 0 ? 0 : gap),
          child: Row(
            children: List.generate(end - start, (col) {
              final idx = start + col;
              return Expanded(
                child: Padding(
                  padding: EdgeInsets.only(left: col == 0 ? 0 : gap),
                  child: ClipRRect(
                    borderRadius:
                        BorderRadius.circular(AppSpacing.smallBorderRadius),
                    child: AspectRatio(
                      aspectRatio: 1,
                      child: idx < urls.length
                          ? _img(urls[idx])
                          : Container(color: AppColors.gridImagePlaceholderLight),
                    ),
                  ),
                ),
              );
            }),
          ),
        );
      }),
    );
  }

  Widget _img(String url) {
    if (url.isEmpty) {
      return Container(color: AppColors.gridImagePlaceholderLight);
    }
    return CachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      placeholder: (context, url) =>
          Container(color: AppColors.gridImagePlaceholderLight),
      errorWidget: (context, url, err) =>
          Container(color: AppColors.gridImagePlaceholderLight),
    );
  }
}

// ── 视频卡片 ────────────────────────────────────────────────────────────────

class _MomentVideoCard extends StatelessWidget {
  const _MomentVideoCard({required this.dto, required this.isDark});

  final PostBaseDto dto;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    return ClipRRect(
      borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
      child: AspectRatio(
        aspectRatio: 16 / 9,
        child: Stack(
          fit: StackFit.expand,
          children: [
            Container(color: AppColors.momentVideoCardBackdrop),
            Center(
              child: Container(
                width: AppSpacing.videoPlayOverlaySize,
                height: AppSpacing.videoPlayOverlaySize,
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppColors.black.withValues(alpha: 0.5),
                  border: Border.all(
                    color: AppColors.white,
                    width: AppSpacing.toolPanelItemBorderWidthSelected,
                  ),
                ),
                child: Icon(
                  CupertinoIcons.play_fill,
                  color: AppColors.white,
                  size: AppSpacing.videoPlayOverlayIconSize,
                ),
              ),
            ),
            if (dto.durationMs != null)
              Positioned(
                right: AppSpacing.intraGroupMd,
                bottom: AppSpacing.intraGroupSm,
                child: Container(
                  padding: EdgeInsets.symmetric(
                    horizontal: AppSpacing.intraGroupSm,
                    vertical: AppSpacing.xs / 2,
                  ),
                  decoration: BoxDecoration(
                    color: AppColors.black.withValues(alpha: 0.6),
                    borderRadius:
                        BorderRadius.circular(AppSpacing.smallBorderRadius),
                  ),
                  child: Text(
                      _formatDuration(dto.durationMs!),
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: AppColors.white,
                      fontWeight: AppTypography.semiBold,
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  static String _formatDuration(int ms) {
    final s = ms ~/ 1000;
    final m = s ~/ 60;
    final sec = s % 60;
    return '${m.toString().padLeft(2, '0')}:${sec.toString().padLeft(2, '0')}';
  }
}

// ── 互动操作行 ──────────────────────────────────────────────────────────────

class _ActionRow extends StatelessWidget {
  const _ActionRow({required this.item, required this.isDark});

  final PostBaseDto item;
  final bool isDark;

  static String _fmt(int n) {
    return formatCompactActionCount(n);
  }

  @override
  Widget build(BuildContext context) {
    final muted =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        _chip(
          child: Icon(CupertinoIcons.heart,
              size: AppSpacing.iconMedium, color: muted),
          label: _fmt(item.likeCount),
          muted: muted,
        ),
        _chip(
          child: Icon(CupertinoIcons.arrowshape_turn_up_right,
              size: AppSpacing.iconMedium, color: muted),
          label: _fmt(item.shareCount),
          muted: muted,
        ),
        _chip(
          child: Icon(CupertinoIcons.star,
              size: AppSpacing.iconMedium, color: muted),
          label: _fmt(item.favoriteCount),
          muted: muted,
        ),
        _chip(
          child: Icon(CupertinoIcons.chat_bubble,
              size: AppSpacing.iconMedium, color: muted),
          label: _fmt(item.commentCount),
          muted: muted,
        ),
      ],
    );
  }

  Widget _chip({
    required Widget child,
    required String label,
    required Color muted,
  }) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        child,
        SizedBox(width: AppSpacing.intraGroupXs),
        Text(
          label,
          style: TextStyle(fontSize: AppTypography.sm, color: muted),
        ),
      ],
    );
  }
}
