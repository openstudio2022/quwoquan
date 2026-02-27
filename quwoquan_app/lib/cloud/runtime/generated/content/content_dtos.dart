// Barrel: exports all content-domain typed DTOs and the fromMap dispatcher.
// Import this file to get access to all post DTO types at once.

export 'post_base_dto.dart';
export 'photo_post_dto.g.dart';
export 'video_post_dto.g.dart';
export 'article_post_dto.g.dart';
export 'moment_post_dto.g.dart';

import 'package:quwoquan_app/cloud/runtime/generated/content/photo_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/video_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/article_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/moment_post_dto.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/post_base_dto.dart';

/// contentType に応じて対応するサブクラスにディスパッチする。
/// 按 contentType 分发到对应子类型 DTO。
///
/// 支持的 contentType 值：
/// - `image` / `photo` → [PhotoPostDto]
/// - `video` → [VideoPostDto]
/// - `article` → [ArticlePostDto]
/// - `micro` / `moment` → [MomentPostDto]
PostBaseDto postBaseDtoFromMap(Map<String, dynamic> m) {
  final contentType = m['contentType']?.toString() ??
      m['type']?.toString() ??
      m['category']?.toString() ??
      '';
  switch (contentType) {
    case 'video':
      return VideoPostDto.fromMap(m);
    case 'article':
      return ArticlePostDto.fromMap(m);
    case 'micro':
    case 'moment':
      return MomentPostDto.fromMap(m);
    case 'image':
    case 'photo':
    default:
      return PhotoPostDto.fromMap(m);
  }
}
