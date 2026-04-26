import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';

/// 将 [FeedItemDto] 还原为发现区 / postBaseDtoFromMap 兼容的 wire 形状（含别名键）。
extension FeedItemDtoDiscoveryWireMap on FeedItemDto {
  Map<String, dynamic> toDiscoveryWireMap() {
    final iso = createdAt.toUtc().toIso8601String();
    return <String, dynamic>{
      'postId': id,
      '_id': id,
      'contentType': type,
      'contentIdentity': identity,
      'identity': identity,
      'assistantUsePolicy': assistantUsePolicy,
      'authorId': authorId,
      'authorProfileSubjectId': authorProfileSubjectId,
      'profileSubjectId': authorProfileSubjectId,
      'authorNickname': displayName,
      'displayName': displayName,
      'authorAvatarUrl': avatarUrl,
      'avatarUrl': avatarUrl,
      if (title != null && title!.isNotEmpty) 'title': title,
      if (body != null && body!.isNotEmpty) 'body': body,
      if (summary != null && summary!.isNotEmpty) 'summary': summary,
      'coverUrl': coverUrl,
      'thumbnailUrl': thumbnailUrl,
      if (videoUrl != null && videoUrl!.isNotEmpty) 'videoUrl': videoUrl,
      'mediaUrls': imageUrls,
      'imageUrls': imageUrls,
      if (durationMs != null) 'durationMs': durationMs,
      if (width != null) 'width': width,
      if (height != null) 'height': height,
      'likeCount': likeCount,
      'commentCount': commentCount,
      'favoriteCount': favoriteCount,
      'shareCount': shareCount,
      'publishedAt': iso,
      'createdAt': iso,
      if (authorBackgroundUrl != null && authorBackgroundUrl!.trim().isNotEmpty)
        'authorBackgroundUrl': authorBackgroundUrl,
      if (articleTemplate != null && articleTemplate!.trim().isNotEmpty)
        'articleTemplate': articleTemplate,
      if (articleFontPreset != null && articleFontPreset!.trim().isNotEmpty)
        'articleFontPreset': articleFontPreset,
      if (articleDocument != null && articleDocument!.isNotEmpty)
        'articleDocument': articleDocument,
      if (articlePresentationVersion != null)
        'articlePresentationVersion': articlePresentationVersion,
      if (cards != null && cards!.isNotEmpty) 'cards': cards,
      if (circleSummaries != null && circleSummaries!.isNotEmpty)
        'circleSummaries': circleSummaries,
      if (circleIds != null && circleIds!.isNotEmpty) 'circleIds': circleIds,
      if (circleNames != null && circleNames!.isNotEmpty)
        'circleNames': circleNames,
      if (circleId != null && circleId!.trim().isNotEmpty) 'circleId': circleId,
      if (circleName != null && circleName!.trim().isNotEmpty)
        'circleName': circleName,
      if (tags != null && tags!.isNotEmpty) 'tags': tags,
      if (visibility != null && visibility!.trim().isNotEmpty)
        'visibility': visibility,
    };
  }
}
