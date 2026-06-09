import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/components/comment_system/comment_composer_models.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/cloud/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';

enum CommentSortMode { recommended, latest, mostLiked }

enum CommentListStatus { idle, loading, loadingMore, error }

class CommentState {
  final List<CommentDto> comments;
  final String? nextCursor;
  final CommentSortMode sortMode;
  final CommentListStatus status;
  final String? errorMessage;
  final List<CommentDto> pendingComments;
  final int replyPreviewCount;
  final int replyExpandPageSize;
  final Set<String> loadingReplyCommentIds;
  final bool hasNewComments;
  final bool isRefreshing;

  const CommentState({
    this.comments = const [],
    this.nextCursor,
    this.sortMode = CommentSortMode.recommended,
    this.status = CommentListStatus.idle,
    this.errorMessage,
    this.pendingComments = const [],
    this.replyPreviewCount = 1,
    this.replyExpandPageSize = 10,
    this.loadingReplyCommentIds = const {},
    this.hasNewComments = false,
    this.isRefreshing = false,
  });

  bool get hasMore => nextCursor != null;
  bool get isLoading => status == CommentListStatus.loading;

  CommentState copyWith({
    List<CommentDto>? comments,
    String? Function()? nextCursor,
    CommentSortMode? sortMode,
    CommentListStatus? status,
    String? Function()? errorMessage,
    List<CommentDto>? pendingComments,
    int? replyPreviewCount,
    int? replyExpandPageSize,
    Set<String>? loadingReplyCommentIds,
    bool? hasNewComments,
    bool? isRefreshing,
  }) {
    return CommentState(
      comments: comments ?? this.comments,
      nextCursor: nextCursor != null ? nextCursor() : this.nextCursor,
      sortMode: sortMode ?? this.sortMode,
      status: status ?? this.status,
      errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
      pendingComments: pendingComments ?? this.pendingComments,
      replyPreviewCount: replyPreviewCount ?? this.replyPreviewCount,
      replyExpandPageSize: replyExpandPageSize ?? this.replyExpandPageSize,
      loadingReplyCommentIds:
          loadingReplyCommentIds ?? this.loadingReplyCommentIds,
      hasNewComments: hasNewComments ?? this.hasNewComments,
      isRefreshing: isRefreshing ?? this.isRefreshing,
    );
  }
}

class CommentNotifier extends Notifier<CommentState> {
  CommentNotifier(this.postId);

  static const Duration _pollingInterval = Duration(seconds: 30);
  static final Map<String, _CommentPageCacheEntry> _commentPageCache =
      <String, _CommentPageCacheEntry>{};
  static final Set<CommentNotifier> _activePollingTargets = <CommentNotifier>{};
  static Timer? _sharedPollingTimer;

  final String postId;

  ContentRepository get _repo => ref.read(contentRepositoryProvider);
  CommentObservability get _observability =>
      ref.read(commentObservabilityProvider);

