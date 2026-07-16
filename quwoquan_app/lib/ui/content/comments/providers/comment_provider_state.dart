part of 'comment_provider.dart';

enum CommentListStatus { idle, loading, loadingMore, error }

class CommentState {
  final List<ContentCommentListItem> comments;
  final String? nextCursor;
  final int totalCount;
  final int sessionLoadVersion;
  final CommentListStatus status;
  final RuntimeFailureBase? failure;
  final RuntimeFailureBase? appendFailure;
  final int replyPreviewCount;
  final int replyFirstExpandPageSize;
  final int replyExpandPageSize;

  /// 长评论折叠阈值（超过该行数折叠并显示「展开全文」）。
  final int foldLineCount;
  final Set<String> loadingReplyCommentIds;

  /// 当前处于「展开回复」显示态的一级评论 id 集合（用于驱动
  /// 「展开 N 条回复 → 展开更多回复 → 收起」的三段标签切换）。
  final Set<String> expandedReplyCommentIds;

  const CommentState({
    this.comments = const [],
    this.nextCursor,
    this.totalCount = 0,
    this.sessionLoadVersion = 0,
    this.status = CommentListStatus.idle,
    this.failure,
    this.appendFailure,
    this.replyPreviewCount = 1,
    this.replyFirstExpandPageSize = 5,
    this.replyExpandPageSize = 10,
    this.foldLineCount = 3,
    this.loadingReplyCommentIds = const {},
    this.expandedReplyCommentIds = const {},
  });

  bool get hasMore => nextCursor != null;
  bool get isLoading => status == CommentListStatus.loading;

  CommentState copyWith({
    List<ContentCommentListItem>? comments,
    String? Function()? nextCursor,
    int? totalCount,
    int? sessionLoadVersion,
    CommentListStatus? status,
    RuntimeFailureBase? Function()? failure,
    RuntimeFailureBase? Function()? appendFailure,
    int? replyPreviewCount,
    int? replyFirstExpandPageSize,
    int? replyExpandPageSize,
    int? foldLineCount,
    Set<String>? loadingReplyCommentIds,
    Set<String>? expandedReplyCommentIds,
  }) {
    return CommentState(
      comments: comments ?? this.comments,
      nextCursor: nextCursor != null ? nextCursor() : this.nextCursor,
      totalCount: totalCount ?? this.totalCount,
      sessionLoadVersion: sessionLoadVersion ?? this.sessionLoadVersion,
      status: status ?? this.status,
      failure: failure != null ? failure() : this.failure,
      appendFailure: appendFailure != null
          ? appendFailure()
          : this.appendFailure,
      replyPreviewCount: replyPreviewCount ?? this.replyPreviewCount,
      replyFirstExpandPageSize:
          replyFirstExpandPageSize ?? this.replyFirstExpandPageSize,
      replyExpandPageSize: replyExpandPageSize ?? this.replyExpandPageSize,
      foldLineCount: foldLineCount ?? this.foldLineCount,
      loadingReplyCommentIds:
          loadingReplyCommentIds ?? this.loadingReplyCommentIds,
      expandedReplyCommentIds:
          expandedReplyCommentIds ?? this.expandedReplyCommentIds,
    );
  }
}
