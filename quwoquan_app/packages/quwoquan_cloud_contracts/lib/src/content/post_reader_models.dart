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
    Iterable<String> imageUrls = const <String>[],
    this.videoUrl,
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
       imageUrls = List<String>.unmodifiable(imageUrls),
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
  final List<String> imageUrls;
  final String? videoUrl;
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

/// 保留详情扩展中的动态 JSON 结构，但不把 `Map<String, dynamic>` 暴露给合同调用方。
sealed class ContentPostStructuredValue {
  const ContentPostStructuredValue();
}

final class ContentPostStructuredObject extends ContentPostStructuredValue {
  ContentPostStructuredObject(Map<String, ContentPostStructuredValue> fields)
    : fields = Map<String, ContentPostStructuredValue>.unmodifiable(fields);

  final Map<String, ContentPostStructuredValue> fields;
}

final class ContentPostStructuredArray extends ContentPostStructuredValue {
  ContentPostStructuredArray(Iterable<ContentPostStructuredValue> values)
    : values = List<ContentPostStructuredValue>.unmodifiable(values);

  final List<ContentPostStructuredValue> values;
}

final class ContentPostStructuredText extends ContentPostStructuredValue {
  const ContentPostStructuredText(this.value);

  final String value;
}

final class ContentPostStructuredNumber extends ContentPostStructuredValue {
  const ContentPostStructuredNumber(this.value);

  final num value;
}

final class ContentPostStructuredBoolean extends ContentPostStructuredValue {
  const ContentPostStructuredBoolean(this.value);

  final bool value;
}

final class ContentPostStructuredNull extends ContentPostStructuredValue {
  const ContentPostStructuredNull();
}

final class ContentPostEntityMention {
  const ContentPostEntityMention({
    required this.subjectType,
    required this.subjectId,
    required this.displayName,
    required this.rangeStart,
    required this.rangeEnd,
  });

  final String subjectType;
  final String subjectId;
  final String displayName;
  final int rangeStart;
  final int rangeEnd;
}

/// GET post 的详情切片：基础内容投影与详情扩展均是纯 Dart 类型。
final class ContentPostDetailSlice {
  ContentPostDetailSlice({
    required this.post,
    this.isOfficial,
    this.badge,
    this.articleTemplate,
    this.articleFontPreset,
    this.articleMarkdown,
    this.articleMarkdownVersion,
    this.articleMarkdownDigest,
    this.articleAssetManifest,
    this.articleRenderProfile,
    this.contentVertical,
    this.paperThemeMode,
    this.paperTexture,
    Iterable<ContentPostEntityMention> entityMentions =
        const <ContentPostEntityMention>[],
    this.coverUrl,
    Iterable<String>? tagRefs,
    this.visibility,
  }) : entityMentions = List<ContentPostEntityMention>.unmodifiable(
         entityMentions,
       ),
       tagRefs = tagRefs == null ? null : List<String>.unmodifiable(tagRefs);

  final ContentPostProjection post;
  final bool? isOfficial;
  final String? badge;
  final String? articleTemplate;
  final String? articleFontPreset;
  final String? articleMarkdown;
  final String? articleMarkdownVersion;
  final String? articleMarkdownDigest;
  final ContentPostStructuredObject? articleAssetManifest;
  final ContentPostStructuredObject? articleRenderProfile;
  final String? contentVertical;
  final String? paperThemeMode;
  final String? paperTexture;
  final List<ContentPostEntityMention> entityMentions;
  final String? coverUrl;
  final List<String>? tagRefs;
  final String? visibility;
}

/// ListUserPosts 的分页切片。
final class ContentAuthorPostPageSlice {
  ContentAuthorPostPageSlice({
    required Iterable<ContentPostProjection> items,
    this.nextCursor,
    this.totalCount,
  }) : items = List<ContentPostProjection>.unmodifiable(items);

  final List<ContentPostProjection> items;
  final String? nextCursor;
  final int? totalCount;
}
