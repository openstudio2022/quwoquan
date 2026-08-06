part of 'comment_provider.dart';

// CommentNotifier 的纯函数辅助：删除回复、置顶前移和反应计数。

List<CommentViewData> _removeReplyFromParent(
  List<CommentViewData> comments, {
  required String parentCommentId,
  required String replyId,
}) {
  return comments
      .map((comment) {
        if (comment.id != parentCommentId) return comment;
        final nextReplies = comment.replyPreview
            .where((reply) => reply.id != replyId)
            .toList(growable: false);
        final removed = nextReplies.length != comment.replyPreview.length;
        return comment.copyWith(
          replyCount: removed
              ? (comment.replyCount - 1).clamp(0, 1 << 31).toInt()
              : comment.replyCount,
          replyPreview: nextReplies,
        );
      })
      .toList(growable: false);
}

/// 把置顶的一级评论移到列表最前（保持其余评论相对顺序），与云侧排序一致。
List<CommentViewData> _withPinnedFirst(List<CommentViewData> comments) {
  final pinned = comments.where((c) => c.isPinned).toList(growable: false);
  final rest = comments.where((c) => !c.isPinned).toList(growable: false);
  return <CommentViewData>[...pinned, ...rest];
}

List<CommentViewData> _replaceCommentInTree(
  List<CommentViewData> comments,
  CommentViewData updated,
) {
  return comments
      .map((comment) {
        if (comment.id == updated.id) return updated;
        final replies = comment.replyPreview
            .map((reply) => reply.id == updated.id ? updated : reply)
            .toList(growable: false);
        return comment.copyWith(replyPreview: replies);
      })
      .toList(growable: false);
}

CommentViewData _applyReaction(
  CommentViewData comment,
  CommentReactionType reaction,
) {
  var likeCount = comment.likeCount;
  var dislikeCount = comment.dislikeCount;
  if (comment.viewerReaction == CommentReactionType.like) {
    likeCount = (likeCount - 1).clamp(0, 1 << 31).toInt();
  }
  if (comment.viewerReaction == CommentReactionType.dislike) {
    dislikeCount = (dislikeCount - 1).clamp(0, 1 << 31).toInt();
  }
  if (reaction == CommentReactionType.like) likeCount++;
  if (reaction == CommentReactionType.dislike) dislikeCount++;
  return comment.copyWith(
    likeCount: likeCount,
    dislikeCount: dislikeCount,
    viewerReaction: reaction,
  );
}
