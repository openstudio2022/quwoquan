import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// 将 pure-Dart 云合同投影收口为 App 内容 DTO 的唯一边界。
///
/// `Map<String, dynamic>` 仅存在于本 mapper 内部，用于适配现有 generated DTO
/// factory；UI、Provider 与业务模型只消费强类型对象。
final class ContentPostProjectionMapper {
  const ContentPostProjectionMapper();

  PostBaseDto toDto(ContentPostProjection projection) {
    return postBaseDtoFromMap(toWire(projection));
  }

  Map<String, dynamic> toWire(ContentPostProjection projection) {
    final mediaUrls = projection.mediaUrls
        .where((url) => url.trim().isNotEmpty)
        .toList(growable: false);
    final isVideo = projection.contentType == 'video';
    final explicitVideoUrl = projection.videoUrl?.trim() ?? '';
    final videoUrl = explicitVideoUrl.isNotEmpty
        ? explicitVideoUrl
        : (isVideo && mediaUrls.isNotEmpty ? mediaUrls.first : null);
    return <String, dynamic>{
      'id': projection.postId,
      'type': projection.contentType,
      if (projection.contentIdentity != null)
        'identity': projection.contentIdentity,
      'assistantUsePolicy': projection.assistantUsePolicy,
      if (projection.authorId != null) 'authorId': projection.authorId,
      if (projection.authorDisplayName != null)
        'displayName': projection.authorDisplayName,
      if (projection.authorAvatarUrl != null)
        'avatarUrl': projection.authorAvatarUrl,
      if (projection.authorBackgroundUrl != null)
        'authorBackgroundUrl': projection.authorBackgroundUrl,
      if (projection.authorRoleLabel != null)
        'authorRoleLabel': projection.authorRoleLabel,
      'authorIdentityTags': projection.authorIdentityTags,
      'authorVerified': projection.authorVerified,
      if (projection.title != null) 'title': projection.title,
      if (projection.body != null) 'body': projection.body,
      if (projection.summary != null) 'summary': projection.summary,
      if (projection.coverUrl != null) 'coverUrl': projection.coverUrl,
      if (projection.articleTemplate != null)
        'articleTemplate': projection.articleTemplate,
      if (projection.articleFontPreset != null)
        'articleFontPreset': projection.articleFontPreset,
      'imageUrls': isVideo ? const <String>[] : mediaUrls,
      'videoUrl': ?videoUrl,
      if (projection.mediaAssetId != null)
        'mediaAssetId': projection.mediaAssetId,
      if (projection.mediaAssetVersion != null)
        'mediaAssetVersion': projection.mediaAssetVersion,
      if (projection.hlsCmafMasterManifestUrl != null)
        'hlsCmafMasterManifestUrl': projection.hlsCmafMasterManifestUrl,
      if (projection.hlsCmafDescriptorVersion != null)
        'hlsCmafDescriptorVersion': projection.hlsCmafDescriptorVersion,
      if (projection.thumbnailUrl != null)
        'thumbnailUrl': projection.thumbnailUrl,
      if (projection.width != null) 'width': projection.width,
      if (projection.height != null) 'height': projection.height,
      if (projection.durationMs != null) 'durationMs': projection.durationMs,
      'likeCount': projection.likeCount,
      'commentCount': projection.commentCount,
      'shareCount': projection.shareCount,
      if (projection.createdAt != null)
        'createdAt': projection.createdAt!.toUtc().toIso8601String(),
      if (projection.updatedAt != null)
        'updatedAt': projection.updatedAt!.toUtc().toIso8601String(),
      if (projection.publishedAt != null)
        'publishedAt': projection.publishedAt!.toUtc().toIso8601String(),
      if (projection.contentVertical != null)
        'contentVertical': projection.contentVertical,
      if (projection.recallPath != null) 'recallPath': projection.recallPath,
      if (projection.supplySource != null)
        'supplySource': projection.supplySource,
      if (projection.intersectionReasons != null)
        'intersectionReasons': projection.intersectionReasons!
            .map(
              (reason) => <String, dynamic>{
                'kind': reason.kind,
                'primaryText': reason.primaryText,
                'secondaryText': reason.secondaryText,
                'strength': reason.strength,
              },
            )
            .toList(growable: false),
    };
  }
}
