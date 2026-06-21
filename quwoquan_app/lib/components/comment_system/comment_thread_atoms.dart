part of 'comment_thread_view.dart';

// 评论原子组件：可展开长文本、图片附件、动作行、赞踩 gutter、徽标、相对时间。
// 与 comment_thread_view.dart 同库（part），拆出仅为收敛主文件行数（R03/R24）。

/// 长评论折叠：超过 [maxLines] 行时折叠并显示「展开全文 / 收起」。
class _ExpandableCommentText extends StatefulWidget {
  const _ExpandableCommentText({
    required this.text,
    required this.maxLines,
    required this.isDark,
    this.onTap,
  });

  final String text;
  final int maxLines;
  final bool isDark;
  final VoidCallback? onTap;

  @override
  State<_ExpandableCommentText> createState() => _ExpandableCommentTextState();
}

class _ExpandableCommentTextState extends State<_ExpandableCommentText> {
  bool _expanded = false;
  TapGestureRecognizer? _toggleRecognizer;

  @override
  void dispose() {
    _toggleRecognizer?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final textStyle = TextStyle(
      fontSize: AppTypography.base,
      height: AppTypography.lineHeightRelaxed,
      color: AppColorsFunctional.getColor(
        widget.isDark,
        ColorType.foregroundPrimary,
      ),
    );
    return LayoutBuilder(
      builder: (context, constraints) {
        final painter = TextPainter(
          text: TextSpan(text: widget.text, style: textStyle),
          maxLines: widget.maxLines,
          textDirection: Directionality.of(context),
        )..layout(maxWidth: constraints.maxWidth);
        final isOverflowing = painter.didExceedMaxLines;
        if (!isOverflowing) {
          return GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: widget.onTap,
            child: Text(widget.text, style: textStyle),
          );
        }
        _toggleRecognizer?.dispose();
        _toggleRecognizer = TapGestureRecognizer()
          ..onTap = () => setState(() => _expanded = !_expanded);
        final actionStyle = TextStyle(
          fontSize: AppTypography.xs,
          color: AppColors.primaryColor,
          fontWeight: AppTypography.medium,
        );
        if (_expanded) {
          return Text.rich(
            TextSpan(
              children: [
                TextSpan(text: widget.text, style: textStyle),
                TextSpan(
                  text: ' ${context.l10n.collapseReplies}',
                  style: actionStyle,
                  recognizer: _toggleRecognizer,
                ),
              ],
            ),
          );
        }
        final suffix = '...${context.l10n.expandFullText}';
        final collapsed = _truncateForInlineAction(
          context: context,
          maxWidth: constraints.maxWidth,
          textStyle: textStyle,
          actionStyle: actionStyle,
          suffix: suffix,
        );
        return GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: widget.onTap ?? () => setState(() => _expanded = !_expanded),
          child: Text.rich(
            TextSpan(
              children: [
                TextSpan(text: collapsed, style: textStyle),
                TextSpan(
                  text: suffix,
                  style: actionStyle,
                  recognizer: widget.onTap == null ? null : _toggleRecognizer,
                ),
              ],
            ),
            maxLines: widget.maxLines,
            overflow: TextOverflow.clip,
          ),
        );
      },
    );
  }

  String _truncateForInlineAction({
    required BuildContext context,
    required double maxWidth,
    required TextStyle textStyle,
    required TextStyle actionStyle,
    required String suffix,
  }) {
    final direction = Directionality.of(context);
    var low = 0;
    var high = widget.text.characters.length;
    var best = '';
    while (low <= high) {
      final mid = (low + high) >> 1;
      final candidate = widget.text.characters.take(mid).toString().trimRight();
      final painter = TextPainter(
        text: TextSpan(
          children: [
            TextSpan(text: candidate, style: textStyle),
            TextSpan(text: suffix, style: actionStyle),
          ],
        ),
        maxLines: widget.maxLines,
        textDirection: direction,
      )..layout(maxWidth: maxWidth);
      if (painter.didExceedMaxLines) {
        high = mid - 1;
      } else {
        best = candidate;
        low = mid + 1;
      }
    }
    return best;
  }
}

