part of 'comment_provider.dart';

enum CommentSortMode { recommended, latest, mostLiked }

enum CommentListStatus { idle, loading, loadingMore, error }

class CommentState {
  final List<CommentDto> comments;
  final String? nextCursor;
  final int totalCount;
  final int sessionLoadVersion;
  final CommentSortMode sortMode;
  final CommentListStatus status;
  final String? errorMessage;
  final Object? rawError;
  final Object? appendError;
  final List<CommentDto> pendingComments;
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
    this.sortMode = CommentSortMode.recommended,
    this.status = CommentListStatus.idle,
    this.errorMessage,
    this.rawError,
    this.appendError,
    this.pendingComments = const [],
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
    List<CommentDto>? comments,
    String? Function()? nextCursor,
    int? totalCount,
    int? sessionLoadVersion,
    CommentSortMode? sortMode,
    CommentListStatus? status,
    String? Function()? errorMessage,
    Object? Function()? rawError,
    Object? Function()? appendError,
    List<CommentDto>? pendingComments,
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
      sortMode: sortMode ?? this.sortMode,
      status: status ?? this.status,
      errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
      rawError: rawError != null ? rawError() : this.rawError,
      appendError: appendError != null ? appendError() : this.appendError,
      pendingComments: pendingComments ?? this.pendingComments,
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
