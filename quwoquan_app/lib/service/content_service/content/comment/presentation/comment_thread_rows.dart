part of 'comment_thread_view.dart';

// 评论一级行与二级回复展开控件。与 comment_thread_view.dart 同库（part），
// 复用同一份私有 widget/TestKeys，拆出仅为收敛主文件行数（R03/R24）。

/// 评论头像点击进入作者主页：携带评论快照作乐观首屏，
/// referralSource 归因链由路由侧 authorProfile 语义承载。
void _openCommentAuthorProfile(BuildContext context, CommentViewData comment) {
  final authorId = comment.authorId.trim();
  if (authorId.isEmpty) return;
  context.push(
    AppRoutePaths.userProfile(userHandle: authorId),
    extra: UserProfileRouteExtra(
      personaId: authorId,
      avatarUrl: comment.authorAvatarUrlSnapshot,
      displayName: comment.authorDisplayNameSnapshot,
    ),
  );
}

Future<void> _deleteCommentWithConfirmation(
  BuildContext context,
  WidgetRef ref, {
  required String postId,
  required String commentId,
}) async {
  final confirmed = await _confirmCommentDelete(context);
  if (!confirmed || !context.mounted) return;
  await ref
      .read(commentProviderFamily(postId).notifier)
      .deleteComment(commentId);
}

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
  final CommentViewData comment;
  final bool isDark;
  final bool loadingReplies;
  final bool repliesExpanded;
  final int replyPreviewCount;
  final int foldLineCount;
  final bool highlighted;
  final String? highlightedReplyId;
  final GlobalKey Function(String replyId)? replyItemKeyFor;
  final ValueChanged<CommentViewData>? onReplySelected;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final body = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Semantics(
              button: true,
              label: ContentText.goToUserProfile,
              child: GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => _openCommentAuthorProfile(context, comment),
                child: SizedBox.square(
                  dimension: AppSpacing.minInteractiveSize,
                  child: Center(
                    child: RoundedSquareAvatar(
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
                  ),
                ),
              ),
            ),
            SizedBox(width: AppSpacing.sm),
            Expanded(child: _buildContent(context, ref)),
            SizedBox(width: AppSpacing.xs),
            _CommentReactionGroup(
              likeSelected: comment.viewerReaction == CommentReactionType.like,
              dislikeSelected:
                  comment.viewerReaction == CommentReactionType.dislike,
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
                  ? () => unawaited(
                      _deleteCommentWithConfirmation(
                        context,
                        ref,
                        postId: postId,
                        commentId: comment.id,
                      ),
                    )
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
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onLongPress: () => showCommentItemActionsSheet(
            context,
            ref,
            postId: postId,
            comment: comment,
          ),
          child: body,
        ),
      ),
    );
  }

  Widget _buildContent(BuildContext context, WidgetRef ref) {
    final canReplyToComment = comment.canReply && !comment.canDelete;
    // 交集关系标签：只渲染服务端事实投影（关注/互关），无事实不显示。
    final relationBadge = switch (comment.viewerRelation) {
      CommentViewerRelation.friend => ContentText.commentRelationFriendBadge,
      CommentViewerRelation.following =>
        ContentText.commentRelationFollowingBadge,
      CommentViewerRelation.none => null,
    };
    final hasBadges =
        comment.isPinned ||
        relationBadge != null ||
        comment.authorLiked ||
        comment.isAuthor;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        GestureDetector(
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
        if (hasBadges) ...[
          SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.xs,
            runSpacing: AppSpacing.xs,
            children: [
              if (comment.isPinned)
                _Badge(label: ContentText.commentPinnedBadge, isDark: isDark),
              if (relationBadge != null)
                _Badge(label: relationBadge, isDark: isDark),
              if (comment.authorLiked)
                _Badge(
                  label: ContentText.commentAuthorLikedBadge,
                  isDark: isDark,
                ),
              if (comment.isAuthor)
                _Badge(label: ContentText.commentAuthorBadge, isDark: isDark),
            ],
          ),
        ],
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
          onMore: () => showCommentItemActionsSheet(
            context,
            ref,
            postId: postId,
            comment: comment,
          ),
        ),
      ],
    );
  }

  Future<void> _togglePin(
    BuildContext context,
    WidgetRef ref,
    CommentViewData comment,
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
            ? ContentText.commentPinnedToast
            : ContentText.commentUnpinnedToast,
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
        child: AppRequestFeedback.inline(),
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
    return Semantics(
      button: true,
      child: CupertinoButton(
        key: controlKey,
        padding: EdgeInsets.zero,
        minimumSize: const Size(
          AppSpacing.minInteractiveSize,
          AppSpacing.minInteractiveSize,
        ),
        alignment: AlignmentDirectional.centerStart,
        onPressed: onTap,
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
