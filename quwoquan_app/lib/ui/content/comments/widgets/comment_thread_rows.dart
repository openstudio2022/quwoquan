part of 'comment_thread_view.dart';

// 评论一级行与二级回复展开控件。与 comment_thread_view.dart 同库（part），
// 复用同一份私有 widget/TestKeys，拆出仅为收敛主文件行数（R03/R24）。

class _CommentThreadItem extends ConsumerWidget {
  const _CommentThreadItem({
    required this.postId,
    required this.comment,
    required this.isDark,
    required this.loadingReplies,
    required this.repliesExpanded,
    required this.replyPreviewCount,
    required this.foldLineCount,
    this.highlighted = false,
    this.highlightedReplyId,
    this.replyItemKeyFor,
    this.onReplySelected,
  });

  final String postId;
  final ContentCommentListItem comment;
  final bool isDark;
  final bool loadingReplies;
  final bool repliesExpanded;
  final int replyPreviewCount;
  final int foldLineCount;
  final bool highlighted;
  final String? highlightedReplyId;
  final GlobalKey Function(String replyId)? replyItemKeyFor;
  final ValueChanged<ContentCommentListItem>? onReplySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            RoundedSquareAvatar(
              size: AppSpacing.commentAvatarSize,
              imageUrl: comment.authorAvatarUrlSnapshot,
              name: comment.authorDisplayNameSnapshot,
              borderRadius: AppSpacing.commentAvatarSize / 2,
              backgroundColor: AppColorsFunctional.getColor(
                isDark,
                ColorType.backgroundSecondary,
              ),
              fallbackIcon: CupertinoIcons.person_fill,
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(child: _buildContent(context, ref)),
            SizedBox(width: AppSpacing.xs),
            _CommentReactionGroup(
              likeSelected:
                  comment.viewerReaction == ContentCommentReactionValue.like,
              dislikeSelected:
                  comment.viewerReaction == ContentCommentReactionValue.dislike,
              showDeleteAction: comment.canDelete,
              likeCount: comment.likeCount,
              dislikeCount: comment.dislikeCount,
              onLike: () =>
                  runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                    ref
                        .read(commentProviderFamily(postId).notifier)
                        .toggleLike(comment.id);
                  }),
              onDislike: comment.canDelete
                  ? null
                  : () =>
                        runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                          ref
                              .read(commentProviderFamily(postId).notifier)
                              .toggleDislike(comment.id);
                        }),
              onDelete: comment.canDelete
                  ? () => ref
                        .read(commentProviderFamily(postId).notifier)
                        .deleteComment(comment.id)
                  : null,
            ),
          ],
        ),
        if (comment.replyPreview.isNotEmpty || comment.replyCount > 0)
          Padding(
            padding: EdgeInsets.only(
              left: AppSpacing.commentAvatarSize + AppSpacing.sm,
              top: AppSpacing.sm,
            ),
            child: _buildReplies(context, ref),
          ),
      ],
    );
    return Padding(
      padding: EdgeInsets.only(bottom: AppSpacing.md),
      // 深链命中态：淡入淡出的高亮底色，引导用户视线落到目标评论。
      child: AnimatedContainer(
        key: highlighted ? TestKeys.commentHighlightedItem : null,
        duration: const Duration(milliseconds: 300),
        curve: Curves.easeOut,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.xs,
          vertical: highlighted ? AppSpacing.xs : 0,
        ),
        decoration: BoxDecoration(
          color: highlighted
              ? AppColors.primaryColor.withValues(alpha: 0.10)
              : AppColors.transparent,
          borderRadius: BorderRadius.circular(AppSpacing.smallBorderRadius),
        ),
        child: body,
      ),
    );
  }

  Widget _buildContent(BuildContext context, WidgetRef ref) {
    final canReplyToComment = comment.canReply && !comment.canDelete;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            if (comment.isPinned) ...[
              _Badge(label: UITextConstants.commentPinnedBadge, isDark: isDark),
              SizedBox(width: AppSpacing.xs),
            ],
            Expanded(
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: canReplyToComment
                    ? () => onReplySelected?.call(comment)
                    : null,
                child: Text(
                  comment.authorDisplayNameSnapshot ?? comment.authorId,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
                    color: AppColorsFunctional.getColor(
                      isDark,
                      ColorType.foregroundSecondary,
                    ),
                    fontWeight: AppTypography.regular,
                  ),
                ),
              ),
            ),
            if (comment.isAuthor)
              _Badge(label: UITextConstants.commentAuthorBadge, isDark: isDark),
          ],
        ),
        SizedBox(height: AppSpacing.xs),
        _ExpandableCommentText(
          text: comment.content,
          maxLines: foldLineCount,
          isDark: isDark,
          onTap: canReplyToComment
              ? () => onReplySelected?.call(comment)
              : null,
        ),
        if (comment.attachments.isNotEmpty) ...[
          SizedBox(height: AppSpacing.xs),
          _CommentAttachments(attachments: comment.attachments, isDark: isDark),
        ],
        SizedBox(height: AppSpacing.xs),
        _CommentActions(
          comment: comment,
          isDark: isDark,
          onReply: canReplyToComment
              ? () => onReplySelected?.call(comment)
              : null,
          onPin: comment.canPin
              ? () => runWhenLoggedIn(ref, context, AuthGateReason.like, () {
                  _togglePin(context, ref, comment);
                })
              : null,
        ),
      ],
    );
  }

  Future<void> _togglePin(
    BuildContext context,
    WidgetRef ref,
    ContentCommentListItem comment,
  ) async {
    final willPin = !comment.isPinned;
    try {
      await ref
          .read(commentProviderFamily(postId).notifier)
          .togglePin(comment.id);
      if (!context.mounted) return;
      AppToast.show(
        context,
        willPin
            ? UITextConstants.commentPinnedToast
            : UITextConstants.commentUnpinnedToast,
      );
    } catch (e) {
      if (!context.mounted) return;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: e,
          category: UiErrorCategory.backgroundAction,
          scope: UiErrorScope.global,
          allowRetry: false,
        ),
      );
    }
  }

  Widget _buildReplies(BuildContext context, WidgetRef ref) {
    final loaded = comment.replyPreview;
    // 展开态显示全部已加载回复；预览态仅显示前 replyPreviewCount 条。
    final visibleCount = repliesExpanded
        ? loaded.length
        : (replyPreviewCount < loaded.length
              ? replyPreviewCount
              : loaded.length);
    final visibleReplies = loaded.take(visibleCount).toList(growable: false);
    final hasMoreOnServer = comment.replyNextCursor != null;
    // 预览态下未展示的总回复数（含服务端未加载部分）。
    final hiddenCount = comment.replyCount - replyPreviewCount;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        ...visibleReplies.map(
          (reply) => Padding(
            key: replyItemKeyFor?.call(reply.id),
            padding: EdgeInsets.only(bottom: AppSpacing.xs),
            child: _ReplyPreviewItem(
              postId: postId,
              reply: reply,
              isDark: isDark,
              highlighted: highlightedReplyId == reply.id,
              onReplySelected: onReplySelected,
            ),
          ),
        ),
        _buildReplyExpandControl(
          context,
          ref,
          hasMoreOnServer: hasMoreOnServer,
          hiddenCount: hiddenCount,
        ),
      ],
    );
  }

  /// 三段式回复展开控件：
  /// - 预览态且仍有未展示回复：`展开 N 条回复`；
  /// - 展开态且服务端仍有更多：`展开更多回复`；
  /// - 展开态且已全部加载（展示数超过预览数）：`收起`。
  Widget _buildReplyExpandControl(
    BuildContext context,
    WidgetRef ref, {
    required bool hasMoreOnServer,
    required int hiddenCount,
  }) {
    final notifier = ref.read(commentProviderFamily(postId).notifier);
    if (loadingReplies) {
      return Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: const CupertinoActivityIndicator(),
      );
    }
    if (!repliesExpanded) {
      if (hiddenCount <= 0) return const SizedBox.shrink();
      return _ReplyControlLabel(
        controlKey: TestKeys.commentReplyExpand,
        label: context.l10n.expandRepliesTemplate(hiddenCount),
        onTap: () => notifier.expandReplies(comment.id),
      );
    }
    if (hasMoreOnServer) {
      return _ReplyControlLabel(
        controlKey: TestKeys.commentReplyExpand,
        label: context.l10n.expandMoreReplies,
        onTap: () => notifier.expandReplies(comment.id),
      );
    }
    if (comment.replyPreview.length > replyPreviewCount) {
      return _ReplyControlLabel(
        controlKey: TestKeys.commentReplyCollapse,
        label: context.l10n.collapseReplies,
        onTap: () => notifier.collapseReplies(comment.id),
      );
    }
    return const SizedBox.shrink();
  }
}

class _ReplyControlLabel extends StatelessWidget {
  const _ReplyControlLabel({
    required this.controlKey,
    required this.label,
    required this.onTap,
  });

  final Key controlKey;
  final String label;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      key: controlKey,
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(vertical: AppSpacing.xs),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.xs,
            color: AppColors.primaryColor,
            fontWeight: AppTypography.medium,
          ),
        ),
      ),
    );
  }
}
