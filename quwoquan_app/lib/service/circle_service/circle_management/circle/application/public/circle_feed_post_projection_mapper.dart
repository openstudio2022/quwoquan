import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 CircleFeedItemView 的 canonical Post 字段一次映射为公开 App read view。
final class CircleFeedPostProjectionMapper {
  const CircleFeedPostProjectionMapper();

  ContentPostViewData toView(CircleFeedItemView projection) {
    return ContentPostViewData.fromWire(
      ContentPostProjection(
        postId: projection.postId,
        // 圈子投影的 contentType 仍是 wire string（契约尚未类型化），在
        // adapter 边界一次解成闭集；不下传裸字符串，也不放宽未知值。
        contentType: ContentType.fromWire(
          projection.contentType,
          'CircleFeedItemView.contentType',
        ),
        assistantUsePolicy: projection.assistantUsePolicy,
        authorId: projection.authorId,
        authorDisplayName: projection.authorDisplayName,
        authorAvatarUrl: projection.authorAvatarUrl,
        authorBackgroundUrl: projection.authorBackgroundUrl,
        authorRoleLabel: projection.authorRoleLabel,
        authorIdentityTags: projection.authorIdentityTags,
        authorVerified: projection.authorVerified,
        title: projection.title,
        body: projection.body,
        summary: projection.summary,
        coverUrl: projection.coverUrl,
        mediaUrls: projection.imageUrls,
        videoUrl: projection.videoUrl,
        thumbnailUrl: projection.thumbnailUrl,
        width: projection.width,
        height: projection.height,
        durationMs: projection.durationMs,
        likeCount: projection.likeCount,
        commentCount: projection.commentCount,
        shareCount: projection.shareCount,
        createdAt: projection.createdAt,
        updatedAt: projection.updatedAt,
        publishedAt: projection.publishedAt,
        recallPath: projection.recallPath,
        supplySource: projection.supplySource,
      ),
    );
  }
}
