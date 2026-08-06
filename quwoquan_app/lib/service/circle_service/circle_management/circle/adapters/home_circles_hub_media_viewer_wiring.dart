import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_viewer_extra.dart';
import 'package:quwoquan_app/service/circle_service/circle_management/circle/application/public/circle_hub_feed_post_entry.dart';

/// 首页圈子沉浸查看器：从强类型页面模型构建旧沉浸器边界对象。
Map<String, MediaViewerPostWireRow> circleHubMediaViewerRowsByPostId(
  Iterable<CircleHubFeedPostEntry> viewerEntries,
) {
  return <String, MediaViewerPostWireRow>{
    for (final entry in viewerEntries)
      entry.postId: MediaViewerPostWireRow.fromViewData(
        entry.post,
        circleId: entry.circleId,
        likeCount: entry.likeCount,
        commentCount: entry.commentCount,
        shareCount: entry.shareCount,
        isLiked: entry.isLiked,
        isFollowingAuthor: entry.isFollowingAuthor,
      ),
  };
}

/// 将媒体查看器结果适配为 Circle 自有的纯互动快照输入。
void applyCircleHubMediaViewerResult(
  Iterable<CircleHubFeedPostEntry> entries,
  MediaViewerResult result,
) {
  for (final entry in entries) {
    entry.applyInteractionSnapshot(
      effectiveScopePostIds: result.effectiveScopePostIds,
      effectiveScopeProfileIds: result.effectiveScopeProfileIds,
      followingUsers: result.followingUsers,
      likedPosts: result.likedPosts,
      postLikesCount: result.postLikesCount,
      postSharesCount: result.postSharesCount,
      postCommentCount: result.postCommentCount,
    );
  }
}