/// 评论图片附件展示：按宽高比护栏布局，异常宽高比与内容图统一处理。
class _CommentAttachments extends StatelessWidget {
  const _CommentAttachments({
    required this.attachments,
    required this.isDark,
    this.compact = false,
  });

  final List<CommentAttachmentDto> attachments;
  final bool isDark;
  final bool compact;

  @override
  Widget build(BuildContext context) {
    final maxWidth = compact
        ? AppSpacing.commentReplyImageMaxWidth
        : AppSpacing.commentImageMaxWidth;
    return Wrap(
      spacing: AppSpacing.xs,
      runSpacing: AppSpacing.xs,
      children: attachments
          .take(1)
          .map((attachment) {
            final thumbnailUrl = attachment.displayUrl;
            final aspectRatio = clampDisplayAspectRatioValue(
              attachment.aspectRatio,
            );
            return ConstrainedBox(
              constraints: BoxConstraints(maxWidth: maxWidth),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(
                  AppSpacing.smallBorderRadius,
                ),
                child: AspectRatio(
                  aspectRatio: aspectRatio,
                  child: ColoredBox(
                    color: AppColors.primaryColor.withValues(alpha: 0.06),
                    child: thumbnailUrl == null || thumbnailUrl.isEmpty
                        ? const Center(child: Icon(CupertinoIcons.photo))
                        : AppCachedNetworkImage(
                            imageUrl: thumbnailUrl,
                            fit: BoxFit.cover,
                            cdnPreset: CdnImagePreset.thumbnail,
                            errorWidget: const Center(
                              child: Icon(CupertinoIcons.photo),
                            ),
                          ),
                  ),
                ),
              ),
            );
          })
          .toList(growable: false),
    );
  }
}

class _ReplyPreviewItem extends ConsumerWidget {
  const _ReplyPreviewItem({
    required this.postId,
    required this.reply,
    required this.isDark,
    this.highlighted = false,
    this.onReplySelected,
  });

