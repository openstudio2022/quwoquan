part of 'comment_provider.dart';

// CommentNotifier 的纯函数辅助（一/二级回复树乐观增改删、置顶前移、反应位运算、
// 排序参数映射）。均为无状态纯函数（输入即输出），与主文件同库（part）便于复用与单测，
// 不引入第二数据源（R24/R25）。

String _sortParam(CommentSortMode mode) {
  switch (mode) {
    case CommentSortMode.recommended:
      return 'recommended';
    case CommentSortMode.latest:
      return 'latest';
    case CommentSortMode.mostLiked:
      return 'most_liked';
  }
}

List<CommentDto> _appendReplyToParent(
  List<CommentDto> comments, {
  required String parentCommentId,
  required CommentDto reply,
}) {
  return comments
      .map(
        (comment) => comment.id == parentCommentId
            ? comment.copyWith(
                replyCount: comment.replyCount + 1,
                replyPreview: [...comment.replyPreview, reply],
              )
            : comment,
      )
      .toList(growable: false);
}

List<CommentDto> _replaceReplyInParent(
  List<CommentDto> comments, {
  required String parentCommentId,
  required String pendingReplyId,
  required CommentDto confirmed,
}) {
  return comments
      .map(
        (comment) => comment.id == parentCommentId
            ? comment.copyWith(
                replyPreview: comment.replyPreview
                    .map(
                      (reply) =>
                          reply.id == pendingReplyId ? confirmed : reply,
                    )
                    .toList(growable: false),
              )
            : comment,
      )
      .toList(growable: false);
}

List<CommentDto> _removeReplyFromParent(
  List<CommentDto> comments, {
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
List<CommentDto> _withPinnedFirst(List<CommentDto> comments) {
  final pinned = comments.where((c) => c.isPinned).toList(growable: false);
  final rest = comments.where((c) => !c.isPinned).toList(growable: false);
  return <CommentDto>[...pinned, ...rest];
}

CommentDto _applyReaction(CommentDto comment, String reaction) {
  var likeCount = comment.likeCount;
  var dislikeCount = comment.dislikeCount;
  if (comment.viewerReaction == 'like') {
    likeCount = (likeCount - 1).clamp(0, 1 << 31).toInt();
  }
  if (comment.viewerReaction == 'dislike') {
    dislikeCount = (dislikeCount - 1).clamp(0, 1 << 31).toInt();
  }
  if (reaction == 'like') likeCount++;
  if (reaction == 'dislike') dislikeCount++;
  return comment.copyWith(
    likeCount: likeCount,
    dislikeCount: dislikeCount,
    viewerReaction: reaction,
  );
}
