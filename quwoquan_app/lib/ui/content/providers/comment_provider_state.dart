part of 'comment_provider.dart';

enum CommentSortMode { recommended, latest, mostLiked }

enum CommentListStatus { idle, loading, loadingMore, error }

class CommentState {
  final List<CommentDto> comments;
  final String? nextCursor;
  final int totalCount;
  final CommentSortMode sortMode;
  final CommentListStatus status;
  final String? errorMessage;
  final Object? rawError;
  final Object? appendError;
  final Object? refreshError;
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
  final bool hasNewComments;
  final bool isRefreshing;

  /// 进入评论详情时记录的基线 watermark（首次 delta 首同步返回值）。
  /// 后续 poll/refresh 以它作为半开区间下界，向用户解释「较进入时的增量」。
  final DateTime? baselineWatermark;

  /// 最近一次相对 [baselineWatermark] 的可解释增量（新增 N / 删除 M）。
  /// 仅在存在变化时驱动「有新评论」通知位展示解释；展示并刷新后清空。
  final CommentCountsDelta? countsDelta;

  const CommentState({
    this.comments = const [],
    this.nextCursor,
    this.totalCount = 0,
    this.sortMode = CommentSortMode.recommended,
    this.status = CommentListStatus.idle,
    this.errorMessage,
    this.rawError,
    this.appendError,
    this.refreshError,
    this.pendingComments = const [],
    this.replyPreviewCount = 1,
    this.replyFirstExpandPageSize = 5,
    this.replyExpandPageSize = 10,
    this.foldLineCount = 3,
    this.loadingReplyCommentIds = const {},
    this.expandedReplyCommentIds = const {},
    this.hasNewComments = false,
    this.isRefreshing = false,
    this.baselineWatermark,
    this.countsDelta,
  });

  bool get hasMore => nextCursor != null;
  bool get isLoading => status == CommentListStatus.loading;

  /// 是否存在可向用户解释的计数变化（新增或删除任一非零）。
  bool get hasCountsDeltaExplanation => countsDelta?.hasChanges ?? false;

  CommentState copyWith({
    List<CommentDto>? comments,
    String? Function()? nextCursor,
    int? totalCount,
    CommentSortMode? sortMode,
    CommentListStatus? status,
    String? Function()? errorMessage,
    Object? Function()? rawError,
    Object? Function()? appendError,
    Object? Function()? refreshError,
    List<CommentDto>? pendingComments,
    int? replyPreviewCount,
    int? replyFirstExpandPageSize,
    int? replyExpandPageSize,
    int? foldLineCount,
    Set<String>? loadingReplyCommentIds,
    Set<String>? expandedReplyCommentIds,
    bool? hasNewComments,
    bool? isRefreshing,
    DateTime? Function()? baselineWatermark,
    CommentCountsDelta? Function()? countsDelta,
  }) {
    return CommentState(
      comments: comments ?? this.comments,
      nextCursor: nextCursor != null ? nextCursor() : this.nextCursor,
      totalCount: totalCount ?? this.totalCount,
      sortMode: sortMode ?? this.sortMode,
      status: status ?? this.status,
      errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
      rawError: rawError != null ? rawError() : this.rawError,
      appendError: appendError != null ? appendError() : this.appendError,
      refreshError: refreshError != null ? refreshError() : this.refreshError,
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
      hasNewComments: hasNewComments ?? this.hasNewComments,
      isRefreshing: isRefreshing ?? this.isRefreshing,
      baselineWatermark: baselineWatermark != null
          ? baselineWatermark()
          : this.baselineWatermark,
      countsDelta: countsDelta != null ? countsDelta() : this.countsDelta,
    );
  }
}
