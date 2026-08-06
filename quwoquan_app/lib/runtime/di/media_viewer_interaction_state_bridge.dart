import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/post_interaction_state.dart';
import 'package:quwoquan_app/runtime/di/post_interaction_state_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/client_state_sync_dependencies.dart';
import 'package:quwoquan_app/service/user_service/relationship/persona_relationship/application/public/user_relationship_state.dart';
import 'package:quwoquan_app/runtime/di/user_relationship_state_dependencies.dart';

UserRelationshipInteractionInput _userRelationshipInput(
  MediaViewerInteractionSnapshot snapshot,
) {
  return UserRelationshipInteractionInput(
    scopePersonaIds: snapshot.effectiveScopeProfileIds,
    followingPersonaIds: snapshot.followingUsers,
  );
}

PostInteractionInput _postInteractionInput(
  MediaViewerInteractionSnapshot snapshot,
) {
  return PostInteractionInput(
    scopePostIds: snapshot.effectiveScopePostIds,
    likedPostIds: snapshot.likedPosts,
    likeCounts: snapshot.postLikesCount,
    shareCounts: snapshot.postSharesCount,
    commentCounts: snapshot.postCommentCount,
  );
}

MediaViewerInteractionSnapshot buildMediaViewerInteractionSnapshot({
  required Iterable<ContentPostViewData> posts,
  required UserRelationshipState relationshipState,
  required PostInteractionState postInteractionState,
}) {
  final scopedPosts = posts.toList(growable: false);
  final scopePostIds = scopedPosts
      .map((post) => post.id)
      .where((id) => id.trim().isNotEmpty)
      .toSet();
  final scopeProfileIds = scopedPosts
      .map((post) => post.personaId)
      .where((id) => id.trim().isNotEmpty)
      .toSet();
  final likedPosts = <String>{};
  final followingUsers = <String>{};
  final postLikesCount = <String, int>{};
  final postSharesCount = <String, int>{};
  final postCommentCount = <String, int>{};

  for (final post in scopedPosts) {
    final id = post.id;
    if (postInteractionState.isLiked(id)) {
      likedPosts.add(id);
    }
    postLikesCount[id] = postInteractionState.likeCountFor(
      id,
      fallback: post.likeCount,
    );
    postSharesCount[id] = postInteractionState.shareCountFor(
      id,
      fallback: post.shareCount,
    );
    postCommentCount[id] = postInteractionState.commentCountFor(
      id,
      fallback: post.commentCount,
    );
    final profileId = post.personaId;
    if (profileId.isNotEmpty && relationshipState.isFollowing(profileId)) {
      followingUsers.add(profileId);
    }
  }

  return MediaViewerInteractionSnapshot(
    scopePostIds: scopePostIds,
    scopeProfileIds: scopeProfileIds,
    followingUsers: followingUsers,
    likedPosts: likedPosts,
    postLikesCount: postLikesCount,
    postSharesCount: postSharesCount,
    postCommentCount: postCommentCount,
  );
}

void primeMediaViewerInteractionSnapshot(
  WidgetRef ref,
  MediaViewerInteractionSnapshot snapshot,
) {
  ref
      .read(userRelationshipStateProvider.notifier)
      .mergeInteractionState(_userRelationshipInput(snapshot));
  ref
      .read(postInteractionStateProvider.notifier)
      .mergeInteractionState(_postInteractionInput(snapshot));
}

void applyConfirmedInteractionPost(WidgetRef ref, ContentPostViewData post) {
  ref
      .read(postInteractionStateProvider.notifier)
      .applyConfirmedCounters(
        post.id,
        shareCount: post.shareCount,
        commentCount: post.commentCount,
      );
}

void applyConfirmedInteractionPosts(
  WidgetRef ref,
  Iterable<ContentPostViewData> posts,
) {
  ref.read(postInteractionStateProvider.notifier).applyConfirmedPosts(posts);
}

void applyMediaViewerResultToInteractionState(
  WidgetRef ref,
  MediaViewerResult result,
) {
  ref
      .read(userRelationshipStateProvider.notifier)
      .applyInteractionState(_userRelationshipInput(result));
  ref
      .read(postInteractionStateProvider.notifier)
      .applyInteractionState(_postInteractionInput(result));
}

bool effectivePostLiked(WidgetRef ref, String postId) {
  final postInteraction = ref.read(postInteractionStateProvider);
  if (postInteraction.hasLikeStateFor(postId)) {
    return postInteraction.isLiked(postId);
  }
  return false;
}

bool effectiveProfileFollowing(WidgetRef ref, String personaId) {
  final relationshipState = ref.read(userRelationshipStateProvider);
  if (relationshipState.hasRelationshipStateFor(personaId)) {
    return relationshipState.isFollowing(personaId);
  }
  return false;
}

int effectivePostLikeCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  final postInteraction = ref.read(postInteractionStateProvider);
  return postInteraction.likeCountFor(postId, fallback: fallback);
}

int effectivePostShareCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  final postInteraction = ref.read(postInteractionStateProvider);
  return postInteraction.shareCountFor(postId, fallback: fallback);
}

int effectivePostCommentCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  final postInteraction = ref.read(postInteractionStateProvider);
  return postInteraction.commentCountFor(postId, fallback: fallback);
}

void syncPostLikeIntent(
  WidgetRef ref, {
  required String postId,
  required bool previousLiked,
  required bool isLiked,
  required int likeCount,
}) {
  // 点赞为「游客设备态可写」：游客与登录用户均可写本地乐观态 + outbox。
  // 云侧按 deviceActorId（游客）/ userId（登录）独立计数、不并账；设备头由
  // CloudRequestHeaders 统一注入，故此处无需区分登录态。
  ref
      .read(postInteractionStateProvider.notifier)
      .setLiked(postId, isLiked, likeCount: likeCount);
  ref
      .read(clientStateSyncOutboxProvider.notifier)
      .enqueuePostLike(
        postId: postId,
        currentLiked: previousLiked,
        isLiked: isLiked,
      );
}

void syncProfileFollowIntent(
  WidgetRef ref, {
  required String personaId,
  required bool previousFollowing,
  required bool isFollowing,
  required String sourceSurfaceId,
}) {
  if (!ref.read(authSessionControllerProvider).isAuthenticated) {
    return;
  }
  ref
      .read(userRelationshipStateProvider.notifier)
      .setFollowing(personaId, isFollowing);
  ref
      .read(clientStateSyncOutboxProvider.notifier)
      .enqueueFollow(
        personaId: personaId,
        currentFollowing: previousFollowing,
        shouldFollow: isFollowing,
        sourceSurfaceId: sourceSurfaceId,
      );
}

void syncPostCommentCount(
  WidgetRef ref, {
  required String postId,
  required int commentCount,
}) {
  ref
      .read(postInteractionStateProvider.notifier)
      .applyConfirmedCounters(postId, commentCount: commentCount);
}