  final String postId;
  final CommentDto reply;
  final bool isDark;
  final bool highlighted;
  final ValueChanged<CommentDto>? onReplySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final ip = (reply.ipLocation ?? '').trim();
    final canReplyToReply = reply.canReply && !reply.canDelete;
    final body = Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: canReplyToReply ? () => onReplySelected?.call(reply) : null,
          child: RoundedSquareAvatar(
            size: AppSpacing.commentReplyAvatarSize,
            imageUrl: reply.avatarUrl,
            name: reply.displayName,
            borderRadius: AppSpacing.commentReplyAvatarSize / 2,
            backgroundColor: AppColorsFunctional.getColor(
              isDark,
              ColorType.backgroundSecondary,
            ),
            fallbackIcon: CupertinoIcons.person_fill,
          ),
        ),
        SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: canReplyToReply
                    ? () => onReplySelected?.call(reply)
                    : null,
                // 引用昵称浅色弱化、正文主色，名字与正文同段（TextSpan）。
                child: Text.rich(
                  TextSpan(
                    children: [
                      TextSpan(
                        text: reply.displayName ?? reply.authorId,
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundSecondary,
                          ),
                        ),
                      ),
                      TextSpan(
                        text: '：',
                        style: TextStyle(
                          fontSize: AppTypography.sm,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundTertiary,
                          ),
                        ),
                      ),
                      ..._replyTargetSpans(isDark, reply),
                      TextSpan(
                        text: reply.content,
                        style: TextStyle(
                          fontSize: AppTypography.base,
                          height: AppTypography.lineHeightRelaxed,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundPrimary,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              if (reply.attachments.isNotEmpty) ...[
                SizedBox(height: AppSpacing.xs),
                _CommentAttachments(
                  attachments: reply.attachments,
                  isDark: isDark,
                  compact: true,
                ),
              ],
              SizedBox(height: AppSpacing.xs),
              Row(
                children: [
                  Text(
                    formatCommentRelativeTime(context, reply.createdAt),
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundTertiary,
                      ),
                    ),
                  ),
                  if (ip.isNotEmpty) ...[
                    SizedBox(width: AppSpacing.sm),
                    Text(
                      ip,
                      style: TextStyle(
                        fontSize: AppTypography.xs,
                        color: AppColorsFunctional.getColor(
                          isDark,
                          ColorType.foregroundTertiary,
                        ),
                      ),
                    ),
                  ],
                  if (reply.canReply) ...[
                    SizedBox(width: AppSpacing.md),
                    GestureDetector(
                      onTap: canReplyToReply
                          ? () => onReplySelected?.call(reply)
                          : null,
                      child: Text(
                        UITextConstants.replyAction,
                        style: TextStyle(
                          fontSize: AppTypography.xs,
                          color: AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundSecondary,
                          ),
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ],
          ),
        ),
        SizedBox(width: AppSpacing.xs),
        _CommentReactionGroup(
          likeSelected: reply.viewerReaction == 'like',
          dislikeSelected: reply.viewerReaction == 'dislike',
          likeCount: reply.likeCount,
          dislikeCount: reply.dislikeCount,
          onLike: () => ref
              .read(commentProviderFamily(postId).notifier)
              .toggleLike(reply.id),
          onDislike: () => ref
              .read(commentProviderFamily(postId).notifier)
              .toggleDislike(reply.id),
        ),
      ],
    );
    return AnimatedContainer(
      key: highlighted ? TestKeys.commentHighlightedReply : null,
      duration: const Duration(milliseconds: 300),
      curve: Curves.easeOut,
      padding: EdgeInsets.symmetric(
        horizontal: highlighted ? AppSpacing.xs : 0,
        vertical: highlighted ? AppSpacing.xs : 0,
      ),
      decoration: BoxDecoration(
        color: highlighted
            ? AppColors.primaryColor.withValues(alpha: 0.10)
            : AppColors.transparent,
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: body,
    );
  }

  List<InlineSpan> _replyTargetSpans(bool isDark, CommentDto reply) {
    final targetName = reply.replyToDisplayName?.trim();
    final isReplyingToNested =
        (reply.replyToCommentId?.trim().isNotEmpty ?? false) &&
        reply.replyToCommentId != reply.parentCommentId;
    if (!isReplyingToNested || targetName == null || targetName.isEmpty) {
      return const <InlineSpan>[];
    }
    return <InlineSpan>[
      TextSpan(
        text: '${UITextConstants.replyAction} @$targetName ',
        style: TextStyle(
          fontSize: AppTypography.sm,
          color: AppColorsFunctional.getColor(
            isDark,
            ColorType.foregroundTertiary,
          ),
        ),
      ),
    ];
  }
}

class _CommentActions extends StatelessWidget {
  const _CommentActions({
    required this.comment,
    required this.isDark,
    this.onReply,
    this.onDelete,
    this.onPin,
  });

  final CommentDto comment;
  final bool isDark;
  final VoidCallback? onReply;
  final VoidCallback? onDelete;
  final VoidCallback? onPin;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Text(
          _formatTime(context, comment.createdAt),
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundTertiary,
            ),
          ),
        ),
        if ((comment.ipLocation ?? '').trim().isNotEmpty) ...[
          SizedBox(width: AppSpacing.sm),
          Text(
            comment.ipLocation!.trim(),
            style: TextStyle(
              fontSize: AppTypography.xs,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
            ),
          ),
        ],
        if (onReply != null) ...[
          SizedBox(width: AppSpacing.md),
          GestureDetector(
            onTap: onReply,
            child: Text(
              UITextConstants.replyAction,
              style: TextStyle(
                fontSize: AppTypography.xs,
                color: AppColorsFunctional.getColor(
                  isDark,
                  ColorType.foregroundSecondary,
                ),
              ),
            ),
          ),
        ],
        const Spacer(),
        if (onPin != null) ...[
          GestureDetector(
            onTap: onPin,
            child: Icon(
              comment.isPinned ? CupertinoIcons.pin_fill : CupertinoIcons.pin,
              size: AppSpacing.iconSmall,
              color: comment.isPinned
                  ? AppColors.primaryColor
                  : AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundTertiary,
                    ),
            ),
          ),
          SizedBox(width: AppSpacing.sm),
        ],
        if (onDelete != null) ...[
          GestureDetector(
            onTap: onDelete,
            child: Icon(
              CupertinoIcons.trash,
              size: AppSpacing.iconSmall,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundTertiary,
              ),
            ),
          ),
          SizedBox(width: AppSpacing.sm),
        ],
      ],
    );
  }

  String _formatTime(BuildContext context, DateTime time) =>
      formatCommentRelativeTime(context, time);
}

