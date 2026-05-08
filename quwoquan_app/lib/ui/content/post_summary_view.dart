import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/ui/content/post_read_projection_facade.dart';

/// 投射后的 post 视图模型 — 由 [PostSummaryView.fromDto] 从 [PostBaseDto] 构建；
/// 典型入口为 `post_view_projection.dart` 中的 `projectPostMap`（避免与本文件循环 import，故不作 dartdoc 链接）。
///
/// **与 [PostReadPresentation] 分工**：本类内嵌 [readPresentation]（metadata 对齐的标题/正文等）；
/// 同时保留 **viewer 侧记录命名**（如 [likesCount]）。新业务优先直接用 [readPresentation] 或 DTO，
/// 避免第三套并行只读模型。
///
/// 取代所有 `post['likesCount']`、`post['author']['name']` 等散落字符串访问。
class PostSummaryView {
  PostSummaryView({
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
    required this.readPresentation,
    this.surfaceId = PostReadSurfaceId.feedCard,
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

  /// metadata 只读投影（与 [surfaceId] 对应表面一致由调用方保证）。
  final PostReadPresentation readPresentation;

  /// 本视图所服务的 UI 表面（P2 SurfaceSpec）。
  final PostReadSurfaceId surfaceId;

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

  factory PostSummaryView.fromDto(
    PostBaseDto dto, {
    PostReadSurfaceId surfaceId = PostReadSurfaceId.feedCard,
    Map<String, dynamic>? wire,
  }) {
    final author = PostAuthorSummary(
      id: dto.subAccountId,
      username: dto.subAccountId,
      name: dto.displayName,
      avatar: dto.avatarUrl,
    );

    List<String>? images = dto.hasImages ? dto.mediaImageUrls : null;
    if (dto.isArticleLike &&
        dto.mediaCoverUrl.isNotEmpty &&
        (images == null || images.isEmpty)) {
      images = <String>[dto.mediaCoverUrl];
    }

    var thumbnail = dto.primaryVisualUrl.isEmpty ? null : dto.primaryVisualUrl;
    var thumbnailUrl = dto.mediaThumbnailUrl.isEmpty
        ? (dto.primaryVisualUrl.isEmpty ? null : dto.primaryVisualUrl)
        : dto.mediaThumbnailUrl;
    final coverUrl = dto.mediaCoverUrl.isEmpty
        ? (dto.primaryImageUrl.isEmpty ? null : dto.primaryImageUrl)
        : dto.mediaCoverUrl;

    // 图片作品：外显缩略图优先封面，与多图 gallery（images）解耦
    if (dto.displayFormat == 'image' && dto.mediaCoverUrl.isNotEmpty) {
      thumbnail = dto.mediaCoverUrl;
      thumbnailUrl = dto.mediaCoverUrl;
    }
    final aspectRatio = dto.aspectRatio;
    final videoUrl = dto.hasVideo ? dto.mediaVideoUrl : null;
    final videoType = dto.hasVideo ? dto.type : null;
    final duration = dto.durationMs;
    final read = PostReadProjectionFacade.presentationFor(
      dto,
      surfaceId,
      wire: wire,
    );
    final title = read.title.isEmpty ? null : read.title;
    final body = read.body.isEmpty ? null : read.body;

    return PostSummaryView(
      id: dto.id,
      type: dto.type,
      authorId: dto.subAccountId,
      displayName: dto.displayName,
      avatarUrl: dto.avatarUrl,
      backgroundImage: dto.authorBackgroundUrl,
      author: author,
      likesCount: dto.likeCount,
      commentsCount: dto.commentCount,
      savesCount: dto.favoriteCount,
      sharesCount: dto.shareCount,
      createdAt: dto.createdAt.toIso8601String(),
      readPresentation: read,
      surfaceId: surfaceId,
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
