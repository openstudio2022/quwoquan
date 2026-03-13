// Hand-written abstract base for all typed post DTOs.
// NOT code-generated.
//
// Subclasses are generated from _projections/*.yaml client_projection:
//   PhotoPostDto   ← photo_post_dto.g.dart
//   VideoPostDto   ← video_post_dto.g.dart
//   ArticlePostDto ← article_post_dto.g.dart
//   MomentPostDto  ← moment_post_dto.g.dart

/// 所有类型化帖子 DTO 的抽象基类。
///
/// 共享字段：id / type / identity / displayFormat / 作者信息 / 互动计数 / createdAt。
/// 子类按内容类型扩展特有字段（PhotoPostDto 的 width/height/imageUrls 等）。
///
/// 按 contentType 分发到具体子类使用 [postBaseDtoFromMap]：
/// ```dart
/// import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
/// final PostBaseDto post = postBaseDtoFromMap(rawMap);
/// if (post is PhotoPostDto) { ... }
/// ```
abstract class PostBaseDto {
  const PostBaseDto();

  String get id;
  String get type;
  String get identity;
  String get displayFormat;
  String get authorId;
  String get displayName;
  String get avatarUrl;
  /// 作者主页背景图 URL；null 表示未配置，UI 显示默认渐变背景。
  String? get authorBackgroundUrl;
  String get assistantUsePolicy;
  int get likeCount;
  int get commentCount;
  int get favoriteCount;
  int get shareCount;
  DateTime get createdAt;

  Map<String, dynamic> toMap();
}
