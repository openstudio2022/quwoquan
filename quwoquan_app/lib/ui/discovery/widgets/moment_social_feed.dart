// ignore_for_file: unnecessary_non_null_assertion
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_feed_provider.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_state.dart';
import 'package:quwoquan_app/core/services/app_content_repository.dart';

/// 微趣频道：微博风格社交信息流
///
/// - 单列时间流
/// - 图片自适应：1 张全宽 4:3，2 张双列 1:1，3-9 张三列九宫格
/// - 文字超 5 行展示"展开"按钮，就地展开/收起
/// - 视频帖：内联视频卡片（静态封面 + 播放标识）
class MomentSocialFeed extends ConsumerWidget {
  const MomentSocialFeed({
    super.key,
    required this.isDark,
    required this.onUserTap,
    this.onPostTap,
    this.onMoreTap,
  });

  final bool isDark;
  final void Function(String userId,
      {String? avatarUrl,
      String? displayName,
      String? backgroundUrl}) onUserTap;
  /// 点击图片/视频时打开侵入式浏览器；若仅需埋点可传 (post, i) => _trackBehavior('click', post)
  final void Function(PostBaseDto post, int index, {List<PostBaseDto>? feedPosts})? onPostTap;
  final void Function(dynamic post)? onMoreTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final discoveryState = ref.watch(discoveryStateProvider);
    final feedAsync = ref.watch(discoveryFeedProvider('moment'));
    final fallbackRaw =
        ref.watch(appContentRepositoryProvider).discoveryMomentData;
    final feedMap = ref.watch(discoveryFeedMapProvider);

