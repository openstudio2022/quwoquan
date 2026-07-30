import 'content_post_projection.dart';

export 'content_post_projection.dart';

/// 单篇内容详情中的统一媒体序列项。
///
/// 它保留服务端公开投影的媒体事实，供 Work Browser 读取；媒体 authority
/// 仍由 App runtime 注入，不能在这里拼接 URL。
final class ContentPostMediaItem {
  const ContentPostMediaItem({
    required this.kind,
    required this.url,
    this.mediaAssetId,
    this.mediaAssetVersion,
    this.hlsCmafMasterManifestUrl,
    this.hlsCmafDescriptorVersion,
    this.coverUrl,
    this.durationMs,
    this.width,
    this.height,
    this.title,
  });

  final String kind;
  final String url;
  final String? mediaAssetId;
  final int? mediaAssetVersion;
  final String? hlsCmafMasterManifestUrl;
  final int? hlsCmafDescriptorVersion;
  final String? coverUrl;
  final int? durationMs;
  final int? width;
  final int? height;
  final String? title;
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
    Iterable<ContentPostMediaItem> mediaItems = const <ContentPostMediaItem>[],
    this.isOfficial,
    this.badge,
    this.articleTemplate,
    this.articleFontPreset,
    this.articleMarkdown,
    this.markdownDialect,
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
    this.status = 'published',
    this.moderationStatus,
    this.visibility,
  }) : mediaItems = List<ContentPostMediaItem>.unmodifiable(mediaItems),
       entityMentions = List<ContentPostEntityMention>.unmodifiable(
         entityMentions,
       ),
       tagRefs = tagRefs == null ? null : List<String>.unmodifiable(tagRefs);

  final ContentPostProjection post;
  final List<ContentPostMediaItem> mediaItems;
  final bool? isOfficial;
  final String? badge;
  final String? articleTemplate;
  final String? articleFontPreset;
  final String? articleMarkdown;
  final String? markdownDialect;
  final String? articleMarkdownDigest;
  final ContentPostStructuredObject? articleAssetManifest;
  final ContentPostStructuredObject? articleRenderProfile;
  final String? contentVertical;
  final String? paperThemeMode;
  final String? paperTexture;
  final List<ContentPostEntityMention> entityMentions;
  final String? coverUrl;
  final List<String>? tagRefs;
  final String status;
  final String? moderationStatus;
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

/// 首页发现流的强类型分页投影与服务端归因上下文。
enum ContentDiscoveryFeedOutcome { content, empty }

enum ContentDiscoveryFeedEmptyReason {
  noActiveRelease,
  noEligibleContent,
  followingEmpty,
  continuationEnd,
}

final class ContentDiscoveryFeedPageSlice {
  ContentDiscoveryFeedPageSlice({
    required Iterable<ContentPostProjection> items,
    required this.outcome,
    this.emptyReason,
    Iterable<ContentPostStructuredObject> objectCards =
        const <ContentPostStructuredObject>[],
    this.nextCursor,
    this.previousCursor,
    this.paginationExpiresAt,
    this.feedRequestId,
    this.policyDigest,
    this.hasMore,
  }) : items = List<ContentPostProjection>.unmodifiable(items),
       objectCards = List<ContentPostStructuredObject>.unmodifiable(
         objectCards,
       );

  final List<ContentPostProjection> items;
  final ContentDiscoveryFeedOutcome outcome;
  final ContentDiscoveryFeedEmptyReason? emptyReason;
  final List<ContentPostStructuredObject> objectCards;
  final String? nextCursor;
  final String? previousCursor;
  final DateTime? paginationExpiresAt;
  final String? feedRequestId;
  final String? policyDigest;
  final bool? hasMore;
}
