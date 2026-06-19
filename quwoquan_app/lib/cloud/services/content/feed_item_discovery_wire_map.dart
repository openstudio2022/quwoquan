import 'package:quwoquan_app/cloud/runtime/generated/content/feed_item_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_text_span.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_visual.g.dart';

/// 将 [FeedItemDto] 还原为发现区 / postBaseDtoFromMap 兼容的 wire 形状（含别名键）。
extension FeedItemDtoDiscoveryWireMap on FeedItemDto {
  Map<String, dynamic> toDiscoveryWireMap() {
    final createdIso = createdAt.toUtc().toIso8601String();
    final updatedIso = updatedAt?.toUtc().toIso8601String();
    final publishedIso = publishedAt?.toUtc().toIso8601String();
    return <String, dynamic>{
      'postId': id,
      '_id': id,
      'contentType': type,
      'contentIdentity': identity,
      'identity': identity,
      'assistantUsePolicy': assistantUsePolicy,
      'authorId': authorId,
      'authorNickname': displayName,
      'displayName': displayName,
      'authorAvatarUrl': avatarUrl,
      'avatarUrl': avatarUrl,
      if (authorRoleLabel.trim().isNotEmpty) 'authorRoleLabel': authorRoleLabel,
      if (authorIdentityTags.isNotEmpty)
        'authorIdentityTags': authorIdentityTags,
      'authorVerified': authorVerified,
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
      'shareCount': shareCount,
      'createdAt': createdIso,
      ...(updatedIso == null
          ? const <String, dynamic>{}
          : {'updatedAt': updatedIso}),
      ...(publishedIso == null
          ? const <String, dynamic>{}
          : {'publishedAt': publishedIso}),
      if (authorBackgroundUrl != null && authorBackgroundUrl!.trim().isNotEmpty)
        'authorBackgroundUrl': authorBackgroundUrl,
      if (articleTemplate != null && articleTemplate!.trim().isNotEmpty)
        'articleTemplate': articleTemplate,
      if (articleFontPreset != null && articleFontPreset!.trim().isNotEmpty)
        'articleFontPreset': articleFontPreset,
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
      if (visibility != null && visibility!.trim().isNotEmpty)
        'visibility': visibility,
      if (intersectionReasons != null && intersectionReasons!.isNotEmpty)
        'intersectionReasons': intersectionReasons!
            .map(_intersectionReasonToWireMap)
            .toList(growable: false),
    };
  }
}

Map<String, dynamic> _intersectionReasonToWireMap(IntersectionReason reason) {
  return <String, dynamic>{
    ...reason.toMap(),
    'primarySpans': reason.primarySpans
        .map(_intersectionTextSpanToWireMap)
        .toList(growable: false),
    'sampleVisuals': reason.sampleVisuals
        .map(_intersectionVisualToWireMap)
        .toList(growable: false),
  };
}

Map<String, dynamic> _intersectionTextSpanToWireMap(IntersectionTextSpan span) {
  return <String, dynamic>{
    'text': span.text,
    'role': span.role,
    if (span.target != null) 'target': span.target!.toMap(),
  };
}

Map<String, dynamic> _intersectionVisualToWireMap(IntersectionVisual visual) {
  return <String, dynamic>{
    'assetKind': visual.assetKind,
    'imageUrl': visual.imageUrl,
    'displayName': visual.displayName,
    if (visual.target != null) 'target': visual.target!.toMap(),
  };
}
