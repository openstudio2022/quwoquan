import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

enum CommentSortMode { latest, hot }

enum CommentListStatus { idle, loading, loadingMore, error }

class CommentState {
  final List<CommentDto> comments;
  final Set<String> likedCommentIds;
  final String? nextCursor;
  final CommentSortMode sortMode;
  final CommentListStatus status;
  final String? errorMessage;
  final List<CommentDto> pendingComments;

  const CommentState({
    this.comments = const [],
    this.likedCommentIds = const {},
    this.nextCursor,
    this.sortMode = CommentSortMode.latest,
    this.status = CommentListStatus.idle,
    this.errorMessage,
    this.pendingComments = const [],
  });

  bool get hasMore => nextCursor != null;
  bool get isLoading => status == CommentListStatus.loading;

  CommentState copyWith({
    List<CommentDto>? comments,
    Set<String>? likedCommentIds,
    String? Function()? nextCursor,
    CommentSortMode? sortMode,
    CommentListStatus? status,
    String? Function()? errorMessage,
    List<CommentDto>? pendingComments,
  }) {
    return CommentState(
      comments: comments ?? this.comments,
      likedCommentIds: likedCommentIds ?? this.likedCommentIds,
      nextCursor: nextCursor != null ? nextCursor() : this.nextCursor,
      sortMode: sortMode ?? this.sortMode,
      status: status ?? this.status,
      errorMessage: errorMessage != null ? errorMessage() : this.errorMessage,
      pendingComments: pendingComments ?? this.pendingComments,
    );
  }
}

class CommentNotifier extends Notifier<CommentState> {
  CommentNotifier(this.postId);

  final String postId;

  ContentRepository get _repo => ref.read(contentRepositoryProvider);

  @override
  CommentState build() => const CommentState();

  Future<ActivePersonaContextViewData> _resolveActivePersonaContext() async {
    final activeContext = await ref.read(activePersonaContextProvider.future);
    if (ref.read(contentRepositoryProvider).requiresResolvedPersonaForMutations &&
        activeContext.isFallback) {
      throw StateError('active persona context unavailable');
    }
    return activeContext;
  }

  Future<void> loadComments() async {
    if (state.isLoading) return;
    state = state.copyWith(
      status: CommentListStatus.loading,
      errorMessage: () => null,
    );
    try {
      final sortParam = state.sortMode == CommentSortMode.hot
          ? 'hot'
          : 'latest';
      final page = await _repo.listComments(postId: postId, sort: sortParam);
      state = state.copyWith(
        comments: page.items,
        nextCursor: () => page.nextCursor,
        status: CommentListStatus.idle,
      );
    } catch (e) {
      state = state.copyWith(
        status: CommentListStatus.error,
        errorMessage: () => e.toString(),
      );
    }
  }

  Future<void> loadMore() async {
    if (!state.hasMore || state.status == CommentListStatus.loadingMore) {
      return;
    }
    state = state.copyWith(status: CommentListStatus.loadingMore);
    try {
      final sortParam = state.sortMode == CommentSortMode.hot
          ? 'hot'
          : 'latest';
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
    } catch (e) {
      state = state.copyWith(status: CommentListStatus.idle);
    }
  }

  Future<void> switchSort(CommentSortMode mode) async {
    if (mode == state.sortMode) return;
    state = state.copyWith(
      sortMode: mode,
      comments: [],
      nextCursor: () => null,
    );
    await loadComments();
  }

  Future<CommentDto?> addComment(
    String content, {
    String? replyToCommentId,
    String? personaId,
  }) async {
    final activeContext = await _resolveActivePersonaContext();
    final resolvedProfileSubjectId = activeContext.profileSubjectId.isNotEmpty
        ? activeContext.profileSubjectId
        : ref.read(currentUserIdProvider);
    final resolvedPersonaId = personaId ?? activeContext.subAccountId;
    final optimistic = CommentDto(
      id: 'pending_${DateTime.now().millisecondsSinceEpoch}',
      postId: postId,
      authorId: resolvedProfileSubjectId,
      content: content,
      replyToCommentId: replyToCommentId,
      personaId: resolvedPersonaId.isEmpty ? null : resolvedPersonaId,
      displayName: activeContext.displayName,
      avatarUrl: activeContext.avatarUrl,
      createdAt: DateTime.now(),
    );
    state = state.copyWith(
      comments: [optimistic, ...state.comments],
      pendingComments: [...state.pendingComments, optimistic],
    );
    try {
      final confirmed = await _repo.createComment(
        postId: postId,
        content: content,
        replyToCommentId: replyToCommentId,
        personaId: resolvedPersonaId.isEmpty ? null : resolvedPersonaId,
        profileSubjectId: resolvedProfileSubjectId,
        personaContextVersion: activeContext.personaContextVersion,
      );
      state = state.copyWith(
        comments: state.comments
            .map((c) => c.id == optimistic.id ? confirmed : c)
            .toList(),
        pendingComments: state.pendingComments
            .where((c) => c.id != optimistic.id)
            .toList(),
      );
      return confirmed;
    } catch (e) {
      state = state.copyWith(
        comments: state.comments.where((c) => c.id != optimistic.id).toList(),
        pendingComments: state.pendingComments
            .where((c) => c.id != optimistic.id)
            .toList(),
      );
      rethrow;
    }
  }

  Future<void> deleteComment(String commentId) async {
    final original = state.comments;
    state = state.copyWith(
      comments: state.comments.where((c) => c.id != commentId).toList(),
    );
    try {
      await _repo.deleteComment(postId: postId, commentId: commentId);
    } catch (e) {
      state = state.copyWith(comments: original);
      rethrow;
    }
  }

  Future<void> toggleLike(String commentId) async {
    final isLiked = state.likedCommentIds.contains(commentId);
    final updatedLikes = Set<String>.from(state.likedCommentIds);
    if (isLiked) {
      updatedLikes.remove(commentId);
    } else {
      updatedLikes.add(commentId);
    }
    final delta = isLiked ? -1 : 1;
    state = state.copyWith(
      likedCommentIds: updatedLikes,
      comments: state.comments.map((c) {
        if (c.id == commentId) {
          return c.copyWith(likeCount: c.likeCount + delta);
        }
        return c;
      }).toList(),
    );
    try {
      if (isLiked) {
        await _repo.unlikeComment(commentId: commentId);
      } else {
        await _repo.likeComment(commentId: commentId);
      }
    } catch (e) {
      if (isLiked) {
        updatedLikes.add(commentId);
      } else {
        updatedLikes.remove(commentId);
      }
      state = state.copyWith(
        likedCommentIds: updatedLikes,
        comments: state.comments.map((c) {
          if (c.id == commentId) {
            return c.copyWith(likeCount: c.likeCount - delta);
          }
          return c;
        }).toList(),
      );
    }
  }
}

final commentProviderFamily =
    NotifierProvider.autoDispose.family<CommentNotifier, CommentState, String>(
  CommentNotifier.new,
);
