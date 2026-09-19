import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/assistant_use_policy_codec.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Test/data-boundary projection of the authoritative service read model into
/// the canonical generated Content contract.
ContentPostProjection contentPostProjectionFromReadModelMap(
  Map<String, dynamic> source,
) {
  return ContentPostProjection(
    postId: _requiredText(source, 'postId'),
    contentType: ContentType.fromWire(
      _requiredText(source, 'contentType'),
      'ContentPostProjection.contentType',
    ),
    assistantUsePolicy: assistantUsePolicyFromWire(
      source['assistantUsePolicy'],
      'ContentPostProjection.assistantUsePolicy',
    ),
    authorId: _optionalText(source['authorId']),
    authorDisplayName: _optionalText(source['authorDisplayName']),
    authorAvatarUrl: _optionalText(source['authorAvatarUrl']),
    authorAvatarAssetId: _optionalText(source['authorAvatarAssetId']),
    authorAvatarAccessMode: _optionalAccessMode(
      source['authorAvatarAccessMode'],
      'ContentPostProjection.authorAvatarAccessMode',
    ),
    authorBackgroundUrl: _optionalText(source['authorBackgroundUrl']),
    authorRoleLabel: _optionalText(source['authorRoleLabel']),
    authorIdentityTags: _stringList(source['authorIdentityTags']),
    authorVerified: source['authorVerified'] as bool?,
    title: _optionalText(source['title']),
    body: _optionalText(source['body']),
    summary: _optionalText(source['summary']),
    coverUrl: _optionalText(source['coverUrl']),
    articleTemplate: _optionalText(source['articleTemplate']),
    articleFontPreset: _optionalText(source['articleFontPreset']),
    mediaUrls: _stringList(source['mediaUrls']),
    videoUrl: _optionalText(source['videoUrl']),
    mediaAssetId: _optionalText(source['mediaAssetId']),
    mediaAssetVersion: _optionalInt(source['mediaAssetVersion']),
    mediaItems: _mediaItems(source['mediaItems']),
    hlsCmafMasterManifestUrl: _optionalText(source['hlsCmafMasterManifestUrl']),
    hlsCmafDescriptorVersion: _optionalInt(source['hlsCmafDescriptorVersion']),
    thumbnailUrl: _optionalText(source['thumbnailUrl']),
    width: _optionalInt(source['width']),
    height: _optionalInt(source['height']),
    durationMs: _optionalInt(source['durationMs']),
    likeCount: _optionalInt(source['likeCount']) ?? 0,
    commentCount: _optionalInt(source['commentCount']) ?? 0,
    shareCount: _optionalInt(source['shareCount']) ?? 0,
    createdAt: _optionalDateTime(source['createdAt']),
    updatedAt: _optionalDateTime(source['updatedAt']),
    publishedAt: _optionalDateTime(source['publishedAt']),
    recallPath: _optionalText(source['recallPath']),
    supplySource: _optionalText(source['supplySource']),
    intersectionReasons: _intersectionReasons(source['intersectionReasons']),
  );
}

/// [source] 的 `openSurface` / `presentationRecipe` 只在 App 本地快照里出现；
/// canonical Post 投影不含展示轴，缺席即为未下发信封，不按内容类型补猜。
ContentPostViewData contentPostViewDataFromReadModelMap(
  Map<String, dynamic> source,
) => ContentPostViewData.fromWire(
  contentPostProjectionFromReadModelMap(source),
  openSurface: source['openSurface'] == null
      ? null
      : ContentUiSurface.fromWire(
          source['openSurface'],
          'ContentPostViewData.openSurface',
        ),
  presentationRecipe: source['presentationRecipe'] == null
      ? null
      : FeedPresentationRecipe.fromWire(
          source['presentationRecipe'],
          'ContentPostViewData.presentationRecipe',
        ),
);

Map<String, Object?> contentPostWireFromReadModelMap(
  Map<String, dynamic> source,
) => contentPostProjectionFromReadModelMap(source).toWire();

/// 发现流 items 的唯一混排信封；实体主页不再走 objectCards 旁路。
Map<String, Object?> contentListItemWireFromReadModelMap(
  Map<String, dynamic> source,
) {
  final post = contentPostWireFromReadModelMap(source);
  final postId = post['postId']! as String;
  final contentType = post['contentType']! as String;
  final openSurface = switch (contentType) {
    'article' => 'article_reader',
    'video' => 'media_immersive',
    _ => 'home_feed',
  };
  return <String, Object?>{
    'envelope': <String, Object?>{
      'objectKind': 'post',
      'contentType': contentType,
      'openSurface': openSurface,
      'post': <String, Object?>{'postId': postId},
    },
    'post': post,
  };
}

String _requiredText(Map<String, dynamic> source, String field) {
  final value = _optionalText(source[field]);
  if (value == null) {
    throw FormatException('Content read model requires $field');
  }
  return value;
}

String? _optionalText(Object? value) {
  if (value == null) return null;
  final text = value.toString().trim();
  return text.isEmpty ? null : text;
}

int? _optionalInt(Object? value) => value is num ? value.toInt() : null;

DateTime? _optionalDateTime(Object? value) {
  if (value == null) return null;
  if (value is DateTime) return value;
  if (value is String) return DateTime.tryParse(value);
  throw const FormatException('Content timestamp must be RFC3339');
}

List<String>? _stringList(Object? value) {
  if (value == null) return null;
  if (value is! List) {
    throw const FormatException('Content string collection must be a list');
  }
  return List<String>.unmodifiable(value.map((item) => item.toString()));
}

MediaDeliveryAccessMode? _optionalAccessMode(Object? value, String path) {
  if (value == null) return null;
  if (value is MediaDeliveryAccessMode) return value;
  return MediaDeliveryAccessMode.fromWire(value, path);
}

List<PostMediaItem>? _mediaItems(Object? value) {
  if (value == null) return null;
  if (value is! List) {
    throw const FormatException('mediaItems must be a list');
  }
  return List<PostMediaItem>.unmodifiable(
    value.asMap().entries.map((entry) {
      final item = entry.value;
      if (item is PostMediaItem) return item;
      if (item is Map) {
        return PostMediaItem.fromWire(
          Map<String, Object?>.from(item),
          'ContentPostProjection.mediaItems[${entry.key}]',
        );
      }
      throw const FormatException('Post media item must be an object');
    }),
  );
}

List<IntersectionReason>? _intersectionReasons(Object? value) {
  if (value == null) return null;
  if (value is! List) {
    throw const FormatException('intersectionReasons must be a list');
  }
  return List<IntersectionReason>.unmodifiable(
    value.asMap().entries.map((entry) {
      final item = entry.value;
      if (item is IntersectionReason) return item;
      if (item is Map) {
        return IntersectionReason.fromWire(
          Map<String, Object?>.from(item),
          'ContentPostProjection.intersectionReasons[${entry.key}]',
        );
      }
      throw const FormatException('Intersection reason must be an object');
    }),
  );
}