    if (!feedMap.containsKey('moment')) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load('moment');
      });
    }

    final dtos = feedAsync.value?.items ??
        fallbackRaw.map(postBaseDtoFromMap).toList(growable: false);
    final moments = dtos.whereType<MomentPostDto>().toList(growable: false);
    final hasError = feedAsync.value?.error != null;

    if (feedAsync.isLoading && moments.isEmpty && !hasError) {
      return const Center(child: CircularProgressIndicator());
    }

    if (hasError && moments.isEmpty) {
      return Center(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.interGroupLg),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                context.l10n.loadFailed,
                style: TextStyle(
                  color: Theme.of(context).colorScheme.error,
                  fontSize: AppTypography.base,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: AppSpacing.interGroupMd),
              TextButton.icon(
                onPressed: () =>
                    ref.read(discoveryFeedMapProvider.notifier).load('moment'),
                icon: const Icon(Icons.refresh),
                label: Text(context.l10n.retry),
              ),
            ],
          ),
        ),
      );
    }

    final horizontal = AppSpacing.feedContentHorizontal(context);
    final dividerColor =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundTertiary);

    return ListView.builder(
      padding: EdgeInsets.only(
        top: AppSpacing.containerSm,
        bottom: MediaQuery.of(context).padding.bottom +
            AppSpacing.bottomNavHeight +
            AppSpacing.interGroupLg,
      ),
      itemCount: moments.length,
      itemBuilder: (context, index) {
        final dto = moments[index];
        // 首次渲染时上报曝光（Tracker 内部去重）
        WidgetsBinding.instance.addPostFrameCallback((_) {
          ref.read(contentBehaviorTrackerProvider).trackImpression(dto.id);
        });
        return Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Padding(
              padding: EdgeInsets.symmetric(horizontal: horizontal),
              child: _MomentWeiboCard(
                item: dto,
                isDark: isDark,
                isLiked: discoveryState.likedPosts.contains(dto.id),
                isBookmarked: discoveryState.savedPosts.contains(dto.id),
                likeCount: (() {
                  final n = discoveryState.getPostLikesCount(dto.id);
                  return n > 0 ? n : dto.likeCount;
                })(),
                favoriteCount: (() {
                  final n = discoveryState.getPostBookmarksCount(dto.id);
                  return n > 0 ? n : dto.favoriteCount;
                })(),
                onUserTap: (id) => onUserTap(
                  id,
                  avatarUrl: dto.avatarUrl,
                  displayName: dto.displayName,
                  backgroundUrl: dto.authorBackgroundUrl,
                ),
                onImageTap: (imgIndex) =>
                    onPostTap?.call(dto, imgIndex, feedPosts: moments),
                onCommentTap: () {
                  CommentViewer.showModal(
                    context: context,
                    postId: dto.id,
                  );
                },
                onShareTap: () {
                  ref.read(discoveryStateProvider).incrementShares(dto.id);
                  ref.read(contentBehaviorTrackerProvider).trackShare(dto.id);
                  _showShare(context);
                },
                onLikeTap: () {
                  ref.read(discoveryStateProvider).toggleLike(
                    dto.id,
                    baseLikesCount: dto.likeCount,
                  );
                },
                onBookmarkTap: () {
                  ref.read(discoveryStateProvider).toggleSave(
                    dto.id,
                    baseBookmarksCount: dto.favoriteCount,
                  );
                },
                onMoreTap: () {
                  if (onMoreTap != null) {
                    onMoreTap!(dto);
                  } else {
                    MoreActionPopup.show(
                      context: context,
                      config: MediaPostMoreActionConfig(
                        post: dto,
                        onNotInterested: () {
                          ref.read(contentBehaviorTrackerProvider).trackDislike(dto.id);
                        },
                        onBlockUser: () {
                          ref.read(blockRepositoryProvider).blockUser(dto.authorId);
                        },
                        onBlockWords: () async {
                          final keyword = _extractKeyword(dto.body);
                          if (keyword.isEmpty) return;
                          await ref.read(keywordBlockRepositoryProvider).addBlockedKeyword(keyword);
                        },
                        onReport: () {
                          ref.read(behaviorRepositoryProvider).reportSingle(
                            contentId: dto.id,
                            action: 'report',
                          );
                          ref.read(reportRepositoryProvider).createReport(
                            targetId: dto.id,
                            targetType: 'post',
                            reason: 'inappropriate',
                          );
                        },
                      ),
                    );
                  }
                },
              ),
            ),
            if (index < moments.length - 1)
              Container(
                height: AppSpacing.sm,
                color: dividerColor,
              ),
          ],
        );
      },
    );
  }

  void _showShare(BuildContext context) {
    showModalBottomSheet<void>(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: EdgeInsets.all(AppSpacing.containerMd),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              ListTile(
                leading: const Icon(Icons.link),
                title: Text(UITextConstants.copyLink),
                onTap: () => Navigator.pop(ctx),
              ),
            ],
          ),
        ),
      ),
    );
  }

  String _extractKeyword(String text) {
    final tokens = text
        .split(RegExp(r'[^\\u4e00-\\u9fa5A-Za-z0-9_]+'))
        .map((e) => e.trim())
        .where((e) => e.length >= 2)
        .toList();
    return tokens.isEmpty ? '' : tokens.first;
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 单条微趣卡片（微博风格）
// ─────────────────────────────────────────────────────────────────────────────

class _MomentWeiboCard extends ConsumerStatefulWidget {
  const _MomentWeiboCard({
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.isBookmarked,
    required this.likeCount,
    required this.favoriteCount,
    required this.onUserTap,
    required this.onImageTap,
    required this.onCommentTap,
    required this.onShareTap,
    required this.onLikeTap,
    required this.onBookmarkTap,
    required this.onMoreTap,
  });

  final MomentPostDto item;
  final bool isDark;
  final bool isLiked;
  final bool isBookmarked;
  final int likeCount;
  final int favoriteCount;
  final void Function(String) onUserTap;
  final void Function(int imageIndex) onImageTap;
  final VoidCallback onCommentTap;
  final VoidCallback onShareTap;
  final VoidCallback onLikeTap;
  final VoidCallback onBookmarkTap;
  final VoidCallback onMoreTap;

  @override
  ConsumerState<_MomentWeiboCard> createState() => _MomentWeiboCardState();
}

class _MomentWeiboCardState extends ConsumerState<_MomentWeiboCard>
    with SingleTickerProviderStateMixin {
  static const int _maxLines = 5;

  bool _isExpanded = false;
  late AnimationController _likeCtrl;

  @override
  void initState() {
    super.initState();
    _likeCtrl = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 200),
    );
  }

  @override
  void dispose() {
    _likeCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final isDark = widget.isDark;
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final muted =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final bg =
        AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

    return Container(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerMd),
      color: bg,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // 头像 + 作者信息行
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GestureDetector(
                onTap: () => widget.onUserTap(item.authorId),
                child: CircleAvatar(
                  radius: AppSpacing.avatarUserMd / 2,
                  backgroundImage: item.avatarUrl.isNotEmpty
                      ? NetworkImage(item.avatarUrl)
                      : null,
                  backgroundColor: AppColors.followingButtonOnDark,
                ),
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
              IconButton(
                icon: Icon(Icons.more_horiz,
                    size: AppSpacing.iconMedium, color: muted),
                onPressed: widget.onMoreTap,
                style: IconButton.styleFrom(
                  minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                ),
              ),
            ],
          ),

          // 正文（5 行截断 + 就地展开）
          if (item.body.isNotEmpty) ...[
            SizedBox(height: AppSpacing.intraGroupSm),
            _ExpandableText(
              text: item.body,
              maxLines: _maxLines,
              isDark: isDark,
              expanded: _isExpanded,
              onToggle: () => setState(() => _isExpanded = !_isExpanded),
            ),
          ],

          // 图片区域（自适应宫格）
          if (item.hasImages) ...[
            SizedBox(height: AppSpacing.interGroupSm),
            _MomentImageGrid(
              urls: item.imageUrls,
              onTap: widget.onImageTap,
            ),
          ],

          // 视频卡片
          if (item.hasVideo && !item.hasImages) ...[
            SizedBox(height: AppSpacing.interGroupSm),
            _MomentVideoCard(
              dto: item,
              isDark: isDark,
              onTap: () => widget.onImageTap(0),
            ),
          ],

          // 互动栏
          SizedBox(height: AppSpacing.interGroupSm),
          _ActionRow(
            item: item,
            isDark: isDark,
            isLiked: widget.isLiked,
            isBookmarked: widget.isBookmarked,
            likeCount: widget.likeCount,
            favoriteCount: widget.favoriteCount,
            likeCtrl: _likeCtrl,
            onLike: () {
              final wasLiked = widget.isLiked;
              _likeCtrl.forward(from: 0);
              widget.onLikeTap();
              final repo = ref.read(contentInteractionRepositoryProvider);
              if (wasLiked) repo.unlike(widget.item.id);
              if (!wasLiked) repo.like(widget.item.id);
            },
            onBookmark: () {
              final wasBookmarked = widget.isBookmarked;
              widget.onBookmarkTap();
              final repo = ref.read(contentInteractionRepositoryProvider);
              if (wasBookmarked) repo.unfavorite(widget.item.id);
              if (!wasBookmarked) repo.favorite(widget.item.id);
            },
            onComment: widget.onCommentTap,
            onShare: widget.onShareTap,
          ),
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

