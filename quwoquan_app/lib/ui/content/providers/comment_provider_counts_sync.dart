part of 'comment_provider.dart';

/// CommentNotifier 的公共辅助能力：耗时埋点 + 权威评论总数同步。
/// 与主文件同库（part），通过抽象 hook 复用主类的 [postId] / [_observability]，
/// 不构成第二数据源（R24/R25）。
mixin _CommentCountsSyncMixin on Notifier<CommentState> {
  String get postId;
  CommentObservability get _observability;

  void _trackLatency({
    required String metricName,
    required Stopwatch stopwatch,
    required String result,
    String? commentId,
    String? source,
    int? itemCount,
  }) {
    stopwatch.stop();
    _observability.trackLatency(
      metricName: metricName,
      postId: postId,
      durationMs: stopwatch.elapsedMilliseconds,
      result: result,
      commentId: commentId,
      source: source,
      itemCount: itemCount,
    );
  }

  void _syncConfirmedCommentTotal(int totalCount) {
    ref
        .read(postInteractionStateProvider.notifier)
        .setCommentCount(postId, totalCount);
  }
}
