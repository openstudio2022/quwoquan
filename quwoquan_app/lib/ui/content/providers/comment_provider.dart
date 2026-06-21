import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/comment_system/comment_composer_models.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';

part 'comment_provider_state.dart';
part 'comment_provider_reply_tree.dart';
part 'comment_provider_counts_sync.dart';

class CommentNotifier extends Notifier<CommentState>
    with _CommentCountsSyncMixin {
  CommentNotifier(this.postId);

  static const Duration _pollingInterval = Duration(seconds: 30);
  static final Map<String, _CommentPageCacheEntry> _commentPageCache =
      <String, _CommentPageCacheEntry>{};
  static final Set<CommentNotifier> _activePollingTargets = <CommentNotifier>{};
  static Timer? _sharedPollingTimer;

  @override
  final String postId;

  @override
  ContentRepository get _repo => ref.read(contentRepositoryProvider);
  @override
  CommentObservability get _observability =>
      ref.read(commentObservabilityProvider);
  PageLifecycleObservability get _lifecycleObservability =>
      ref.read(pageLifecycleObservabilityProvider);

  @override
  CommentState build() {
    _registerPollingTarget();
    ref.onDispose(_unregisterPollingTarget);
    final cached =
        _commentPageCache[_snapshotKey(CommentSortMode.recommended)]?.state;
    if (cached != null) {
      // 重新进入详情：清空上次会话的基线/增量解释/新评论标记，
      // 确保按「本次进入」重新建立 baseline watermark。
      return cached.copyWith(
        baselineWatermark: () => null,
        countsDelta: () => null,
        hasNewComments: false,
      );
    }
    return const CommentState();
  }

  void _registerPollingTarget() {
    _activePollingTargets.add(this);
    _sharedPollingTimer ??= Timer.periodic(_pollingInterval, (_) {
      for (final target in List<CommentNotifier>.from(_activePollingTargets)) {
        unawaited(target.checkForNewComments());
      }
    });
  }

  void _unregisterPollingTarget() {
    _activePollingTargets.remove(this);
    if (_activePollingTargets.isEmpty) {
      _sharedPollingTimer?.cancel();
      _sharedPollingTimer = null;
    }
  }

  Future<ActivePersonaContextViewData> _resolveActivePersonaContext() async {
    final requiresResolvedPersonaForMutations = ref
        .read(contentRepositoryProvider)
        .requiresResolvedPersonaForMutations;
    final activeContext = await ref.read(activePersonaContextProvider.future);
    if (requiresResolvedPersonaForMutations && activeContext.isFallback) {
      throw StateError('active persona context unavailable');
    }
    return activeContext;
  }

  Future<void> loadComments() async {
    if (state.isLoading) return;
    final stopwatch = Stopwatch()..start();
    state = state.copyWith(
      status: CommentListStatus.loading,
      errorMessage: () => null,
      rawError: () => null,
      appendError: () => null,
      refreshError: () => null,
      hasNewComments: false,
    );
    _lifecycleObservability.recordPageState(
      pageName: 'comment_thread',
      route: '/posts/$postId/comments',
      surface: 'comments',
      phase: 'onlineLoading',
      source: 'online',
      hasCache: state.comments.isNotEmpty,
      itemCount: state.comments.length,
    );
    try {
      await _hydrateCommentConfig();
      final sortParam = _sortParam(state.sortMode);
      final page = await _repo.listComments(postId: postId, sort: sortParam);
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        totalCount: page.totalCount,
        status: CommentListStatus.idle,
      );
      _syncConfirmedCommentTotal(page.totalCount);
      await _establishCountsBaselineIfNeeded();
      if (!ref.mounted) {
        return;
      }
      _storeSnapshot();
      _trackLatency(
        metricName: CommentMetricNames.listLoadMs,
        stopwatch: stopwatch,
        result: 'success',
        source: 'initial',
        itemCount: page.items.length,
      );
      _lifecycleObservability.recordPageState(
        pageName: 'comment_thread',
        route: '/posts/$postId/comments',
        surface: 'comments',
        phase: page.items.isEmpty ? 'emptySuccess' : 'onlineSuccess',
        source: 'online',
        hasCache: false,
        itemCount: page.items.length,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      final hasRetainedComments = state.comments.isNotEmpty;
      state = state.copyWith(
        status: hasRetainedComments
            ? CommentListStatus.idle
            : CommentListStatus.error,
        errorMessage: () => runtimeErrorDisplayMessage(e),
        rawError: () => e,
      );
      _trackLatency(
        metricName: CommentMetricNames.listLoadMs,
        stopwatch: stopwatch,
        result: 'error',
        source: 'initial',
      );
      _lifecycleObservability.recordPageState(
        pageName: 'comment_thread',
        route: '/posts/$postId/comments',
        surface: 'comments',
        phase: hasRetainedComments ? 'cacheFallback' : 'blockingFailure',
        source: hasRetainedComments ? 'retained' : 'online',
        copyKey: hasRetainedComments
            ? 'refreshFailedRetained'
            : 'commentLoadFailedTitle',
        error: e,
        durationMs: stopwatch.elapsedMilliseconds,
        hasCache: hasRetainedComments,
        itemCount: state.comments.length,
      );
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.status == CommentListStatus.loadingMore) {
      return;
    }
    final itemCountBefore = state.comments.length;
    state = state.copyWith(
      status: CommentListStatus.loadingMore,
      appendError: () => null,
    );
    _lifecycleObservability.recordAppend(
      pageName: 'comment_thread',
      result: 'loading',
      cursorPresent: state.nextCursor != null,
      hasMore: state.hasMore,
      itemCountBefore: itemCountBefore,
    );
    try {
      final sortParam = _sortParam(state.sortMode);
      final page = await _repo.listComments(
        postId: postId,
        cursor: state.nextCursor,
        sort: sortParam,
      );
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: [...state.comments, ...page.items],
        nextCursor: () => page.nextCursor,
        totalCount: page.totalCount,
        status: CommentListStatus.idle,
      );
      _syncConfirmedCommentTotal(page.totalCount);
      _storeSnapshot();
      _lifecycleObservability.recordAppend(
        pageName: 'comment_thread',
        result: 'success',
        cursorPresent: page.nextCursor != null,
        hasMore: page.nextCursor != null,
        itemCountBefore: itemCountBefore,
        itemCountAfter: state.comments.length,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        status: CommentListStatus.idle,
        appendError: () => e,
      );
      _lifecycleObservability.recordAppend(
        pageName: 'comment_thread',
        result: 'failure',
        cursorPresent: state.nextCursor != null,
        hasMore: state.hasMore,
        itemCountBefore: itemCountBefore,
        copyKey: 'appendFailedRetry',
        error: e,
      );
    }
  }

  Future<void> switchSort(CommentSortMode mode) async {
    if (mode == state.sortMode) return;
    _observability.trackAction(
      eventName: CommentEventNames.sortChanged,
      postId: postId,
      sortMode: _sortParam(mode),
    );
    final snapshot = _commentPageCache[_snapshotKey(mode)]?.state;
    if (snapshot != null) {
      _observability.trackAction(
        eventName: CommentEventNames.listCacheHit,
        postId: postId,
        sortMode: _sortParam(mode),
        itemCount: snapshot.comments.length,
      );
    }
    state = state.copyWith(
      sortMode: mode,
      comments: snapshot?.comments ?? [],
      nextCursor: () => snapshot?.nextCursor,
      totalCount: snapshot?.totalCount ?? 0,
      rawError: () => null,
      appendError: () => null,
      refreshError: () => null,
      hasNewComments: false,
    );
    await loadComments();
  }

  Future<void> refreshFromNewCommentNotice() async {
    if (state.isRefreshing) return;
    final stopwatch = Stopwatch()..start();
    _observability.trackAction(
      eventName: CommentEventNames.newNoticeClicked,
      postId: postId,
      sortMode: _sortParam(state.sortMode),
    );
    state = state.copyWith(isRefreshing: true, refreshError: () => null);
    try {
      final page = await _repo.listComments(
        postId: postId,
        sort: _sortParam(state.sortMode),
      );
      if (!ref.mounted) {
        return;
      }
      // 用户已确认解释（点击刷新）：推进基线到本次已展示 delta 的 watermark，
      // 并清空增量，避免下次 poll 重复计数；无已展示 delta 则保持原基线。
      final advancedWatermark = state.countsDelta?.watermark;
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        totalCount: page.totalCount,
        hasNewComments: false,
        isRefreshing: false,
        status: CommentListStatus.idle,
        countsDelta: () => null,
        baselineWatermark:
            advancedWatermark != null ? () => advancedWatermark : null,
      );
      _syncConfirmedCommentTotal(page.totalCount);
      _storeSnapshot();
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'success',
        source: 'notice',
        itemCount: page.items.length,
      );
      _lifecycleObservability.recordRefresh(
        pageName: 'comment_thread',
        result: 'success',
        retained: true,
        itemCount: page.items.length,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(isRefreshing: false, refreshError: () => e);
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'error',
        source: 'notice',
      );
      _lifecycleObservability.recordRefresh(
        pageName: 'comment_thread',
        result: 'failure',
        retained: true,
        copyKey: 'refreshFailedRetained',
        error: e,
      );
    }
  }

  Future<CommentDto?> addComment(
    String content, {
    String? replyToCommentId,
    List<String> attachmentMediaIds = const <String>[],
    List<CommentMentionCandidate> mentions = const <CommentMentionCandidate>[],
    String? subAccountId,
  }) async {
    final stopwatch = Stopwatch()..start();
    // 仅在 Repository 边界把强类型 @ 候选落到云侧 codegen 契约 wire 形态。
    final mentionsWire = mentions
        .map((m) => m.toWire())
        .toList(growable: false);
    final baselineCommentCount = ref
        .read(postInteractionStateProvider)
        .commentCountFor(postId, fallback: state.totalCount);
    final activeContext = await _resolveActivePersonaContext();
    if (!ref.mounted) {
      return null;
    }
    final resolvedSubAccountId = subAccountId ?? activeContext.subAccountId;
    final parentCommentId = replyToCommentId == null
        ? null
        : _parentIdForReplyTarget(replyToCommentId);
    final optimistic = CommentDto(
      id: 'pending_${DateTime.now().millisecondsSinceEpoch}',
      postId: postId,
      authorId: resolvedSubAccountId,
      content: content,
      replyToCommentId: replyToCommentId,
      parentCommentId: parentCommentId,
      attachmentMediaIds: attachmentMediaIds,
      attachments: attachmentMediaIds
          .map(
            (id) => CommentAttachmentDto(
              mediaId: id,
              type: 'image',
              url: 'media/comment/$id/v1/comment.png',
            ),
          )
          .toList(growable: false),
      mentions: mentionsWire,
      viewerReaction: 'none',
      canDelete: true,
      canReply: true,
      canReport: false,
      displayName: activeContext.displayName,
      avatarUrl: activeContext.avatarUrl,
      createdAt: DateTime.now(),
    );
    final nextTotalCount = state.totalCount + 1;
    state = state.copyWith(
      comments: parentCommentId == null
          ? [optimistic, ...state.comments]
          : _appendReplyToParent(
              state.comments,
              parentCommentId: parentCommentId,
              reply: optimistic,
            ),
      pendingComments: [...state.pendingComments, optimistic],
      totalCount: nextTotalCount,
      expandedReplyCommentIds: parentCommentId == null
          ? state.expandedReplyCommentIds
          : {...state.expandedReplyCommentIds, parentCommentId},
    );
    ref
        .read(postInteractionStateProvider.notifier)
        .stageOptimisticComment(
          postId,
          baseCommentCount: baselineCommentCount,
          delta: 1,
        );
    try {
      final confirmed = await _repo.createComment(
        postId: postId,
        content: content,
        replyToCommentId: replyToCommentId,
        attachmentMediaIds: attachmentMediaIds,
        mentions: mentionsWire,
        subAccountId: resolvedSubAccountId.isEmpty
            ? null
            : resolvedSubAccountId,
        personaContextVersion: activeContext.contextVersion,
      );
      if (!ref.mounted) {
        return confirmed;
      }
      state = state.copyWith(
        comments: parentCommentId == null
            ? state.comments
                  .map((c) => c.id == optimistic.id ? confirmed : c)
                  .toList()
            : _replaceReplyInParent(
                state.comments,
                parentCommentId: parentCommentId,
                pendingReplyId: optimistic.id,
                confirmed: confirmed,
              ),
        pendingComments: state.pendingComments
            .where((c) => c.id != optimistic.id)
            .toList(),
      );
      _syncConfirmedCommentTotal(state.totalCount);
      _trackLatency(
        metricName: CommentMetricNames.submitConfirmMs,
        stopwatch: stopwatch,
        result: 'success',
        commentId: confirmed.id,
      );
      _observability.trackAction(
        eventName: CommentEventNames.submitSucceeded,
        postId: postId,
        commentId: confirmed.id,
        sortMode: _sortParam(state.sortMode),
        replyDepth: replyToCommentId == null ? 0 : 1,
        latencyMs: stopwatch.elapsedMilliseconds,
        attachmentCount: attachmentMediaIds.length,
        mentionCount: mentions.length,
      );
      return confirmed;
    } catch (e) {
      if (!ref.mounted) {
        return null;
      }
      state = state.copyWith(
        comments: parentCommentId == null
            ? state.comments.where((c) => c.id != optimistic.id).toList()
            : _removeReplyFromParent(
                state.comments,
                parentCommentId: parentCommentId,
                replyId: optimistic.id,
              ),
        pendingComments: state.pendingComments
            .where((c) => c.id != optimistic.id)
            .toList(),
        totalCount: (state.totalCount - 1).clamp(0, 1 << 31).toInt(),
      );
      ref
          .read(postInteractionStateProvider.notifier)
          .rollbackOptimisticComment(
            postId,
            baseCommentCount: baselineCommentCount,
            delta: 1,
          );
      _trackLatency(
        metricName: CommentMetricNames.submitConfirmMs,
        stopwatch: stopwatch,
        result: 'error',
        commentId: optimistic.id,
      );
      _observability.trackAction(
        eventName: CommentEventNames.submitFailed,
        postId: postId,
        commentId: optimistic.id,
        sortMode: _sortParam(state.sortMode),
        replyDepth: replyToCommentId == null ? 0 : 1,
        latencyMs: stopwatch.elapsedMilliseconds,
        failureKind: e.runtimeType.toString(),
        attachmentCount: attachmentMediaIds.length,
        mentionCount: mentions.length,
      );
      rethrow;
    }
  }

  Future<void> deleteComment(String commentId) async {
    final original = state.comments;
    final originalTotalCount = state.totalCount;
    final parentCommentId = _parentIdForReplyTarget(commentId);
    final baselineCommentCount = ref
        .read(postInteractionStateProvider)
        .commentCountFor(postId, fallback: originalTotalCount);
    state = state.copyWith(
      comments: parentCommentId == null
          ? state.comments.where((c) => c.id != commentId).toList()
          : _removeReplyFromParent(
              state.comments,
              parentCommentId: parentCommentId,
              replyId: commentId,
            ),
      totalCount: (state.totalCount - 1).clamp(0, 1 << 31).toInt(),
    );
    ref
        .read(postInteractionStateProvider.notifier)
        .stageOptimisticComment(
          postId,
          baseCommentCount: baselineCommentCount,
          delta: -1,
        );
    try {
      await _repo.deleteComment(postId: postId, commentId: commentId);
      if (!ref.mounted) {
        return;
      }
      _syncConfirmedCommentTotal(state.totalCount);
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: original,
        totalCount: originalTotalCount,
      );
      ref
          .read(postInteractionStateProvider.notifier)
          .rollbackOptimisticComment(
            postId,
            baseCommentCount: baselineCommentCount,
            delta: -1,
          );
      rethrow;
    }
  }

  Future<void> toggleLike(String commentId) async {
    final current = _findComment(commentId);
    final next = current?.viewerReaction == 'like' ? 'none' : 'like';
    await reactToComment(commentId, next);
  }

  Future<void> toggleDislike(String commentId) async {
    final current = _findComment(commentId);
    final next = current?.viewerReaction == 'dislike' ? 'none' : 'dislike';
    await reactToComment(commentId, next);
  }

  Future<void> reactToComment(String commentId, String reaction) async {
    final stopwatch = Stopwatch()..start();
    final original = state.comments;
    final current = _findComment(commentId);
    if (current == null) return;
    final updated = _applyReaction(current, reaction);
    state = state.copyWith(
      comments: state.comments.map((c) {
        if (c.id == commentId) {
          return updated;
        }
        return c;
      }).toList(),
    );
    try {
      final confirmed = await _repo.reactToComment(
        commentId: commentId,
        reaction: reaction,
      );
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: state.comments
            .map((c) => c.id == commentId ? confirmed : c)
            .toList(),
      );
      _trackLatency(
        metricName: CommentMetricNames.reactionConfirmMs,
        stopwatch: stopwatch,
        result: 'success',
        commentId: commentId,
        source: reaction,
      );
      _observability.trackAction(
        eventName: CommentEventNames.reactionChanged,
        postId: postId,
        commentId: commentId,
        sortMode: _sortParam(state.sortMode),
        latencyMs: stopwatch.elapsedMilliseconds,
        reaction: reaction,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(comments: original);
      _trackLatency(
        metricName: CommentMetricNames.reactionConfirmMs,
        stopwatch: stopwatch,
        result: 'error',
        commentId: commentId,
        source: reaction,
      );
      rethrow;
    }
  }

  /// 内容作者置顶/取消置顶一级评论。仅一级评论可置顶，置顶后排到列表最前；
  /// 乐观更新失败时回滚到原顺序并向上抛出（由 UI 用结构化错误码提示）。
  Future<void> togglePin(String commentId) async {
    final current = _findComment(commentId);
    if (current == null) return;
    final nextPinned = !current.isPinned;
    final stopwatch = Stopwatch()..start();
    final original = state.comments;
    final optimistic = current.copyWith(
      isPinned: nextPinned,
      pinnedAt: () => nextPinned ? DateTime.now() : null,
    );
    state = state.copyWith(
      comments: _withPinnedFirst(
        state.comments
            .map((c) => c.id == commentId ? optimistic : c)
            .toList(growable: false),
      ),
    );
    try {
      final confirmed = await _repo.setCommentPinned(
        postId: postId,
        commentId: commentId,
        pinned: nextPinned,
      );
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: _withPinnedFirst(
          state.comments
              .map((c) => c.id == commentId ? confirmed : c)
              .toList(growable: false),
        ),
      );
      _trackLatency(
        metricName: CommentMetricNames.pinConfirmMs,
        stopwatch: stopwatch,
        result: 'success',
        commentId: commentId,
        source: nextPinned ? 'pin' : 'unpin',
      );
      _observability.trackAction(
        eventName: CommentEventNames.pinChanged,
        postId: postId,
        commentId: commentId,
        sortMode: _sortParam(state.sortMode),
        latencyMs: stopwatch.elapsedMilliseconds,
        reaction: nextPinned ? 'pin' : 'unpin',
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(comments: original);
      _trackLatency(
        metricName: CommentMetricNames.pinConfirmMs,
        stopwatch: stopwatch,
        result: 'error',
        commentId: commentId,
        source: nextPinned ? 'pin' : 'unpin',
      );
      rethrow;
    }
  }

  /// 展开二级回复（分段加载）：
  /// - 首次展开（未处于展开态）：最多加载 [CommentState.replyFirstExpandPageSize] 条；
  /// - 后续「展开更多回复」：每页最多 [CommentState.replyExpandPageSize] 条；
  /// - 服务端已无更多（`replyNextCursor == null`）：仅切到展开显示态，不再请求。
  Future<void> expandReplies(String commentId) async {
    if (state.loadingReplyCommentIds.contains(commentId)) return;
    final parent = _findComment(commentId);
    if (parent == null) return;
    final wasExpanded = state.expandedReplyCommentIds.contains(commentId);
    // 服务端已无更多回复：仅把显示态切到展开，复用已加载回复。
    if (parent.replyNextCursor == null) {
      if (!wasExpanded) {
        state = state.copyWith(
          expandedReplyCommentIds: {
            ...state.expandedReplyCommentIds,
            commentId,
          },
        );
        _observability.trackAction(
          eventName: CommentEventNames.replyExpanded,
          postId: postId,
          commentId: commentId,
          sortMode: _sortParam(state.sortMode),
          replyDepth: 1,
        );
      }
      return;
    }
    final stopwatch = Stopwatch()..start();
    final pageSize = wasExpanded
        ? state.replyExpandPageSize
        : state.replyFirstExpandPageSize;
    state = state.copyWith(
      loadingReplyCommentIds: {...state.loadingReplyCommentIds, commentId},
      expandedReplyCommentIds: {...state.expandedReplyCommentIds, commentId},
    );
    try {
      final page = await _repo.listCommentReplies(
        postId: postId,
        commentId: commentId,
        cursor: parent.replyNextCursor,
        limit: pageSize,
      );
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: state.comments
            .map(
              (comment) => comment.id == commentId
                  ? comment.copyWith(
                      replyPreview: [...comment.replyPreview, ...page.items],
                      replyNextCursor: () => page.nextCursor,
                    )
                  : comment,
            )
            .toList(),
        loadingReplyCommentIds: state.loadingReplyCommentIds
            .where((id) => id != commentId)
            .toSet(),
      );
      _trackLatency(
        metricName: CommentMetricNames.replyExpandMs,
        stopwatch: stopwatch,
        result: 'success',
        commentId: commentId,
        itemCount: page.items.length,
      );
      _observability.trackAction(
        eventName: CommentEventNames.replyExpanded,
        postId: postId,
        commentId: commentId,
        sortMode: _sortParam(state.sortMode),
        replyDepth: 1,
        latencyMs: stopwatch.elapsedMilliseconds,
      );
    } catch (e) {
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        loadingReplyCommentIds: state.loadingReplyCommentIds
            .where((id) => id != commentId)
            .toSet(),
      );
      _trackLatency(
        metricName: CommentMetricNames.replyExpandMs,
        stopwatch: stopwatch,
        result: 'error',
        commentId: commentId,
      );
      rethrow;
    }
  }

  /// 收起二级回复：回到「仅显示 [CommentState.replyPreviewCount] 条」的预览态，
  /// 已加载的回复保留在内存，再次展开时无需重复请求已加载部分。
  void collapseReplies(String commentId) {
    if (!state.expandedReplyCommentIds.contains(commentId)) return;
    state = state.copyWith(
      expandedReplyCommentIds: state.expandedReplyCommentIds
          .where((id) => id != commentId)
          .toSet(),
    );
    _observability.trackAction(
      eventName: CommentEventNames.replyCollapsed,
      postId: postId,
      commentId: commentId,
      sortMode: _sortParam(state.sortMode),
      replyDepth: 1,
    );
  }

  Future<void> _hydrateCommentConfig() async {
    final config = ref.read(commentRemoteConfigProvider);
    state = state.copyWith(
      replyPreviewCount: config.replyPreviewCount,
      replyFirstExpandPageSize: config.replyFirstExpandPageSize,
      replyExpandPageSize: config.replyExpandPageSize,
      foldLineCount: config.foldLineCount,
    );
  }

  String? _parentIdForReplyTarget(String commentId) {
    for (final comment in state.comments) {
      if (comment.id == commentId) return comment.id;
      for (final reply in comment.replyPreview) {
        if (reply.id == commentId) {
          final parentId = reply.parentCommentId?.trim();
          return parentId?.isNotEmpty == true ? parentId : comment.id;
        }
      }
    }
    return null;
  }

  CommentDto? _findComment(String commentId) {
    for (final comment in state.comments) {
      if (comment.id == commentId) return comment;
      for (final reply in comment.replyPreview) {
        if (reply.id == commentId) return reply;
      }
    }
    return null;
  }

  String _snapshotKey(CommentSortMode mode) => '$postId:${_sortParam(mode)}';

  void _storeSnapshot() {
    _commentPageCache[_snapshotKey(state.sortMode)] = _CommentPageCacheEntry(
      state: state.copyWith(
        status: CommentListStatus.idle,
        errorMessage: () => null,
        rawError: () => null,
        appendError: () => null,
        refreshError: () => null,
        isRefreshing: false,
      ),
      cachedAt: DateTime.now(),
    );
  }
}

class _CommentPageCacheEntry {
  const _CommentPageCacheEntry({required this.state, required this.cachedAt});

  final CommentState state;
  final DateTime cachedAt;
}

final commentProviderFamily = NotifierProvider.autoDispose
    .family<CommentNotifier, CommentState, String>(CommentNotifier.new);
