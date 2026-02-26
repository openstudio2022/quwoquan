import 'package:quwoquan_app/core/constants/content_type_constants.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_metadata.g.dart';

/// 本地生成 Post 的元数据适配层。
///
/// - 元数据主数据由 `content/content_metadata.g.dart`（codegen 产物）提供。
/// - 仅保留端侧展示投影字段（如 username/displayName）的默认值补齐。
class LocalPostMetadata {
  const LocalPostMetadata._();

  static const String contentTypeMicro = 'micro';

  static const Map<String, String> contentTypeToRenderType =
      GeneratedPostRuntimeMetadata.contentTypeToRenderType;

  static const Map<String, dynamic> defaultFeedPost = <String, dynamic>{
    ...GeneratedPostRuntimeMetadata.feedProjectionDefaults,
    'username': 'me',
    'displayName': '我',
    'authorId': 'me',
    'avatarUrl': '',
  };

  static String normalizeContentType(String raw) {
    final normalized = raw.trim();
    if (normalized.isEmpty) return ContentTypeConstants.image;
    return GeneratedPostRuntimeMetadata.contentTypeToRenderType
            .containsKey(normalized)
        ? normalized
        : ContentTypeConstants.image;
  }

  static String renderTypeForContentType(String contentType) {
    return contentTypeToRenderType[contentType] ?? ContentTypeConstants.image;
  }
}