  @override
  CommentState build() {
    _registerPollingTarget();
    ref.onDispose(_unregisterPollingTarget);
    return _commentPageCache[_snapshotKey(CommentSortMode.recommended)]
            ?.state ??
        const CommentState();
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
    final activeContext = await ref.read(activePersonaContextProvider.future);
    if (ref
            .read(contentRepositoryProvider)
            .requiresResolvedPersonaForMutations &&
        activeContext.isFallback) {
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
      hasNewComments: false,
    );
    try {
      await _hydrateCommentConfig();
      final sortParam = _sortParam(state.sortMode);
      final page = await _repo.listComments(postId: postId, sort: sortParam);
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        status: CommentListStatus.idle,
      );
      _storeSnapshot();
      _trackLatency(
        metricName: CommentMetricNames.listLoadMs,
        stopwatch: stopwatch,
        result: 'success',
        source: 'initial',
        itemCount: page.items.length,
      );
    } catch (e) {
      state = state.copyWith(
        status: CommentListStatus.error,
        errorMessage: () => runtimeErrorDisplayMessage(e),
      );
      _trackLatency(
        metricName: CommentMetricNames.listLoadMs,
        stopwatch: stopwatch,
        result: 'error',
        source: 'initial',
      );
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.status == CommentListStatus.loadingMore) {
      return;
    }
    state = state.copyWith(status: CommentListStatus.loadingMore);
    try {
      final sortParam = _sortParam(state.sortMode);
      final page = await _repo.listComments(
        postId: postId,
        cursor: state.nextCursor,
        sort: sortParam,
      );
      state = state.copyWith(
        comments: [...state.comments, ...page.items],
        nextCursor: () => page.nextCursor,
        status: CommentListStatus.idle,
      );
      _storeSnapshot();
    } catch (e) {
      state = state.copyWith(status: CommentListStatus.idle);
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
    state = state.copyWith(isRefreshing: true);
    try {
      final page = await _repo.listComments(
        postId: postId,
        sort: _sortParam(state.sortMode),
      );
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        hasNewComments: false,
        isRefreshing: false,
        status: CommentListStatus.idle,
      );
      _storeSnapshot();
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'success',
        source: 'notice',
        itemCount: page.items.length,
      );
    } catch (e) {
      state = state.copyWith(isRefreshing: false);
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'error',
        source: 'notice',
      );
    }
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
      final latest = page.items.isEmpty ? null : page.items.first;
      if (latest != null && latest.id != state.comments.first.id) {
        state = state.copyWith(hasNewComments: true);
      }
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'success',
        source: 'polling',
        itemCount: page.items.length,
      );
    } catch (e) {
      _trackLatency(
        metricName: CommentMetricNames.pollingRefreshMs,
        stopwatch: stopwatch,
        result: 'error',
        source: 'polling',
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
        .commentCountFor(postId, fallback: state.comments.length);
    final activeContext = await _resolveActivePersonaContext();
    final resolvedSubAccountId = subAccountId ?? activeContext.subAccountId;
    final optimistic = CommentDto(
      id: 'pending_${DateTime.now().millisecondsSinceEpoch}',
      postId: postId,
      authorId: resolvedSubAccountId,
      content: content,
      replyToCommentId: replyToCommentId,
      parentCommentId: replyToCommentId,
      attachmentMediaIds: attachmentMediaIds,
      attachments: attachmentMediaIds
          .map(
            (id) => <String, dynamic>{
              'mediaId': id,
              'type': 'image',
              'url': 'media/comment/$id/v1/comment.png',
            },
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
    state = state.copyWith(
      comments: [optimistic, ...state.comments],
      pendingComments: [...state.pendingComments, optimistic],
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
      state = state.copyWith(
        comments: state.comments
            .map((c) => c.id == optimistic.id ? confirmed : c)
            .toList(),
        pendingComments: state.pendingComments
            .where((c) => c.id != optimistic.id)
            .toList(),
      );
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
      state = state.copyWith(
        comments: state.comments.where((c) => c.id != optimistic.id).toList(),
        pendingComments: state.pendingComments
            .where((c) => c.id != optimistic.id)
            .toList(),
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
    final baselineCommentCount = ref
        .read(postInteractionStateProvider)
        .commentCountFor(postId, fallback: original.length);
    state = state.copyWith(
      comments: state.comments.where((c) => c.id != commentId).toList(),
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
    } catch (e) {
      state = state.copyWith(comments: original);
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

  Future<void> expandReplies(String commentId) async {
    if (state.loadingReplyCommentIds.contains(commentId)) return;
    final parent = _findComment(commentId);
    if (parent == null || parent.replyNextCursor == null) return;
    final stopwatch = Stopwatch()..start();
    state = state.copyWith(
      loadingReplyCommentIds: {...state.loadingReplyCommentIds, commentId},
    );
    try {
      final page = await _repo.listCommentReplies(
        postId: postId,
        commentId: commentId,
        cursor: parent.replyNextCursor,
        limit: state.replyExpandPageSize,
      );
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

  Future<void> _hydrateCommentConfig() async {
    final config = ref.read(commentRemoteConfigProvider);
    state = state.copyWith(
      replyPreviewCount: config.replyPreviewCount,
      replyExpandPageSize: config.replyExpandPageSize,
    );
  }

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

  CommentDto? _findComment(String commentId) {
    for (final comment in state.comments) {
      if (comment.id == commentId) return comment;
      for (final reply in comment.replyPreview) {
        if (reply.id == commentId) return reply;
      }
    }
    return null;
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

  String _snapshotKey(CommentSortMode mode) => '$postId:${_sortParam(mode)}';

  void _storeSnapshot() {
    _commentPageCache[_snapshotKey(state.sortMode)] = _CommentPageCacheEntry(
      state: state.copyWith(
        status: CommentListStatus.idle,
        errorMessage: () => null,
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