/// 评论相对时间格式化（一级评论与二级回复共用，统一时间语义）。
String formatCommentRelativeTime(BuildContext context, DateTime time) {
  final l10n = context.l10n;
  final diff = DateTime.now().difference(time);
  if (diff.inMinutes < 1) return l10n.justNow;
  if (diff.inHours < 1) return l10n.minutesAgoTemplate(diff.inMinutes);
  if (diff.inDays < 1) return l10n.hoursAgoTemplate(diff.inHours);
  if (diff.inDays < 30) return l10n.daysAgoTemplate(diff.inDays);
  return l10n.monthDayTemplate(time.month, time.day);
}

class _CommentReactionGroup extends StatelessWidget {
  const _CommentReactionGroup({
    required this.likeSelected,
    required this.dislikeSelected,
    required this.likeCount,
    required this.dislikeCount,
    required this.onLike,
    required this.onDislike,
  });

  final bool likeSelected;
  final bool dislikeSelected;
  final int likeCount;
  final int dislikeCount;
  final VoidCallback onLike;
  final VoidCallback onDislike;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.commentReactionGroupWidth,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _ReactionIconButton(
            selected: likeSelected,
            icon: CupertinoIcons.heart,
            selectedIcon: CupertinoIcons.heart_fill,
            count: likeCount,
            onTap: onLike,
          ),
          SizedBox(width: AppSpacing.commentReactionActionGap),
          _ReactionIconButton(
            selected: dislikeSelected,
            icon: CupertinoIcons.hand_thumbsdown,
            selectedIcon: CupertinoIcons.hand_thumbsdown_fill,
            count: dislikeCount,
            onTap: onDislike,
          ),
        ],
      ),
    );
  }
}

class _ReactionIconButton extends StatelessWidget {
  const _ReactionIconButton({
    required this.selected,
    required this.icon,
    required this.selectedIcon,
    required this.count,
    required this.onTap,
  });

  final bool selected;
  final IconData icon;
  final IconData selectedIcon;
  final int count;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = selected
        ? AppColors.error
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary);
    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: SizedBox(
        width: AppSpacing.commentReactionColumnWidth,
        // 计数置于图标左侧定宽右对齐：数字宽度变化只向左扩展，
        // 图标恒定贴按钮右缘，确保一级/二级赞踩图标右对齐且上下对齐。
        child: Row(
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            SizedBox(
              width: AppSpacing.commentReactionCountWidth,
              child: Text(
                count > 0 ? formatCompactActionCount(count) : '',
                maxLines: 1,
                overflow: TextOverflow.clip,
                textAlign: TextAlign.right,
                style: TextStyle(
                  fontSize: AppTypography.xs,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
                ),
              ),
            ),
            SizedBox(width: AppSpacing.xs),
            Icon(
              selected ? selectedIcon : icon,
              size: AppSpacing.commentReactionIconSize,
              color: foreground,
            ),
          ],
        ),
      ),
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.label, required this.isDark});

  final String label;
  final bool isDark;

  @override
  Widget build(BuildContext context) {
    // 置顶 / 作者赞过 / 作者徽标统一蓝色主色调强调。
    const accent = AppColors.primaryColor;
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.xs,
        vertical: AppSpacing.one,
      ),
      decoration: BoxDecoration(
        color: accent.withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: AppTypography.xs, color: accent),
      ),
    );
  }
}
