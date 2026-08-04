import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/errors/cloud_error_mapper.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/core/trackers/comment_observability.dart';
import 'package:quwoquan_app/core/trackers/page_lifecycle_observability.dart';
import 'package:quwoquan_app/ui/content/models/comment_view_data.dart';
import 'package:quwoquan_runtime_errors/runtime_errors.dart';

part 'comment_provider_state.dart';
part 'comment_provider_reply_tree.dart';
part 'comment_provider_counts_sync.dart';

class CommentNotifier extends Notifier<CommentState>
    with _CommentCountsSyncMixin {
  CommentNotifier(this.postId);

  @override
  final String postId;

  @override
  CommentObservability get _observability =>
      ref.read(commentObservabilityProvider);
  PageLifecycleObservability get _lifecycleObservability =>
      ref.read(pageLifecycleObservabilityProvider);

  ContentCommentFacet get _repo =>
      ref.read(workBrowserContentCommentFacetProvider);

  @override
  CommentState build() => const CommentState();

  Future<ActivePersonaContextViewData> _resolveActivePersonaContext() async {
    final requiresResolvedPersonaForMutations = ref
        .read(contentConfigRepositoryProvider)
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
      failure: () => null,
      appendFailure: () => null,
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
      final page = await _repo.listComments(postId: postId, sort: state.sort);
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: page.items
            .map(CommentViewData.fromWire)
            .toList(growable: false),
        nextCursor: () => page.nextCursor,
        totalCount: page.total,
        sessionLoadVersion: state.sessionLoadVersion + 1,
        status: CommentListStatus.idle,
      );
      _syncConfirmedCommentTotal(page.total);
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
      final failure = CloudErrorMapper.runtimeFailureFromException(
        e,
        requestPath: '/content/posts/$postId/comments',
      );
      final hasRetainedComments = state.comments.isNotEmpty;
      state = state.copyWith(
        status: hasRetainedComments
            ? CommentListStatus.idle
            : CommentListStatus.error,
        failure: () => failure,
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
        error: failure,
        durationMs: stopwatch.elapsedMilliseconds,
        hasCache: hasRetainedComments,
        itemCount: state.comments.length,
      );
    }
  }

  /// 切换服务端排序档位并重新加载首屏；排序真相源在服务端，禁止本地重排。
  Future<void> changeSort(CommentSort sort) async {
    if (state.sort == sort || state.isLoading) return;
    state = state.copyWith(
      sort: sort,
      comments: const [],
      nextCursor: () => null,
      expandedReplyCommentIds: const {},
    );
    await loadComments();
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.status == CommentListStatus.loadingMore) {
      return;
    }
    final itemCountBefore = state.comments.length;
    state = state.copyWith(
      status: CommentListStatus.loadingMore,
      appendFailure: () => null,
    );
    _lifecycleObservability.recordAppend(
      pageName: 'comment_thread',
      result: 'loading',
      cursorPresent: state.nextCursor != null,
      hasMore: state.hasMore,
      itemCountBefore: itemCountBefore,
    );
    try {
      final page = await _repo.listComments(
        postId: postId,
        cursor: state.nextCursor,
        sort: state.sort,
      );
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: [
          ...state.comments,
          ...page.items.map(CommentViewData.fromWire),
        ],
        nextCursor: () => page.nextCursor,
        totalCount: page.total,
        status: CommentListStatus.idle,
      );
      _syncConfirmedCommentTotal(page.total);
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
      final failure = CloudErrorMapper.runtimeFailureFromException(
        e,
        requestPath: '/content/posts/$postId/comments',
      );
      state = state.copyWith(
        status: CommentListStatus.idle,
        appendFailure: () => failure,
      );
      _lifecycleObservability.recordAppend(
        pageName: 'comment_thread',
        result: 'failure',
        cursorPresent: state.nextCursor != null,
        hasMore: state.hasMore,
        itemCountBefore: itemCountBefore,
        copyKey: 'appendFailedRetry',
        error: failure,
      );
    }
  }

  Future<CommentViewData?> addComment(
    String content, {
    String? replyToCommentId,
    List<String> attachmentMediaIds = const <String>[],
    List<CommentMention> mentions = const <CommentMention>[],
  }) async {
    final stopwatch = Stopwatch()..start();
    final activeContext = await _resolveActivePersonaContext();
    if (!ref.mounted) {
      return null;
    }
    final parentCommentId = replyToCommentId == null
        ? null
        : _parentIdForReplyTarget(replyToCommentId);
    final personaContextVersion = activeContext.contextVersion > 0
        ? activeContext.contextVersion
        : null;
    try {
      final result = await _repo.createComment(
        CreateContentCommentCommand(
          postId: postId,
          content: content,
          replyToCommentId: replyToCommentId,
          attachmentMediaIds: attachmentMediaIds,
          mentions: mentions,
          authorDisplayNameSnapshot: activeContext.displayName,
          authorAvatarUrlSnapshot: activeContext.avatarUrl,
          personaContextVersion: personaContextVersion,
        ),
      );
      if (!ref.mounted) {
        return null;
      }
      final confirmed = await _refreshAfterCreate(
        createdCommentId: result.id,
        parentCommentId: parentCommentId,
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
        sortMode: state.sort.wireName,
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
      _trackLatency(
        metricName: CommentMetricNames.submitConfirmMs,
        stopwatch: stopwatch,
        result: 'error',
      );
      _observability.trackAction(
        eventName: CommentEventNames.submitFailed,
        postId: postId,
        sortMode: state.sort.wireName,
        replyDepth: replyToCommentId == null ? 0 : 1,
        latencyMs: stopwatch.elapsedMilliseconds,
        failureKind: e.runtimeType.toString(),
        attachmentCount: attachmentMediaIds.length,
        mentionCount: mentions.length,
      );
      rethrow;
    }
  }

  Future<CommentViewData> _refreshAfterCreate({
    required String createdCommentId,
    required String? parentCommentId,
  }) async {
    final page = await _repo.listComments(postId: postId, sort: state.sort);
    if (!ref.mounted) {
      throw StateError('comment surface disposed during authoritative refresh');
    }
    state = state.copyWith(
      comments: page.items
          .map(CommentViewData.fromWire)
          .toList(growable: false),
      nextCursor: () => page.nextCursor,
      totalCount: page.total,
      status: CommentListStatus.idle,
      expandedReplyCommentIds: parentCommentId == null
          ? state.expandedReplyCommentIds
          : {...state.expandedReplyCommentIds, parentCommentId},
    );
    _syncConfirmedCommentTotal(page.total);
    final visible = _findComment(createdCommentId);
    if (visible != null) return visible;
    if (parentCommentId == null) {
      throw StateError('created comment missing from authoritative projection');
    }
    final replies = await _repo.listReplies(
      postId: postId,
      commentId: parentCommentId,
      limit: state.replyExpandPageSize,
    );
    CommentViewData? created;
    for (final reply in replies.items) {
      if (reply.id == createdCommentId) {
        created = CommentViewData.fromWire(reply);
        break;
      }
    }
    if (created == null) {
      throw StateError('created reply missing from authoritative projection');
    }
    state = state.copyWith(
      comments: state.comments
          .map(
            (comment) => comment.id == parentCommentId
                ? comment.copyWith(
                    replyPreview: replies.items
                        .map(CommentViewData.fromWire)
                        .toList(growable: false),
                    replyCount: replies.total,
                    replyNextCursor: () => replies.nextCursor,
                  )
                : comment,
          )
          .toList(growable: false),
    );
    return created;
  }

  Future<void> deleteComment(String commentId) async {
    final current = _findComment(commentId);
    if (current == null) return;
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
      await _repo.deleteComment(
        DeleteContentCommentCommand(postId: postId, commentId: commentId),
      );
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
    final next = current?.viewerReaction == CommentReactionType.like
        ? CommentReactionType.none
        : CommentReactionType.like;
    await reactToComment(commentId, next);
  }

  Future<void> toggleDislike(String commentId) async {
    final current = _findComment(commentId);
    final next = current?.viewerReaction == CommentReactionType.dislike
        ? CommentReactionType.none
        : CommentReactionType.dislike;
    await reactToComment(commentId, next);
  }

  Future<void> reactToComment(
    String commentId,
    CommentReactionType reaction,
  ) async {
    final stopwatch = Stopwatch()..start();
    final original = state.comments;
    final current = _findComment(commentId);
    if (current == null) return;
    final updated = _applyReaction(current, reaction);
    state = state.copyWith(
      comments: _replaceCommentInTree(state.comments, updated),
    );
    try {
      final confirmed = await _repo.reactToComment(
        ReactToContentCommentCommand(commentId: commentId, reaction: reaction),
      );
      if (!ref.mounted) {
        return;
      }
      final projected = _findComment(commentId);
      if (projected == null) {
        throw StateError('reacted comment missing from local projection');
      }
      state = state.copyWith(
        comments: _replaceCommentInTree(
          state.comments,
          projected.copyWith(
            likeCount: confirmed.likeCount,
            dislikeCount: confirmed.dislikeCount,
            viewerReaction: confirmed.reaction,
          ),
        ),
      );
      _trackLatency(
        metricName: CommentMetricNames.reactionConfirmMs,
        stopwatch: stopwatch,
        result: 'success',
        commentId: commentId,
        source: reaction.name,
      );
      _observability.trackAction(
        eventName: CommentEventNames.reactionChanged,
        postId: postId,
        commentId: commentId,
        sortMode: state.sort.wireName,
        latencyMs: stopwatch.elapsedMilliseconds,
        reaction: reaction.name,
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
        source: reaction.name,
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
      final command = ChangeContentCommentPinCommand(
        postId: postId,
        commentId: commentId,
      );
      final confirmed = nextPinned
          ? await _repo.pinComment(command)
          : await _repo.unpinComment(command);
      if (!ref.mounted) {
        return;
      }
      state = state.copyWith(
        comments: _withPinnedFirst(
          state.comments
              .map(
                (comment) => comment.id == commentId
                    ? comment.copyWith(
                        version: confirmed.version,
                        status: confirmed.status,
                        isPinned: nextPinned,
                        pinnedAt: () => nextPinned
                            ? (comment.pinnedAt ?? DateTime.now().toUtc())
                            : null,
                      )
                    : comment,
              )
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
        sortMode: state.sort.wireName,
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
          sortMode: state.sort.wireName,
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
      final page = await _repo.listReplies(
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
                      replyPreview: [
                        ...comment.replyPreview,
                        ...page.items.map(CommentViewData.fromWire),
                      ],
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
        sortMode: state.sort.wireName,
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
      sortMode: state.sort.wireName,
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

  CommentViewData? _findComment(String commentId) {
    for (final comment in state.comments) {
      if (comment.id == commentId) return comment;
      for (final reply in comment.replyPreview) {
        if (reply.id == commentId) return reply;
      }
    }
    return null;
  }
}

final commentProviderFamily = NotifierProvider.autoDispose
    .family<CommentNotifier, CommentState, String>(CommentNotifier.new);
