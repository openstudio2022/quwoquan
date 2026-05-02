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
/// 按 contentType 分发到具体子类使用 [postBaseDtoFromMap]，后续消费统一经由
/// `PostBaseDto` 暴露的标题 / 正文 / 图片 / 视频 / 封面接口，避免在 UI 层直接分支判断
/// 具体子类型。
abstract class PostBaseDto {
  const PostBaseDto();

  String get id;
  String get type;
  String get identity;
  String get displayFormat;
  String get authorId;

  /// Canonical author profile subject key.
  /// Must be sourced from `authorProfileSubjectId` / `profileSubjectId`,
  /// and must not silently fall back to current `authorId`.
  String get authorProfileSubjectId;
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

  /// Optional canonical title for note/article-like posts.
  String get title => '';

  /// Optional canonical body / caption across all post kinds.
  String? get body => null;

  /// Canonical image list when the post carries image media.
  List<String> get imageUrls => const <String>[];

  /// Canonical cover image for article/photo-like posts.
  String? get coverUrl => null;

  /// Canonical video URL for video-like posts.
  String? get videoUrl => null;

  /// Canonical video thumbnail for video-like posts.
  String? get thumbnailUrl => null;

  /// Optional media duration in milliseconds.
  int? get durationMs => null;

  /// Optional canonical aspect ratio for visual posts.
  double? get aspectRatio => null;

  String get normalizedTitle => title.trim();

  String get normalizedBody => (body ?? '').trim();

  List<String> get mediaImageUrls => imageUrls
      .map((url) => url.trim())
      .where((url) => url.isNotEmpty)
      .toList(growable: false);

  String get mediaCoverUrl => (coverUrl ?? '').trim();

  String get mediaVideoUrl => (videoUrl ?? '').trim();

  String get mediaThumbnailUrl => (thumbnailUrl ?? '').trim();

  bool get hasImages => mediaImageUrls.isNotEmpty;

  bool get hasVideo => mediaVideoUrl.isNotEmpty;

  bool get hasVisualMedia =>
      hasImages || mediaCoverUrl.isNotEmpty || mediaThumbnailUrl.isNotEmpty;

  bool get hasAnyMedia => hasVisualMedia || hasVideo;

  int get mediaCount => hasVideo ? 1 : mediaImageUrls.length;

  String get primaryImageUrl {
    if (mediaImageUrls.isNotEmpty) {
      return mediaImageUrls.first;
    }
    if (mediaCoverUrl.isNotEmpty) {
      return mediaCoverUrl;
    }
    if (mediaThumbnailUrl.isNotEmpty) {
      return mediaThumbnailUrl;
    }
    return '';
  }

  String get primaryVisualUrl {
    if (hasVideo) {
      if (mediaThumbnailUrl.isNotEmpty) {
        return mediaThumbnailUrl;
      }
      if (mediaCoverUrl.isNotEmpty) {
        return mediaCoverUrl;
      }
      if (mediaImageUrls.isNotEmpty) {
        return mediaImageUrls.first;
      }
      return mediaVideoUrl;
    }
    return primaryImageUrl;
  }

  bool get isArticleLike => identity == 'work' && displayFormat == 'note';

  bool get isVideoLike => hasVideo || displayFormat == 'video';

  bool get isTextOnly => displayFormat == 'note' && !hasAnyMedia;

  bool get supportsUnifiedViewer =>
      hasAnyMedia || normalizedTitle.isNotEmpty || normalizedBody.isNotEmpty;

  Map<String, dynamic> toMap();
}
