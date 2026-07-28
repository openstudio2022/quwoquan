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

  final List<ContentCommentAttachment> attachments;
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
  final ContentCommentListItem reply;
  final bool isDark;
  final bool highlighted;
  final ValueChanged<ContentCommentListItem>? onReplySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final canReplyToReply = reply.canReply && !reply.canDelete;
    final body = Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          button: true,
          label: ContentText.goToUserProfile,
          child: GestureDetector(
            behavior: HitTestBehavior.opaque,
            onTap: () => _openCommentAuthorProfile(context, reply),
            child: SizedBox.square(
              dimension: AppSpacing.minInteractiveSize,
              child: Center(
                child: RoundedSquareAvatar(
                  size: AppSpacing.commentReplyAvatarSize,
                  imageUrl: reply.authorAvatarUrlSnapshot,
                  name: reply.authorDisplayNameSnapshot,
                  borderRadius: AppSpacing.commentReplyAvatarSize / 2,
                  backgroundColor: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.backgroundSecondary,
                  ),
                  fallbackIcon: CupertinoIcons.person_fill,
                ),
              ),
            ),
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
                        text: reply.authorDisplayNameSnapshot ?? reply.authorId,
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
              Wrap(
                crossAxisAlignment: WrapCrossAlignment.center,
                spacing: AppSpacing.sm,
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
                  if (reply.canReply) ...[
                    Semantics(
                      button: true,
                      child: CupertinoButton(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size.square(
                          AppSpacing.minInteractiveSize,
                        ),
                        onPressed: canReplyToReply
                            ? () => onReplySelected?.call(reply)
                            : null,
                        child: Text(
                          ContentText.replyAction,
                          style: TextStyle(
                            fontSize: AppTypography.xs,
                            color: AppColorsFunctional.getColor(
                              isDark,
                              ColorType.foregroundSecondary,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                  Semantics(
                    button: true,
                    label: ContentText.commentMoreActions,
                    child: CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size.square(
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () => showCommentItemActionsSheet(
                        context,
                        ref,
                        postId: postId,
                        comment: reply,
                      ),
                      child: Icon(
                        CupertinoIcons.ellipsis,
                        size: AppSpacing.iconSmall,
                        color: AppColorsFunctional.getColor(
                          isDark,
                          ColorType.foregroundSecondary,
                        ),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
        SizedBox(width: AppSpacing.xs),
        _CommentReactionGroup(
          likeSelected:
              reply.viewerReaction == ContentCommentReactionValue.like,
          dislikeSelected:
              reply.viewerReaction == ContentCommentReactionValue.dislike,
          showDeleteAction: reply.canDelete,
          likeCount: reply.likeCount,
          dislikeCount: reply.dislikeCount,
          onLike: () => runWhenLoggedIn(ref, context, AuthGateReason.like, () {
            ref
                .read(commentProviderFamily(postId).notifier)
                .toggleLike(reply.id);
          }),
          onDislike: reply.canDelete
              ? null
              : () => runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                  ref
                      .read(commentProviderFamily(postId).notifier)
                      .toggleDislike(reply.id);
                }),
          onDelete: reply.canDelete
              ? () => unawaited(
                  _deleteCommentWithConfirmation(
                    context,
                    ref,
                    postId: postId,
                    commentId: reply.id,
                  ),
                )
              : null,
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
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onLongPress: () => showCommentItemActionsSheet(
          context,
          ref,
          postId: postId,
          comment: reply,
        ),
        child: body,
      ),
    );
  }
}

class _CommentActions extends StatelessWidget {
  const _CommentActions({
    required this.comment,
    required this.isDark,
    required this.onMore,
    this.onReply,
    this.onPin,
  });

  final ContentCommentListItem comment;
  final bool isDark;
  final VoidCallback onMore;
  final VoidCallback? onReply;
  final VoidCallback? onPin;

  @override
  Widget build(BuildContext context) {
    final ipLocation = comment.authorIpLocation?.trim() ?? '';
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          // IP 属地为创建时服务端快照；解析不出为空则只显示时间，绝不臆造。
          ipLocation.isEmpty
              ? _formatTime(context, comment.createdAt)
              : '${_formatTime(context, comment.createdAt)}'
                    ' ${ContentText.commentIpLocationPrefix}$ipLocation',
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: AppColorsFunctional.getColor(
              isDark,
              ColorType.foregroundTertiary,
            ),
          ),
        ),
        Wrap(
          spacing: AppSpacing.xs,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            if (onReply != null)
              Semantics(
                button: true,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size.square(AppSpacing.minInteractiveSize),
                  onPressed: onReply,
                  child: Text(
                    ContentText.replyAction,
                    style: TextStyle(
                      fontSize: AppTypography.xs,
                      color: AppColorsFunctional.getColor(
                        isDark,
                        ColorType.foregroundSecondary,
                      ),
                    ),
                  ),
                ),
              ),
            if (onPin != null)
              Semantics(
                button: true,
                selected: comment.isPinned,
                label: comment.isPinned
                    ? ContentText.commentUnpinAction
                    : ContentText.commentPinAction,
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: const Size.square(AppSpacing.minInteractiveSize),
                  onPressed: onPin,
                  child: Icon(
                    comment.isPinned
                        ? CupertinoIcons.pin_fill
                        : CupertinoIcons.pin,
                    size: AppSpacing.iconSmall,
                    color: comment.isPinned
                        ? AppColors.primaryColor
                        : AppColorsFunctional.getColor(
                            isDark,
                            ColorType.foregroundTertiary,
                          ),
                  ),
                ),
              ),
            Semantics(
              button: true,
              label: ContentText.commentMoreActions,
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size.square(AppSpacing.minInteractiveSize),
                onPressed: onMore,
                child: Icon(
                  CupertinoIcons.ellipsis,
                  size: AppSpacing.iconSmall,
                  color: AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
                ),
              ),
            ),
          ],
        ),
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
    this.showDeleteAction = false,
    required this.likeCount,
    required this.dislikeCount,
    required this.onLike,
    this.onDislike,
    this.onDelete,
  });

  final bool likeSelected;
  final bool dislikeSelected;
  final bool showDeleteAction;
  final int likeCount;
  final int dislikeCount;
  final VoidCallback onLike;
  final VoidCallback? onDislike;
  final VoidCallback? onDelete;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: AppSpacing.commentReactionGroupWidth,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.end,
        children: [
          _ReactionIconButton(
            selected: likeSelected,
            semanticLabel: FoundationText.like,
            icon: CupertinoIcons.heart,
            selectedIcon: CupertinoIcons.heart_fill,
            count: likeCount,
            onTap: onLike,
          ),
          SizedBox(width: AppSpacing.commentReactionActionGap),
          if (showDeleteAction)
            _ReactionIconButton(
              selected: false,
              semanticLabel: ContentText.commentDeleteAction,
              icon: CupertinoIcons.trash,
              selectedIcon: CupertinoIcons.trash,
              reserveCountSlot: true,
              onTap: onDelete,
            )
          else
            _ReactionIconButton(
              selected: dislikeSelected,
              semanticLabel: ContentText.commentDislike,
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
    required this.semanticLabel,
    required this.icon,
    required this.selectedIcon,
    this.count = 0,
    this.reserveCountSlot = true,
    this.onTap,
  });

  final bool selected;
  final String semanticLabel;
  final IconData icon;
  final IconData selectedIcon;
  final int count;
  final bool reserveCountSlot;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final foreground = selected
        ? AppColors.error
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundTertiary);
    return Semantics(
      button: true,
      selected: selected,
      label: semanticLabel,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: const Size(
          AppSpacing.commentReactionColumnWidth,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: onTap,
        child: SizedBox(
          width: AppSpacing.commentReactionColumnWidth,
          height: AppSpacing.minInteractiveSize,
          // 计数置于图标左侧定宽右对齐：数字宽度变化只向左扩展，
          // 图标恒定贴按钮右缘，确保一级/二级赞踩图标右对齐且上下对齐。
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (reserveCountSlot)
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
      ),
    );
  }
}

