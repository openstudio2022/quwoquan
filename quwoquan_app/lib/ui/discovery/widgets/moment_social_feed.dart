// ignore_for_file: unnecessary_non_null_assertion
import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/l10n/app_localizations.dart';
import 'package:quwoquan_app/l10n/l10n.dart';
import 'package:quwoquan_app/components/comment_system/comment_viewer_modal.dart';
import 'package:quwoquan_app/components/more_actions_popup/configs/media_post_config.dart';
import 'package:quwoquan_app/components/more_actions_popup/more_action_popup.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/content_behavior_tracker.dart';
import 'package:quwoquan_app/ui/content/share/content_share_actions.dart';
import 'package:quwoquan_app/ui/content/share/content_share_sheet.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';
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
    this.feedTabId = 'moment',
    this.onPostTap,
    this.onMoreTap,
  });

  final bool isDark;
  final String feedTabId;
  final void Function(
    String userId, {
    String? avatarUrl,
    String? displayName,
    String? backgroundUrl,
  })
  onUserTap;

  /// 点击图片/视频时打开侵入式浏览器；若仅需埋点可传 (post, i) => _trackBehavior('click', post)
  final void Function(
    PostBaseDto post,
    int index, {
    List<PostBaseDto>? feedPosts,
  })?
  onPostTap;
  final void Function(dynamic post)? onMoreTap;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final discoveryState = ref.watch(discoveryStateProvider);
    final feedAsync = ref.watch(discoveryFeedProvider(feedTabId));
    final fallbackRaw = ref
        .watch(appContentRepositoryProvider)
        .discoveryMomentData;
    final feedMap = ref.watch(discoveryFeedMapProvider);

    if (!feedMap.containsKey(feedTabId)) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        ref.read(discoveryFeedMapProvider.notifier).load(feedTabId);
      });
    }

    final dtos =
        feedAsync.value?.items ??
        fallbackRaw.map(postBaseDtoFromMap).toList(growable: false);
    final moments = dtos
        .where((post) => post.identity == 'moment')
        .toList(growable: false);
    final hasError = feedAsync.value?.error != null;

    if (feedAsync.isLoading && moments.isEmpty && !hasError) {
      return const Center(child: CupertinoActivityIndicator());
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
                  fontSize: AppTypography.iosBody,
                ),
                textAlign: TextAlign.center,
              ),
              SizedBox(height: AppSpacing.interGroupMd),
              CupertinoButton(
                onPressed: () =>
                    ref.read(discoveryFeedMapProvider.notifier).load(feedTabId),
                padding: EdgeInsets.symmetric(
                  horizontal: AppSpacing.containerMd,
                  vertical: AppSpacing.intraGroupSm,
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      CupertinoIcons.arrow_clockwise,
                      size: AppSpacing.iconSmall,
                      color: AppColors.iosAccent(context),
                    ),
                    SizedBox(width: AppSpacing.intraGroupXs),
                    Text(
                      context.l10n.retry,
                      style: TextStyle(
                        fontSize: AppTypography.iosSubheadline,
                        fontWeight: AppTypography.semiBold,
                        color: AppColors.iosAccent(context),
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      );
    }

    final horizontal = AppSpacing.feedContentHorizontal(context);
    final pageBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );

    return ColoredBox(
      color: pageBackground,
      child: ListView.separated(
        padding: EdgeInsets.fromLTRB(
          horizontal,
          AppSpacing.interGroupSm,
          horizontal,
          MediaQuery.of(context).padding.bottom +
              AppSpacing.bottomNavHeight +
              AppSpacing.interGroupLg,
        ),
        itemCount: moments.length,
        separatorBuilder: (_, __) => SizedBox(height: AppSpacing.interGroupSm),
        itemBuilder: (context, index) {
          final dto = moments[index];
          WidgetsBinding.instance.addPostFrameCallback((_) {
            ref.read(contentBehaviorTrackerProvider).trackImpression(dto.id);
          });
          return _MomentWeiboCard(
            item: dto,
            isDark: isDark,
            isLiked: discoveryState.likedPosts.contains(dto.id),
            likeCount: (() {
              final n = discoveryState.getPostLikesCount(dto.id);
              return n > 0 ? n : dto.likeCount;
            })(),
            sourceCircleName: _resolveSourceCircleName(ref, dto.id),
            onUserTap: (id) => onUserTap(
              id,
              avatarUrl: dto.avatarUrl,
              displayName: dto.displayName,
              backgroundUrl: dto.authorBackgroundUrl,
            ),
            onImageTap: (imgIndex) =>
                onPostTap?.call(dto, imgIndex, feedPosts: moments),
            onCommentTap: () {
              CommentViewer.showModal(context: context, postId: dto.id);
            },
            onShareTap: () => _showShare(
              context,
              ref,
              dto,
              enableIdentityTemplate: ref.read(
                contentFeatureFlagProvider('enable_identity_share_template'),
              ),
            ),
            onLikeTap: () {
              ref
                  .read(discoveryStateProvider)
                  .toggleLike(dto.id, baseLikesCount: dto.likeCount);
            },
            onMoreTap: () {
              if (onMoreTap != null) {
                onMoreTap!(dto);
              } else {
                MoreActionPopup.show(
                  context: context,
                  config: MediaPostMoreActionConfig(
                    post: dto,
                    onCopyLink: () => _copyLink(
                      context,
                      ref,
                      dto,
                      enableIdentityTemplate: ref.read(
                        contentFeatureFlagProvider(
                          'enable_identity_share_template',
                        ),
                      ),
                    ),
                    onShare: () => _showShare(
                      context,
                      ref,
                      dto,
                      enableIdentityTemplate: ref.read(
                        contentFeatureFlagProvider(
                          'enable_identity_share_template',
                        ),
                      ),
                    ),
                    onNotInterested: () {
                      ref
                          .read(contentBehaviorTrackerProvider)
                          .trackDislike(dto.id);
                    },
                    onBlockUser: () {
                      ref.read(blockRepositoryProvider).blockUser(dto.authorId);
                    },
                    onBlockWords: () async {
                      final keyword = _extractKeyword(dto.normalizedBody);
                      if (keyword.isEmpty) return;
                      await ref
                          .read(keywordBlockRepositoryProvider)
                          .addBlockedKeyword(keyword);
                    },
                    onReport: () {
                      ref
                          .read(behaviorRepositoryProvider)
                          .reportSingle(contentId: dto.id, action: 'report');
                      ref
                          .read(reportRepositoryProvider)
                          .createReport(
                            targetId: dto.id,
                            targetType: 'post',
                            reason: 'inappropriate',
                          );
                    },
                  ),
                );
              }
            },
          );
        },
      ),
    );
  }

  void _showShare(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) {
    final template = _buildShareTemplate(
      ref: ref,
      post: post,
      enableIdentityTemplate: enableIdentityTemplate,
    );
    ContentShareSheet.show(
      context,
      template: template,
      onActionCompleted: (result) async {
        _recordShare(ref, post.id, result.actionId);
      },
    );
  }

  Future<void> _copyLink(
    BuildContext context,
    WidgetRef ref,
    PostBaseDto post, {
    required bool enableIdentityTemplate,
  }) async {
    final result = await const DefaultContentShareActionHandler().execute(
      context,
      _buildShareTemplate(
        ref: ref,
        post: post,
        enableIdentityTemplate: enableIdentityTemplate,
      ),
      const ContentShareAction(
        id: 'copy_link',
        label: UITextConstants.copyLink,
      ),
    );
    if (result.success) {
      _recordShare(ref, post.id, result.actionId);
    }
  }

  ContentShareTemplate _buildShareTemplate({
    required WidgetRef ref,
    required PostBaseDto post,
    required bool enableIdentityTemplate,
  }) {
    final raw = ref
        .read(appContentRepositoryProvider)
        .discoveryMomentData
        .cast<Map<String, dynamic>?>()
        .firstWhere(
          (item) =>
              item?['postId']?.toString() == post.id ||
              item?['id']?.toString() == post.id,
          orElse: () => null,
        );
    final visibility = raw?['visibility']?.toString() ?? 'public';
    final tags =
        (raw?['tags'] as List?)
            ?.map((item) => item.toString().trim())
            .where((item) => item.isNotEmpty)
            .toList(growable: false) ??
        const <String>[];
    final circleName = raw?['circleName']?.toString().trim() ?? '';
    return ContentShareTemplateBuilder.build(
      post: post,
      enableIdentityTemplate: enableIdentityTemplate,
      visibility: visibility,
      tags: tags,
      circleNames: circleName.isEmpty ? const <String>[] : <String>[circleName],
    );
  }

  void _recordShare(WidgetRef ref, String postId, String actionId) {
    ref.read(discoveryStateProvider).incrementShares(postId);
    ref
        .read(contentBehaviorTrackerProvider)
        .trackShare(postId, tags: <String>[actionId]);
  }

  String _resolveSourceCircleName(WidgetRef ref, String postId) {
    final raw = ref
        .read(appContentRepositoryProvider)
        .discoveryMomentData
        .cast<Map<String, dynamic>?>()
        .firstWhere(
          (item) =>
              item?['postId']?.toString() == postId ||
              item?['id']?.toString() == postId,
          orElse: () => null,
        );
    return raw?['circleName']?.toString().trim() ?? '';
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
    required this.likeCount,
    required this.sourceCircleName,
    required this.onUserTap,
    required this.onImageTap,
    required this.onCommentTap,
    required this.onShareTap,
    required this.onLikeTap,
    required this.onMoreTap,
  });

  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final String sourceCircleName;
  final void Function(String) onUserTap;
  final void Function(int imageIndex) onImageTap;
  final VoidCallback onCommentTap;
  final VoidCallback onShareTap;
  final VoidCallback onLikeTap;
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
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final bg = AppColorsFunctional.getColor(isDark, ColorType.surfaceElevated);

    return DecoratedBox(
      decoration: BoxDecoration(
        color: bg,
        borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
      ),
      child: Padding(
        padding: EdgeInsets.all(AppSpacing.containerMd),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // 头像 + 作者信息行
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () => widget.onUserTap(item.authorId),
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
                          fontSize: AppTypography.iosBody,
                          fontWeight: AppTypography.semiBold,
                          color: fg,
                        ),
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs / 2),
                      Text(
                        _buildMetaLine(context),
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          color: muted,
                        ),
                      ),
                    ],
                  ),
                ),
                CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.square(AppSpacing.iconButtonMinSizeSm),
                  onPressed: widget.onMoreTap,
                  child: Icon(
                    CupertinoIcons.ellipsis_circle,
                    size: AppSpacing.iconMedium,
                    color: muted.withValues(alpha: 0.9),
                  ),
                ),
              ],
            ),

            // 正文（5 行截断 + 就地展开）
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

            // 图片区域（自适应宫格）
            if (item.hasImages) ...[
              SizedBox(height: AppSpacing.interGroupSm),
              _MomentImageGrid(
                urls: item.imageUrls,
                isDark: isDark,
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
              likeCount: widget.likeCount,
              likeCtrl: _likeCtrl,
              onLike: () {
                final wasLiked = widget.isLiked;
                HapticFeedback.lightImpact();
                _likeCtrl.forward(from: 0);
                widget.onLikeTap();
                final repo = ref.read(contentInteractionRepositoryProvider);
                if (wasLiked) repo.unlike(widget.item.id);
                if (!wasLiked) repo.like(widget.item.id);
              },
              onComment: widget.onCommentTap,
              onShare: widget.onShareTap,
            ),
          ],
        ),
      ),
    );
  }

  String _buildMetaLine(BuildContext context) {
    final time = _timeAgo(context, widget.item.createdAt);
    if (widget.sourceCircleName.isEmpty) return time;
    return '$time · ${UITextConstants.sourceFromPrefix}${widget.sourceCircleName}';
  }

  static String _timeAgo(BuildContext context, DateTime t) {
    final l10n = Localizations.of<AppLocalizations>(context, AppLocalizations);
    final delta = DateTime.now().difference(t).inHours;
    if (delta < 1) return l10n?.justNow ?? '刚刚';
    if (delta < 24) return l10n?.hoursAgoTemplate(delta) ?? '$delta 小时前';
    return l10n?.monthDayTemplate(t.month, t.day) ?? '${t.month}/${t.day}';
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
    final fg = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final textStyle = TextStyle(
      fontSize: AppTypography.iosBody,
      color: fg,
      height: AppTypography.lineHeightRelaxed,
    );

    return LayoutBuilder(
      builder: (context, constraints) {
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
            CupertinoButton(
              padding: EdgeInsets.zero,
              minimumSize: Size.zero,
              onPressed: onToggle,
              child: Text(
                expanded ? UITextConstants.collapse : UITextConstants.fullText,
                style: TextStyle(
                  fontSize: AppTypography.iosFootnote,
                  color: AppColors.iosAccent(context),
                  fontWeight: AppTypography.semiBold,
                ),
              ),
            ),
          ],
        );
      },
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// 自适应图片宫格：1=全宽 4:3 / 2=双列 1:1 / 3~9=三列九宫格
// ─────────────────────────────────────────────────────────────────────────────

