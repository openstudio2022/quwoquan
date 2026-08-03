part of 'works_immersive_viewer.dart';

extension _WorksImmersiveViewerSocialActions on _WorksImmersiveViewerState {
  void _onLike(ContentPostViewData post) {
    runWhenLoggedIn(ref, context, AuthGateReason.like, () {
      final isLiked = effectivePostLiked(ref, post.id);
      final currentCount = effectivePostLikeCount(
        ref,
        post.id,
        fallback: post.likeCount,
      );
      final nextLiked = !isLiked;
      final nextLikeCount = nextLiked
          ? currentCount + 1
          : (currentCount - 1).clamp(0, 1 << 31).toInt();
      syncPostLikeIntent(
        ref,
        postId: post.id,
        previousLiked: isLiked,
        isLiked: nextLiked,
        likeCount: nextLikeCount,
      );
    });
  }

  void _onFollow(ContentPostViewData post) {
    runWhenLoggedIn(ref, context, AuthGateReason.follow, () {
      final subjectId = post.personaId;
      final wasFollowing = effectiveProfileFollowing(ref, subjectId);
      final nextFollowing = !wasFollowing;
      syncProfileFollowIntent(
        ref,
        personaId: subjectId,
        previousFollowing: wasFollowing,
        isFollowing: nextFollowing,
        sourceSurfaceId: AppUiSurfaces.workBrowser.id,
      );
    });
  }
}