/// 一级评论排序切换（热门/最新）：切换只重新请求服务端，禁止本地重排。
/// 选中态只用颜色与字重微差表达（几何稳定，无位移跳变）。
class _CommentSortSwitcher extends StatelessWidget {
  const _CommentSortSwitcher({
    required this.sort,
    required this.isDark,
    required this.onChanged,
  });

  final ContentCommentSort sort;
  final bool isDark;
  final ValueChanged<ContentCommentSort> onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.sm),
      child: Row(
        children: [
          _sortOption(
            label: ContentText.commentSortHot,
            selected: sort == ContentCommentSort.hot,
            onTap: () => onChanged(ContentCommentSort.hot),
          ),
          SizedBox(width: AppSpacing.md),
          _sortOption(
            label: ContentText.commentSortLatest,
            selected: sort == ContentCommentSort.latest,
            onTap: () => onChanged(ContentCommentSort.latest),
          ),
        ],
      ),
    );
  }

  Widget _sortOption({
    required String label,
    required bool selected,
    required VoidCallback onTap,
  }) {
    return Semantics(
      button: true,
      selected: selected,
      label: label,
      child: CupertinoButton(
        padding: EdgeInsets.symmetric(horizontal: AppSpacing.xs),
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        onPressed: selected ? null : onTap,
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.xs,
            fontWeight: selected ? AppTypography.medium : AppTypography.regular,
            color: selected
                ? AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundPrimary,
                  )
                : AppColorsFunctional.getColor(
                    isDark,
                    ColorType.foregroundTertiary,
                  ),
          ),
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
