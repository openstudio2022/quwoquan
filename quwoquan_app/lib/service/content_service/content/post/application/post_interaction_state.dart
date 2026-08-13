import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_interaction_state.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/platform/storage/client_interaction_state_store.dart';

const String _postInteractionStateStorageKey = 'post_interaction_state';

class PostInteractionStateNotifier extends Notifier<PostInteractionState> {
  @override
  PostInteractionState build() {
    unawaited(_hydratePersistedState());
    return const PostInteractionState();
  }

  Future<void> _hydratePersistedState() async {
    final raw = await readPersistedInteractionMap(
      _postInteractionStateStorageKey,
    );
    if (!ref.mounted) {
      return;
    }
    if (raw == null) {
      return;
    }
    state = PostInteractionState.fromMap(raw);
  }

  void setLiked(String postId, bool isLiked, {int? likeCount}) {
    final nextLiked = Set<String>.from(state.likedPostIds);
    final nextCounts = Map<String, int>.from(state.likeCounts);
    if (isLiked) {
      nextLiked.add(postId);
    } else {
      nextLiked.remove(postId);
    }
    if (likeCount != null) {
      nextCounts[postId] = likeCount;
    }
    state = state.copyWith(likedPostIds: nextLiked, likeCounts: nextCounts);
    unawaited(_persistState());
  }

  void applyConfirmedCounters(
    String postId, {
    int? shareCount,
    int? commentCount,
  }) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    if (shareCount != null) {
      nextConfirmedShareCounts[postId] = shareCount;
    }
    if (commentCount != null) {
      nextConfirmedCommentCounts[postId] = commentCount;
      nextPendingCommentDeltas.remove(postId);
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void setShareCount(String postId, int shareCount) {
    applyConfirmedCounters(postId, shareCount: shareCount);
  }

  void setCommentCount(String postId, int commentCount) {
    applyConfirmedCounters(postId, commentCount: commentCount);
  }

  /// 以服务端权威投影收敛本地互动态。
  ///
  /// - share/comment 计数：无条件采纳权威值。
  /// - 点赞态：仅当 wire 附着了 viewer 态（`viewerLiked != null`）且该 post
  ///   没有待同步 like 意图（[pendingLikePostIds]）时 hydrate；null 表示本次
  ///   响应未附着 viewer 态，不得据此回滚本地状态；本地 pending 意图优先。
  void applyConfirmedPosts(
    Iterable<ContentPostViewData> posts, {
    Set<String> pendingLikePostIds = const <String>{},
  }) {
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    final nextLiked = Set<String>.from(state.likedPostIds);
    var likedChanged = false;
    for (final post in posts) {
      if (post.id.trim().isEmpty) {
        continue;
      }
      nextConfirmedShareCounts[post.id] = post.shareCount;
      nextConfirmedCommentCounts[post.id] = post.commentCount;
      nextPendingCommentDeltas.remove(post.id);
      final viewerLiked = post.viewerLiked;
      if (viewerLiked != null && !pendingLikePostIds.contains(post.id)) {
        final changed = viewerLiked
            ? nextLiked.add(post.id)
            : nextLiked.remove(post.id);
        likedChanged = likedChanged || changed;
      }
    }
    state = state.copyWith(
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
      likedPostIds: likedChanged ? nextLiked : null,
    );
    unawaited(_persistState());
  }

  void stageOptimisticComment(
    String postId, {
    required int baseCommentCount,
    required int delta,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedCommentCounts);
    final nextPending = Map<String, int>.from(state.pendingCommentDeltas);
    nextConfirmed.putIfAbsent(postId, () => baseCommentCount);
    nextPending[postId] = (nextPending[postId] ?? 0) + delta;
    state = state.copyWith(
      confirmedCommentCounts: nextConfirmed,
      pendingCommentDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void rollbackOptimisticComment(
    String postId, {
    required int baseCommentCount,
    required int delta,
  }) {
    final nextConfirmed = Map<String, int>.from(state.confirmedCommentCounts);
    final nextPending = Map<String, int>.from(state.pendingCommentDeltas);
    nextConfirmed.putIfAbsent(postId, () => baseCommentCount);
    final reverted = (nextPending[postId] ?? 0) - delta;
    if (reverted == 0) {
      nextPending.remove(postId);
    } else {
      nextPending[postId] = reverted;
    }
    state = state.copyWith(
      confirmedCommentCounts: nextConfirmed,
      pendingCommentDeltas: nextPending,
    );
    unawaited(_persistState());
  }

  void mergeInteractionState(PostInteractionInput input) {
    final scopePostIds = input.effectiveScopePostIds;
    if (scopePostIds.isEmpty) {
      return;
    }
    final nextLiked = Set<String>.from(state.likedPostIds);
    final nextLikeCounts = Map<String, int>.from(state.likeCounts);
    final nextConfirmedShareCounts = Map<String, int>.from(
      state.confirmedShareCounts,
    );
    final nextConfirmedCommentCounts = Map<String, int>.from(
      state.confirmedCommentCounts,
    );
    final nextPendingCommentDeltas = Map<String, int>.from(
      state.pendingCommentDeltas,
    );
    for (final postId in scopePostIds) {
      if (input.likedPostIds.contains(postId)) {
        nextLiked.add(postId);
      } else {
        nextLiked.remove(postId);
      }
      final likeCount = input.likeCounts[postId];
      if (likeCount != null) {
        nextLikeCounts[postId] = likeCount;
      }
      final shareCount = input.shareCounts[postId];
      if (shareCount != null) {
        nextConfirmedShareCounts[postId] = shareCount;
      }
      final commentCount = input.commentCounts[postId];
      if (commentCount != null) {
        nextConfirmedCommentCounts[postId] = commentCount;
        nextPendingCommentDeltas.remove(postId);
      }
    }
    state = state.copyWith(
      likedPostIds: nextLiked,
      likeCounts: nextLikeCounts,
      confirmedShareCounts: nextConfirmedShareCounts,
      confirmedCommentCounts: nextConfirmedCommentCounts,
      pendingCommentDeltas: nextPendingCommentDeltas,
    );
    unawaited(_persistState());
  }

  void applyInteractionState(PostInteractionInput input) {
    mergeInteractionState(input);
  }

  Future<void> _persistState() async {
    await writePersistedInteractionMap(
      _postInteractionStateStorageKey,
      state.toMap(),
    );
  }
}
