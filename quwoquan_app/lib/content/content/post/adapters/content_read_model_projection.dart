import 'package:quwoquan_app/cloud/runtime/models/content_post_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// Test/data-boundary projection of the authoritative service read model into
/// the canonical generated Content contract.
ContentPostProjection contentPostProjectionFromReadModelMap(
  Map<String, dynamic> source,
) {
  return ContentPostProjection(
    postId: _requiredText(source, 'postId'),
    contentType: _requiredText(source, 'contentType'),
    contentIdentity: _optionalText(source['contentIdentity']),
    assistantUsePolicy: _optionalText(source['assistantUsePolicy']),
    authorId: _optionalText(source['authorId']),
    authorDisplayName: _optionalText(source['authorDisplayName']),
    authorAvatarUrl: _optionalText(source['authorAvatarUrl']),
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
    contentVertical: _optionalText(source['contentVertical']),
    recallPath: _optionalText(source['recallPath']),
    supplySource: _optionalText(source['supplySource']),
    intersectionReasons: _intersectionReasons(source['intersectionReasons']),
  );
}

ContentPostViewData contentPostViewDataFromReadModelMap(
  Map<String, dynamic> source,
) =>
    ContentPostViewData.fromWire(contentPostProjectionFromReadModelMap(source));

/// 将 App 展示投影重新绑定到 canonical generated Post projection。
///
/// 本函数是缓存与测试替身需要序列化 [ContentPostViewData] 时的唯一反向边界；
/// 调用方必须继续使用返回对象的 generated `toWire()`，不得自行维护第二套
/// presentation/wire 字段表。
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
    contentVertical: source.contentVertical,
    recallPath: source.recallPath,
    supplySource: source.supplySource,
    intersectionReasons: source.intersectionReasons,
  );
}

Map<String, Object?> contentPostWireFromReadModelMap(
  Map<String, dynamic> source,
) => contentPostProjectionFromReadModelMap(source).toWire();

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
