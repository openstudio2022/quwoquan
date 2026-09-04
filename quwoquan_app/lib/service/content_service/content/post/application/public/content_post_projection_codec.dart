import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 App 展示投影重新绑定到 canonical generated Post projection。
///
/// 缓存与测试替身序列化 [ContentPostViewData] 时必须继续使用返回对象的
/// generated `toWire()`，不得自行维护第二套 presentation/wire 字段表。
ContentPostProjection contentPostProjectionFromViewData(
  ContentPostViewData source,
) {
  return ContentPostProjection(
    postId: source.id,
    contentType: source.type,
    contentIdentity: source.identity,
    assistantUsePolicy: source.assistantUsePolicy,
    authorId: source.authorId,
    authorDisplayName: source.displayName,
    authorAvatarUrl: source.avatarUrl,
    authorAvatarAssetId: source.authorAvatarAssetId,
    authorAvatarAccessMode: source.authorAvatarAccessMode,
    authorBackgroundUrl: source.authorBackgroundUrl,
    authorRoleLabel: source.authorRoleLabel,
    authorIdentityTags: source.authorIdentityTags,
    authorVerified: source.authorVerified,
    title: source.title,
    body: source.body,
    summary: source.summary,
    coverUrl: source.coverUrl,
    articleTemplate: source.articleTemplate,
    articleFontPreset: source.articleFontPreset,
    mediaUrls: source.imageUrls,
    videoUrl: source.videoUrl,
    mediaAssetId: source.mediaAssetId,
    mediaAssetVersion: source.mediaAssetVersion,
    mediaItems: source.mediaItems,
    hlsCmafMasterManifestUrl: source.hlsCmafMasterManifestUrl,
    hlsCmafDescriptorVersion: source.hlsCmafDescriptorVersion,
    thumbnailUrl: source.thumbnailUrl,
    width: source.width,
    height: source.height,
    durationMs: source.durationMs,
    likeCount: source.likeCount,
    commentCount: source.commentCount,
    shareCount: source.shareCount,
    createdAt: source.createdAt,
    updatedAt: source.updatedAt,
    publishedAt: source.publishedAt,
    recallPath: source.recallPath,
    supplySource: source.supplySource,
    intersectionReasons: source.intersectionReasons,
  );
}