// ─────────────────────────────────────────────────────────────────────────────
// 可展开文字
// ─────────────────────────────────────────────────────────────────────────────

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
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
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

// ─────────────────────────────────────────────────────────────────────────────
// 自适应图片宫格：1=全宽 4:3 / 2=双列 1:1 / 3~9=三列九宫格
// ─────────────────────────────────────────────────────────────────────────────

class _MomentImageGrid extends StatelessWidget {
  const _MomentImageGrid({
    required this.urls,
    required this.onTap,
  });

  final List<String> urls;
  final void Function(int index) onTap;

  @override
  Widget build(BuildContext context) {
    if (urls.isEmpty) return const SizedBox.shrink();
    if (urls.length == 1) return _singleImage(context, urls.first, 0);
    if (urls.length == 2) return _doubleImages(context);
    return _nineGrid(context);
  }

  Widget _singleImage(BuildContext context, String url, int index) {
    return GestureDetector(
      onTap: () => onTap(index),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: AspectRatio(
          aspectRatio: 4 / 3,
          child: _img(url),
        ),
      ),
    );
  }

  Widget _doubleImages(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: GestureDetector(
            onTap: () => onTap(0),
            child: ClipRRect(
              borderRadius: BorderRadius.only(
                topLeft: Radius.circular(AppSpacing.borderRadius),
                bottomLeft: Radius.circular(AppSpacing.borderRadius),
              ),
              child: AspectRatio(aspectRatio: 1, child: _img(urls[0])),
            ),
          ),
        ),
        SizedBox(width: AppSpacing.xs),
        Expanded(
          child: GestureDetector(
            onTap: () => onTap(1),
            child: ClipRRect(
              borderRadius: BorderRadius.only(
                topRight: Radius.circular(AppSpacing.borderRadius),
                bottomRight: Radius.circular(AppSpacing.borderRadius),
              ),
              child: AspectRatio(aspectRatio: 1, child: _img(urls[1])),
            ),
          ),
        ),
      ],
    );
  }

  Widget _nineGrid(BuildContext context) {
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
                  child: GestureDetector(
                    onTap: () => onTap(idx),
                    child: ClipRRect(
                      borderRadius:
                          BorderRadius.circular(AppSpacing.smallBorderRadius),
                      child: AspectRatio(
                        aspectRatio: 1,
                        child: idx < urls.length
                            ? _img(urls[idx])
                            : Container(color: Colors.grey.shade200),
                      ),
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
      return Container(color: Colors.grey.shade200);
    }
    return CachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      placeholder: (context, url) => Container(color: Colors.grey.shade200),
      errorWidget: (context, url, err) => Container(color: Colors.grey.shade200),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 视频卡片（静态封面 + 时长 + 播放标识）
// ─────────────────────────────────────────────────────────────────────────────

class _MomentVideoCard extends StatelessWidget {
  const _MomentVideoCard({
    required this.dto,
    required this.isDark,
    required this.onTap,
  });

  final MomentPostDto dto;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: Stack(
            fit: StackFit.expand,
            children: [
              Container(color: Colors.grey.shade900),
              // 中央播放按钮
              Center(
                child: Container(
                  width: AppSpacing.videoPlayOverlaySize,
                  height: AppSpacing.videoPlayOverlaySize,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: Colors.black.withValues(alpha: 0.5),
                    border: Border.all(
                      color: Colors.white,
                      width: AppSpacing.toolPanelItemBorderWidthSelected,
                    ),
                  ),
                  child: Icon(
                    CupertinoIcons.play_fill,
                    color: Colors.white,
                    size: AppSpacing.videoPlayOverlayIconSize,
                  ),
                ),
              ),
              // 时长
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
                      color: Colors.black.withValues(alpha: 0.6),
                      borderRadius: BorderRadius.circular(
                          AppSpacing.smallBorderRadius),
                    ),
                    child: Text(
                      _formatDuration(dto.durationMs!),
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: Colors.white,
                        fontWeight: AppTypography.semiBold,
                      ),
                    ),
                  ),
                ),
            ],
          ),
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

