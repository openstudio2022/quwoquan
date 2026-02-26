import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';

/// 投射后的 post 视图模型 — 由 projectPostMap 从 DTO 生成，供 viewer/detail 消费。
///
/// 取代所有 post['likesCount']、post['author']['name']、post['images'] 等写死字符串访问。
/// 字段命名与 DTO canonical 字段保持一致（likeCount → likesCount，以 UI 侧统一为准）。
class PostSummaryView {
  const PostSummaryView({
    required this.id,
    required this.type,
    required this.authorId,
    required this.displayName,
    required this.avatarUrl,
    this.backgroundImage,
    required this.author,
    required this.likesCount,
    required this.commentsCount,
    required this.savesCount,
    required this.sharesCount,
    required this.createdAt,
    this.images,
    this.thumbnail,
    this.thumbnailUrl,
    this.coverUrl,
    this.aspectRatio,
    this.videoUrl,
    this.videoType,
    this.duration,
    this.title,
    this.body,
  });

  final String id;
  final String type;

  /// 作者 ID（routing key，用于关注/取关）
  final String authorId;

  /// 作者展示名
  final String displayName;

  /// 作者头像 URL
  final String avatarUrl;

  /// 作者主页背景图（来自 authorBackgroundUrl）
  final String? backgroundImage;

  /// 结构化作者摘要
  final PostAuthorSummary author;

  final int likesCount;
  final int commentsCount;
  final int savesCount;
  final int sharesCount;
  final String createdAt;

  // ── Photo 专属 ──────────────────────────────────────────
  /// 图片 URL 列表（来自 mediaUrls / imageUrls）
  final List<String>? images;
  final String? thumbnail;
  final String? thumbnailUrl;
  final String? coverUrl;
  final double? aspectRatio;

  // ── Video 专属 ──────────────────────────────────────────
  final String? videoUrl;

  /// 内容类型标识（等于 type，主要用于竖/横向判断）
  final String? videoType;

  /// 时长（毫秒，来自 durationMs）
  final int? duration;

  // ── Article / Caption 专属 ─────────────────────────────
  final String? title;

  /// 正文 / caption（对应 DTO.body）
  final String? body;

  // ── 工厂：直接从 DTO 创建（零字符串 key 访问）────────────

  factory PostSummaryView.fromDto(PostBaseDto dto) {
    final author = PostAuthorSummary(
      id: dto.authorId,
      username: dto.authorId,
      name: dto.displayName,
      avatar: dto.avatarUrl,
    );

    List<String>? images;
    String? thumbnail, thumbnailUrl, coverUrl;
    double? aspectRatio;
    String? videoUrl, videoType;
    int? duration;
    String? title, body;

    if (dto is PhotoPostDto) {
      images = dto.imageUrls;
      thumbnail = dto.coverUrl;
      thumbnailUrl = dto.coverUrl;
      coverUrl = dto.coverUrl;
      aspectRatio = dto.aspectRatio;
    } else if (dto is VideoPostDto) {
      thumbnail = dto.thumbnailUrl;
      thumbnailUrl = dto.thumbnailUrl;
      coverUrl = dto.thumbnailUrl;
      videoUrl = dto.videoUrl;
      videoType = dto.type;
      duration = dto.durationMs;
    } else if (dto is ArticlePostDto) {
      title = dto.title;
      body = dto.body;
      coverUrl = dto.coverUrl;
      thumbnailUrl = dto.coverUrl;
      images = [dto.coverUrl];
    } else if (dto is MomentPostDto) {
      images = dto.imageUrls.isEmpty ? null : dto.imageUrls;
      videoUrl = dto.videoUrl;
      duration = dto.durationMs;
      body = dto.body;
    }

    return PostSummaryView(
      id: dto.id,
      type: dto.type,
      authorId: dto.authorId,
      displayName: dto.displayName,
      avatarUrl: dto.avatarUrl,
      backgroundImage: dto.authorBackgroundUrl,
      author: author,
      likesCount: dto.likeCount,
      commentsCount: dto.commentCount,
      savesCount: dto.favoriteCount,
      sharesCount: dto.shareCount,
      createdAt: dto.createdAt.toIso8601String(),
      images: images,
      thumbnail: thumbnail,
      thumbnailUrl: thumbnailUrl,
      coverUrl: coverUrl,
      aspectRatio: aspectRatio,
      videoUrl: videoUrl,
      videoType: videoType,
      duration: duration,
      title: title,
      body: body,
    );
  }
}

/// 投射后的作者摘要（嵌套于 PostSummaryView）
class PostAuthorSummary {
  const PostAuthorSummary({
    required this.id,
    required this.username,
    required this.name,
    required this.avatar,
  });

  final String id;
  final String username;
  final String name;
  final String avatar;
}
