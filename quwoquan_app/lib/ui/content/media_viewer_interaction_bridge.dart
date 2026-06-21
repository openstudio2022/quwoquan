import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/auth/auth_session.dart';
import 'package:quwoquan_app/core/models/media_viewer_extra.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';
import 'package:quwoquan_app/ui/discovery/providers/discovery_state.dart';

MediaViewerInteractionSnapshot buildMediaViewerInteractionSnapshot({
  required Iterable<PostBaseDto> posts,
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
      .map((post) => post.subAccountId)
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
    final profileId = post.subAccountId;
    if (profileId.isNotEmpty &&
        (relationshipState.isFollowing(profileId) ||
            discoveryState.followingUsers.contains(profileId))) {
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
      .mergeInteractionSnapshot(snapshot);
  ref
      .read(postInteractionStateProvider.notifier)
      .mergeInteractionSnapshot(snapshot);
  ref
      .read(discoveryStateProvider.notifier)
      .applyMediaViewerResult(MediaViewerResult.fromSnapshot(snapshot));
}

void applyConfirmedInteractionPost(WidgetRef ref, PostBaseDto post) {
  ref
      .read(postInteractionStateProvider.notifier)
      .applyConfirmedCounters(
        post.id,
        shareCount: post.shareCount,
        commentCount: post.commentCount,
      );
  ref
      .read(discoveryStateProvider.notifier)
      .setShareCount(post.id, post.shareCount);
}

void applyConfirmedInteractionPosts(
  WidgetRef ref,
  Iterable<PostBaseDto> posts,
) {
  ref.read(postInteractionStateProvider.notifier).applyConfirmedPosts(posts);
  final discoveryNotifier = ref.read(discoveryStateProvider.notifier);
  for (final post in posts) {
    discoveryNotifier.setShareCount(post.id, post.shareCount);
  }
}

void applyMediaViewerResultToInteractionState(
  WidgetRef ref,
  MediaViewerResult result,
) {
  ref.read(userRelationshipStateProvider.notifier).applyViewerResult(result);
  ref.read(postInteractionStateProvider.notifier).applyViewerResult(result);
  ref.read(discoveryStateProvider.notifier).applyMediaViewerResult(result);
}

bool effectivePostLiked(WidgetRef ref, String postId) {
  final postInteraction = ref.read(postInteractionStateProvider);
  if (postInteraction.hasLikeStateFor(postId)) {
    return postInteraction.isLiked(postId);
  }
  return ref.read(discoveryStateProvider).likedPosts.contains(postId);
}

bool effectiveProfileFollowing(WidgetRef ref, String subAccountId) {
  final relationshipState = ref.read(userRelationshipStateProvider);
  if (relationshipState.hasRelationshipStateFor(subAccountId)) {
    return relationshipState.isFollowing(subAccountId);
  }
  return ref.read(discoveryStateProvider).followingUsers.contains(subAccountId);
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
      .read(discoveryStateProvider.notifier)
      .setLikeState(postId, isLiked, likeCount: likeCount);
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
  required String subAccountId,
  required bool previousFollowing,
  required bool isFollowing,
}) {
  if (!ref.read(authSessionControllerProvider).isAuthenticated) {
    return;
  }
  ref
      .read(userRelationshipStateProvider.notifier)
      .setFollowing(subAccountId, isFollowing);
  ref
      .read(discoveryStateProvider.notifier)
      .setFollowState(subAccountId, isFollowing);
  ref
      .read(clientStateSyncOutboxProvider.notifier)
      .enqueueFollow(
        subAccountId: subAccountId,
        currentFollowing: previousFollowing,
        shouldFollow: isFollowing,
      );
}

Future<bool> syncPostShareIntent(
  WidgetRef ref, {
  required String postId,
  required int baselineShareCount,
}) async {
  // 分享为「游客设备态可写」：游客与登录用户均可写入权威分享记录。云侧按
  // deviceActorId（游客）/ userId（登录）独立累加、不并账；设备头由
  // CloudRequestHeaders 统一注入。
  ref
      .read(postInteractionStateProvider.notifier)
      .stageOptimisticShare(postId, baseShareCount: baselineShareCount);
  ref
      .read(discoveryStateProvider.notifier)
      .setShareCount(postId, baselineShareCount + 1);
  try {
    final changed = await ref
        .read(contentRepositoryProvider)
        .sharePost(postId: postId);
    if (!changed) {
      ref
          .read(postInteractionStateProvider.notifier)
          .rollbackOptimisticShare(
            postId,
            baseShareCount: baselineShareCount,
            isShared: true,
          );
      ref
          .read(discoveryStateProvider.notifier)
          .setShareCount(postId, baselineShareCount);
    }
    return changed;
  } catch (_) {
    ref
        .read(postInteractionStateProvider.notifier)
        .rollbackOptimisticShare(
          postId,
          baseShareCount: baselineShareCount,
          isShared: false,
        );
    ref
        .read(discoveryStateProvider.notifier)
        .setShareCount(postId, baselineShareCount);
    rethrow;
  }
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
