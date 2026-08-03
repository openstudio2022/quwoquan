import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 CircleFeedItemView 的 canonical Post 字段一次映射为 App ViewData。
final class CircleFeedPostProjectionMapper {
  const CircleFeedPostProjectionMapper();

  ContentPostViewData toDto(CircleFeedItemView projection) {
    return ContentPostViewData.fromWire(
      ContentPostProjection(
        postId: projection.postId,
        contentType: projection.contentType,
        contentIdentity: projection.contentIdentity,
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
        contentVertical: projection.contentVertical,
        recallPath: projection.recallPath,
        supplySource: projection.supplySource,
      ),
    );
  }
}
