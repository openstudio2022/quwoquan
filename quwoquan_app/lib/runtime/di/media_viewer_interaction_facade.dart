// 多对象媒体交互的唯一 runtime/di 组合门面。
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/di/media_viewer_interaction_state_bridge.dart'
    as interaction_state_bridge;
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';
import 'package:quwoquan_app/runtime/di/discovery_state_provider.dart';

MediaViewerInteractionSnapshot buildMediaViewerInteractionSnapshot({
  required Iterable<ContentPostViewData> posts,
  required DiscoveryUiState discoveryState,
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
    if (postInteractionState.isLiked(id) ||
        discoveryState.likedPosts.contains(id)) {
      likedPosts.add(id);
    }
    postLikesCount[id] = postInteractionState.likeCountFor(
      id,
      fallback: discoveryState.getPostLikesCount(id) > 0
          ? discoveryState.getPostLikesCount(id)
          : post.likeCount,
    );
    postSharesCount[id] = postInteractionState.shareCountFor(
      id,
      fallback: discoveryState.getPostSharesCount(id) > 0
          ? discoveryState.getPostSharesCount(id)
          : post.shareCount,
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
  interaction_state_bridge.primeMediaViewerInteractionSnapshot(ref, snapshot);
  ref
      .read(discoveryStateProvider.notifier)
      .applyMediaViewerResult(MediaViewerResult.fromSnapshot(snapshot));
}

void applyConfirmedInteractionPost(WidgetRef ref, ContentPostViewData post) {
  interaction_state_bridge.applyConfirmedInteractionPost(ref, post);
  ref
      .read(discoveryStateProvider.notifier)
      .setShareCount(post.id, post.shareCount);
}

void applyConfirmedInteractionPosts(
  WidgetRef ref,
  Iterable<ContentPostViewData> posts,
) {
  interaction_state_bridge.applyConfirmedInteractionPosts(ref, posts);
  final discoveryNotifier = ref.read(discoveryStateProvider.notifier);
  for (final post in posts) {
    discoveryNotifier.setShareCount(post.id, post.shareCount);
  }
}

void applyMediaViewerResultToInteractionState(
  WidgetRef ref,
  MediaViewerResult result,
) {
  interaction_state_bridge.applyMediaViewerResultToInteractionState(
    ref,
    result,
  );
  ref.read(discoveryStateProvider.notifier).applyMediaViewerResult(result);
}

bool effectivePostLiked(WidgetRef ref, String postId) {
  final postInteraction = ref.read(postInteractionStateProvider);
  if (postInteraction.hasLikeStateFor(postId)) {
    return postInteraction.isLiked(postId);
  }
  return ref.read(discoveryStateProvider).likedPosts.contains(postId);
}

bool effectiveProfileFollowing(WidgetRef ref, String personaId) {
  return ref.read(userRelationshipStateProvider).isFollowing(personaId);
}

int effectivePostLikeCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  final postInteraction = ref.read(postInteractionStateProvider);
  final discoveryState = ref.read(discoveryStateProvider);
  return postInteraction.likeCountFor(
    postId,
    fallback: discoveryState.getPostLikesCount(postId) > 0
        ? discoveryState.getPostLikesCount(postId)
        : fallback,
  );
}

int effectivePostShareCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  final postInteraction = ref.read(postInteractionStateProvider);
  final discoveryState = ref.read(discoveryStateProvider);
  return postInteraction.shareCountFor(
    postId,
    fallback: discoveryState.getPostSharesCount(postId) > 0
        ? discoveryState.getPostSharesCount(postId)
        : fallback,
  );
}

int effectivePostCommentCount(
  WidgetRef ref,
  String postId, {
  required int fallback,
}) {
  return interaction_state_bridge.effectivePostCommentCount(
    ref,
    postId,
    fallback: fallback,
  );
}

void syncPostLikeIntent(
  WidgetRef ref, {
  required String postId,
  required bool previousLiked,
  required bool isLiked,
  required int likeCount,
}) {
  interaction_state_bridge.syncPostLikeIntent(
    ref,
    postId: postId,
    previousLiked: previousLiked,
    isLiked: isLiked,
    likeCount: likeCount,
  );
  ref
      .read(discoveryStateProvider.notifier)
      .setLikeState(postId, isLiked, likeCount: likeCount);
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
  interaction_state_bridge.syncProfileFollowIntent(
    ref,
    personaId: personaId,
    previousFollowing: previousFollowing,
    isFollowing: isFollowing,
    sourceSurfaceId: sourceSurfaceId,
  );
}

void syncPostCommentCount(
  WidgetRef ref, {
  required String postId,
  required int commentCount,
}) {
  interaction_state_bridge.syncPostCommentCount(
    ref,
    postId: postId,
    commentCount: commentCount,
  );
}
