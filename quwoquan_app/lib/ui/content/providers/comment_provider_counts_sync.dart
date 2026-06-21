part of 'comment_provider.dart';

/// CommentNotifier 的「计数增量 / 基线 watermark / 轮询探测 / 权威计数对账 / 耗时埋点」
/// 子系统。与主文件同库（part），通过抽象 hook 复用主类的 [postId] / [_repo] /
/// [_observability]，不构成第二数据源（R24/R25）。
mixin _CommentCountsSyncMixin on Notifier<CommentState> {
  String get postId;
  ContentRepository get _repo;
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

  Future<void> checkForNewComments() async {
    if (state.comments.isEmpty ||
        state.isLoading ||
        state.isRefreshing ||
        state.hasNewComments) {
      return;
    }
    final stopwatch = Stopwatch()..start();
    try {
      final page = await _repo.listComments(
        postId: postId,
        sort: _sortParam(state.sortMode),
        limit: 1,
      );
      if (!ref.mounted) {
        return;
      }
      final latest = page.items.isEmpty ? null : page.items.first;
      _syncConfirmedCommentTotal(page.totalCount);
      final listChanged =
          latest != null && latest.id != state.comments.first.id;
      if (state.baselineWatermark == null) {
        // 基线尚未建立（首次建立失败）：先补建基线，不产出解释，
        // 避免把首同步（无下界）误当作「较进入时的增量」。
        await _establishCountsBaselineIfNeeded();
        if (!ref.mounted) {
          return;
        }
        if (listChanged) {
          state = state.copyWith(hasNewComments: true);
        }
      } else {
        final delta = await _queryCountsDelta(
          since: state.baselineWatermark,
          source: 'polling',
        );
        if (!ref.mounted) {
          return;
        }
        if (delta != null) {
          _reconcileAuthoritativeTotal(delta.currentTotal);
        }
        final hasExplainableDelta = delta?.hasChanges ?? false;
        if (listChanged || hasExplainableDelta) {
          state = state.copyWith(
            hasNewComments: true,
            countsDelta: hasExplainableDelta ? () => delta : null,
          );
        }
      }
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'success',
        source: 'polling',
        itemCount: page.items.length,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'error',
        source: 'polling',
      );
    }
  }

  /// 进入详情后建立基线 watermark（首同步 since=null，仅记录基线、对账权威
  /// 计数，不产出「新增/删除」解释）。已建立则跳过，保证基线锚定「本次进入」。
  Future<void> _establishCountsBaselineIfNeeded() async {
    if (state.baselineWatermark != null) {
      return;
    }
    final delta = await _queryCountsDelta(since: null, source: 'baseline');
    if (delta == null || !ref.mounted) {
      return;
    }
    state = state.copyWith(baselineWatermark: () => delta.watermark);
    _reconcileAuthoritativeTotal(delta.currentTotal);
  }

  /// 统一封装 GetCommentCountsDelta 调用与耗时观测；失败返回 null（不阻断列表）。
  Future<CommentCountsDelta?> _queryCountsDelta({
    required DateTime? since,
    required String source,
  }) async {
    final stopwatch = Stopwatch()..start();
    try {
      final delta = await _repo.getCommentCountsDelta(
        postId: postId,
        since: since,
      );
      _trackLatency(
        metricName: CommentMetricNames.countsDeltaMs,
        stopwatch: stopwatch,
        result: 'success',
        source: source,
      );
      return delta;
    } catch (e) {
      // R17：失败不静默吞掉，落计数增量耗时埋点（result=error）便于诊断。
      _trackLatency(
        metricName: CommentMetricNames.countsDeltaMs,
        stopwatch: stopwatch,
        result: 'error',
        source: source,
      );
      return null;
    }
  }

  /// 用权威 currentTotal 对账写回 postInteractionState，消除「不开评论页拿不到
  /// 权威计数刷新」的债（与 setCommentCount 协同，幂等）。
  void _reconcileAuthoritativeTotal(int currentTotal) {
    ref
        .read(postInteractionStateProvider.notifier)
        .setCommentCount(postId, currentTotal);
  }
}