class _MomentImageGrid extends StatelessWidget {
  const _MomentImageGrid({
    required this.urls,
    required this.isDark,
    required this.onTap,
  });

  final List<String> urls;
  final bool isDark;
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
        child: AspectRatio(aspectRatio: 4 / 3, child: _img(url)),
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
                      borderRadius: BorderRadius.circular(
                        AppSpacing.smallBorderRadius,
                      ),
                      child: AspectRatio(
                        aspectRatio: 1,
                        child: idx < urls.length
                            ? _img(urls[idx])
                            : _placeholder(),
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
      return _placeholder();
    }
    return CachedNetworkImage(
      imageUrl: url,
      fit: BoxFit.cover,
      placeholder: (context, url) => _placeholder(),
      errorWidget: (context, url, err) => _placeholder(),
    );
  }

  Widget _placeholder() {
    return DecoratedBox(
      decoration: BoxDecoration(
        color: AppColorsFunctional.getColor(isDark, ColorType.surfaceMuted),
      ),
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

  final PostBaseDto dto;
  final bool isDark;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final surfaceMuted = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    return GestureDetector(
      onTap: onTap,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
        child: AspectRatio(
          aspectRatio: 16 / 9,
          child: Stack(
            fit: StackFit.expand,
            children: [
              DecoratedBox(decoration: BoxDecoration(color: surfaceMuted)),
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
                      color: AppColors.overlayStrong,
                      borderRadius: BorderRadius.circular(
                        AppSpacing.smallBorderRadius,
                      ),
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
/// 赞 / 转 / 评三列等宽，数字变化不挤压图标位置。
class _ActionRow extends StatelessWidget {
  const _ActionRow({
    required this.item,
    required this.isDark,
    required this.isLiked,
    required this.likeCount,
    required this.likeCtrl,
    required this.onLike,
    required this.onComment,
    required this.onShare,
  });

  final PostBaseDto item;
  final bool isDark;
  final bool isLiked;
  final int likeCount;
  final AnimationController likeCtrl;
  final VoidCallback onLike;
  final VoidCallback onComment;
  final VoidCallback onShare;

  @override
  Widget build(BuildContext context) {
    final muted = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final likeColor = isLiked ? AppColors.worksLike : muted;

    final likeScale = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.0,
          end: 1.25,
        ).chain(CurveTween(curve: Curves.easeOut)),
        weight: 50,
      ),
      TweenSequenceItem(
        tween: Tween<double>(
          begin: 1.25,
          end: 1.0,
        ).chain(CurveTween(curve: Curves.easeIn)),
        weight: 50,
      ),
    ]).animate(likeCtrl);

    return Row(
      children: [
        Expanded(
          child: _chip(
            context: context,
            selected: isLiked,
            child: ScaleTransition(
              scale: likeScale,
              child: Icon(
                isLiked ? CupertinoIcons.heart_fill : CupertinoIcons.heart,
                size: AppSpacing.iconMedium,
                color: likeColor,
              ),
            ),
            label: formatCompactActionCount(likeCount),
            muted: muted,
            onTap: onLike,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            child: Icon(
              CupertinoIcons.arrowshape_turn_up_right,
              size: AppSpacing.iconMedium,
              color: muted,
            ),
            label: formatCompactActionCount(item.shareCount),
            muted: muted,
            onTap: onShare,
          ),
        ),
        Expanded(
          child: _chip(
            context: context,
            child: Icon(
              CupertinoIcons.chat_bubble,
              size: AppSpacing.iconMedium,
              color: muted,
            ),
            label: formatCompactActionCount(item.commentCount),
            muted: muted,
            onTap: onComment,
          ),
        ),
      ],
    );
  }

  Widget _chip({
    required BuildContext context,
    required Widget child,
    required String label,
    required Color muted,
    required VoidCallback onTap,
    bool selected = false,
  }) {
    final foreground = selected ? AppColors.worksLike : muted;

    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.minInteractiveSize,
      ),
      onPressed: onTap,
      child: Container(
        height: AppSpacing.buttonHeightSm,
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            child,
            SizedBox(width: AppSpacing.intraGroupXs),
            Text(
              label,
              maxLines: 1,
              overflow: TextOverflow.fade,
              softWrap: false,
              style: TextStyle(
                fontSize: AppTypography.iosFootnote,
                color: foreground,
                fontWeight: AppTypography.medium,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
