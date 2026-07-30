// Hand-written abstract base for all typed post DTOs.
// NOT code-generated.
//
// Subclasses are generated from _projections/*.yaml client_projection:
//   PhotoPostDto   ← photo_post_dto.g.dart
//   VideoPostDto   ← video_post_dto.g.dart
//   ArticlePostDto ← article_post_dto.g.dart
//   MicroPostDto  ← micro_post_dto.g.dart

import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/source_attribution_dto.g.dart';

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
  String get personaId => authorId;
  String get displayName;
  String get avatarUrl;

  /// 作者主页背景图 URL；null 表示未配置，UI 显示默认渐变背景。
  String? get authorBackgroundUrl;
  String get authorRoleLabel => '';
  List<String> get authorIdentityTags => const <String>[];
  bool get authorVerified => false;
  String get assistantUsePolicy;
  int get likeCount;
  int get commentCount;
  int get shareCount;

  /// 创作时间（内容首次进入系统）。
  DateTime get createdAt;

  /// 最后实质更新时间；null 或不晚于 [createdAt] 表示未编辑过。
  DateTime? get updatedAt => null;

  /// 首次公开时间（仅首次发布置位）；null 表示尚未发布或未知。
  DateTime? get publishedAt => null;

  /// 推荐垂类/召回路径/供给来源为推荐归因字段，UI 不展示，但曝光与互动上报透传。
  String? get contentVertical => null;
  String? get recallPath => null;
  String? get supplySource => null;

  /// 外部来源视频的原创者和权利事实；与平台发布作者身份分离。
  SourceAttributionDto? get sourceAttribution => null;

  /// 是否在创作之后发生过实质更新（决定 UI 是否展示「更新于」）。
  /// 容忍秒级抖动：仅当更新时间比创作时间晚超过 1 秒才算更新。
  bool get hasMeaningfulUpdate {
    final updated = updatedAt;
    if (updated == null) {
      return false;
    }
    return updated.difference(createdAt).inSeconds > 1;
  }

  /// Optional canonical title for note/article-like posts.
  String get title => '';

  /// Optional canonical body / caption across all post kinds.
  String? get body => null;

  /// Optional canonical summary for article-like posts.
  String get summary => '';

  /// Canonical image list when the post carries image media.
  List<String> get imageUrls => const <String>[];

  /// Canonical cover image for article/photo-like posts.
  String? get coverUrl => null;

  /// Article presentation facts; empty for non-article content.
  String get articleTemplate => '';
  String get articleFontPreset => '';

  /// Canonical video URL for video-like posts.
  String? get videoUrl => null;

  /// Canonical video thumbnail for video-like posts.
  String? get thumbnailUrl => null;

  /// Optional media duration in milliseconds.
  int? get durationMs => null;

  /// 交集理由（云侧推荐管线预生成，B1）。
  /// 默认 null 表示该帖无交集线索；内容卡「无来源不展示」。
  /// 子类（如 MicroPostDto）按 projection 字段 override。
  List<IntersectionReason>? get intersectionReasons => null;

  /// Optional canonical aspect ratio for visual posts.
  double? get aspectRatio => null;

  String get normalizedTitle => title.trim();

  String get normalizedBody => (body ?? '').trim();

  /// 供展示层解析的原始图片 media reference。
  ///
  /// DTO 只承载 wire contract；CDN/Gateway URL 解析属于 UI/展示 mapper。
  List<String> get mediaImageUrls => imageUrls
      .map((url) => url.trim())
      .where((url) => url.isNotEmpty)
      .toList(growable: false);

  /// 供展示层解析的原始封面 media reference。
  String get mediaCoverUrl => coverUrl?.trim() ?? '';

  /// 供展示层解析的原始视频 media reference。
  String get mediaVideoUrl => videoUrl?.trim() ?? '';

  /// 供展示层解析的原始缩略图 media reference。
  String get mediaThumbnailUrl => thumbnailUrl?.trim() ?? '';

  /// 视频展示封面优先使用缩略图；未提供时使用内容封面。
  String get mediaVideoCoverUrl {
    if (mediaThumbnailUrl.isNotEmpty) {
      return mediaThumbnailUrl;
    }
    return mediaCoverUrl;
  }

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
      return '';
    }
    return primaryImageUrl;
  }

  bool get isArticleLike => identity == 'work' && displayFormat == 'note';

  bool get isVideoLike => hasVideo;

  bool get isTextOnly => displayFormat == 'note' && !hasAnyMedia;

  bool get supportsUnifiedViewer =>
      hasAnyMedia || normalizedTitle.isNotEmpty || normalizedBody.isNotEmpty;

  Map<String, dynamic> toMap();
}
