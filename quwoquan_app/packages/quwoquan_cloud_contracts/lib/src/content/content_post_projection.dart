/// 纯 Dart 内容投影，不依赖 App DTO 或 JSON Map。
final class ContentPostProjection {
  ContentPostProjection({
    required this.postId,
    required this.contentType,
    this.contentIdentity,
    this.assistantUsePolicy = 'inherit',
    this.authorId,
    this.authorDisplayName,
    this.authorAvatarUrl,
    this.authorBackgroundUrl,
    this.authorRoleLabel,
    Iterable<String> authorIdentityTags = const <String>[],
    this.authorVerified = false,
    this.title,
    this.body,
    this.summary,
    this.coverUrl,
    this.articleTemplate,
    this.articleFontPreset,
    Iterable<String> mediaUrls = const <String>[],
    this.videoUrl,
    this.mediaAssetId,
    this.mediaAssetVersion,
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    this.thumbnailUrl,
    this.width,
    this.height,
    this.durationMs,
    this.likeCount = 0,
    this.commentCount = 0,
    this.shareCount = 0,
    this.createdAt,
    this.updatedAt,
    this.publishedAt,
    this.contentVertical,
    this.recallPath,
    this.supplySource,
    Iterable<ContentPostIntersectionReason>? intersectionReasons,
  }) : authorIdentityTags = List<String>.unmodifiable(authorIdentityTags),
       mediaUrls = List<String>.unmodifiable(mediaUrls),
       intersectionReasons = intersectionReasons == null
           ? null
           : List<ContentPostIntersectionReason>.unmodifiable(
               intersectionReasons,
             );

  final String postId;
  final String contentType;
  final String? contentIdentity;
  final String assistantUsePolicy;
  final String? authorId;
  final String? authorDisplayName;
  final String? authorAvatarUrl;
  final String? authorBackgroundUrl;
  final String? authorRoleLabel;
  final List<String> authorIdentityTags;
  final bool authorVerified;
  final String? title;
  final String? body;
  final String? summary;
  final String? coverUrl;
  final String? articleTemplate;
  final String? articleFontPreset;
  final List<String> mediaUrls;
  final String? videoUrl;
  final String? mediaAssetId;
  final int? mediaAssetVersion;
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final String? thumbnailUrl;
  final int? width;
  final int? height;
  final int? durationMs;
  final int likeCount;
  final int commentCount;
  final int shareCount;
  final DateTime? createdAt;
  final DateTime? updatedAt;
  final DateTime? publishedAt;
  final String? contentVertical;
  final String? recallPath;
  final String? supplySource;
  final List<ContentPostIntersectionReason>? intersectionReasons;
}

final class ContentPostIntersectionReason {
  const ContentPostIntersectionReason({
    this.kind = '',
    this.primaryText = '',
    this.secondaryText = '',
    this.strength = 0,
  });

  final String kind;
  final String primaryText;
  final String secondaryText;
  final double strength;
}