// ─────────────────────────────────────────────────────────────────────────────
// 互动操作行（赞/藏/评/分享）
// ─────────────────────────────────────────────────────────────────────────────

/// Action row for moment (微趣) posts.
/// Order and icon set are identical to the works channel:
/// 赞 · 分享 · 收藏 · 评论  — equally spaced with MainAxisAlignment.spaceBetween.
class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.isBookmarked,
    required this.likeCount,
    required this.favoriteCount,
    required this.likeCtrl,
    required this.onLike,
    required this.onBookmark,
    required this.onComment,
    required this.onShare,
  });

  final MomentPostDto item;
  final bool isDark;
  final bool isLiked;
  final bool isBookmarked;
  final int likeCount;
  final int favoriteCount;
  final AnimationController likeCtrl;
  final VoidCallback onLike;
  final VoidCallback onBookmark;
  final VoidCallback onComment;
  final VoidCallback onShare;

  /// Mirrors _WorksImmersiveViewerState._formatCount.
  /// < 10 000 : raw  |  10 000–99 999 : x.y万+  |  ≥ 100 000 : 10万+
  static String _fmt(int n) {
    if (n < 10000) return '$n';
    if (n >= 100000) return '10万+';
    final tenK = (n / 10000 * 10).floor() / 10;
    return (tenK * 10).round() % 10 == 0
        ? '${tenK.truncate()}万+'
        : '$tenK万+';
  }

  @override
  Widget build(BuildContext context) {
    final muted =
        AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final likeColor = isLiked ? AppColors.worksLike : muted;
    final bookmarkColor = isBookmarked ? AppColors.warning : muted;

    final likeScale = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween<double>(begin: 1.0, end: 1.25)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 50,
      ),
      TweenSequenceItem(
        tween: Tween<double>(begin: 1.25, end: 1.0)
            .chain(CurveTween(curve: Curves.easeIn)),
        weight: 50,
      ),
    ]).animate(likeCtrl);

    // All four chips are rendered identically to the works channel:
    // icon + count text, distributed with equal spacing.
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceBetween,
      children: [
        // 赞
        _chip(
          child: ScaleTransition(
            scale: likeScale,
            child: Icon(
              isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
              size: AppSpacing.iconMedium,
              color: likeColor,
            ),
          ),
          label: _fmt(likeCount),
          muted: muted,
          onTap: onLike,
        ),
        // 分享
        _chip(
          child: Icon(
            CupertinoIcons.arrowshape_turn_up_right,
            size: AppSpacing.iconMedium,
            color: muted,
          ),
          label: _fmt(item.shareCount),
          muted: muted,
          onTap: onShare,
        ),
        // 收藏 (star, matching the works channel)
        _chip(
          child: Icon(
            isBookmarked ? CupertinoIcons.star_fill : CupertinoIcons.star,
            size: AppSpacing.iconMedium,
            color: bookmarkColor,
          ),
          label: _fmt(favoriteCount),
          muted: muted,
          onTap: onBookmark,
        ),
        // 评论
        _chip(
          child: Icon(
            CupertinoIcons.chat_bubble,
            size: AppSpacing.iconMedium,
            color: muted,
          ),
          label: _fmt(item.commentCount),
          muted: muted,
          onTap: onComment,
        ),
      ],
    );
  }

  Widget _chip({
    required Widget child,
    required String label,
    required Color muted,
    required VoidCallback onTap,
  }) {
    return GestureDetector(
      onTap: onTap,
      behavior: HitTestBehavior.opaque,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          child,
          SizedBox(width: AppSpacing.intraGroupXs),
          Text(
            label,
            style: TextStyle(
              fontSize: AppTypography.sm,
              color: muted,
            ),
          ),
        ],
      ),
    );
  }
}
