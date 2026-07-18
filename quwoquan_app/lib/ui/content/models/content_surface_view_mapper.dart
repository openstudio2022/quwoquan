import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/cloud/runtime/generated/recommendation/intersection_reason.g.dart';
import 'package:quwoquan_app/cloud/runtime/models/content_post_detail_payload.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view.dart';
import 'package:quwoquan_app/ui/content/services/post_view_projection.dart';

/// 统一展示模型的唯一映射器：`PostBaseDto (+ wire)` → [ContentSurfaceView]。
///
/// 标题/正文/封面/长文模板字段复用 metadata 对齐的 [PostReadPresentation]，
/// 媒体 URL 在此展示边界解析，作者/统计复用 `PostBaseDto` 的契约派生 getter，
/// 确保四 surface 同源、字段口径与 metadata 投影一致。禁止对 DTO 子类做
/// `is/as/whereType`。
class ContentSurfaceViewMapper {
  const ContentSurfaceViewMapper._();

  static ContentSurfaceView fromDto(
    PostBaseDto dto, {
    Map<String, dynamic>? wire,
    ContentSurfaceReferral referral = const ContentSurfaceReferral(),
  }) {
    final read = PostReadPresentation.fromPostBase(dto, wire: wire);
    final resolver = MediaDeliveryResolver.fromRuntimeConfig();

    final title = read.title.trim().isEmpty ? null : read.title.trim();
    final body = read.body.trim().isEmpty ? null : read.body.trim();

    final projectedCover = resolver.tryResolve(
      read.coverUrl,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
    );
    final mediaCover = resolver.tryResolve(
      dto.mediaCoverUrl,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
    );
    final mediaThumbnail = resolver.tryResolve(
      dto.mediaThumbnailUrl,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
    );
    final mediaVideo = resolver.tryResolve(
      dto.mediaVideoUrl,
      kind: MediaDeliveryKind.video,
      assetId: dto.id,
    );
    final mediaVideoCover = mediaThumbnail ?? mediaCover;
    final coverReference = dto.isVideoLike
        ? mediaVideoCover
        : (projectedCover ?? mediaCover);
    final cover = coverReference == null
        ? null
        : ContentCoverRef(
            delivery: coverReference,
            aspectRatio: dto.aspectRatio,
          );

    final images = dto.mediaImageUrls
        .map(
          (raw) => resolver.tryResolve(
            raw,
            kind: MediaDeliveryKind.image,
            assetId: dto.id,
          ),
        )
        .whereType<MediaDeliveryReference>()
        .map(
          (reference) => ContentImageRef(
            delivery: reference,
            aspectRatio: dto.aspectRatio,
          ),
        )
        .toList(growable: false);

    final ContentVideoRef? video = mediaVideo != null
        ? ContentVideoRef(
            delivery: mediaVideo,
            thumbnail: mediaVideoCover,
            durationMs: dto.durationMs,
            aspectRatio: dto.aspectRatio,
          )
        : null;

    final authorAvatar = resolver.tryResolve(
      dto.avatarUrl,
      kind: MediaDeliveryKind.avatar,
      assetId: dto.subAccountId,
    );
    final authorBackground = resolver.tryResolve(
      dto.authorBackgroundUrl,
      kind: MediaDeliveryKind.background,
      assetId: dto.subAccountId,
    );

    return ContentSurfaceView(
      postId: dto.id,
      kind: _kindFor(dto),
      contentType: dto.type,
      contentIdentity: dto.identity,
      author: ContentAuthorRef(
        id: dto.subAccountId,
        displayName: dto.displayName,
        avatar: authorAvatar,
        background: authorBackground,
      ),
      stats: ContentStats(
        like: dto.likeCount,
        comment: dto.commentCount,
        share: dto.shareCount,
      ),
      createdAt: dto.createdAt,
      updatedAt: dto.updatedAt,
      publishedAt: dto.publishedAt,
      title: title,
      body: body,
      cover: cover,
      images: images,
      video: video,
      intersectionReasons:
          dto.intersectionReasons ?? const <IntersectionReason>[],
      tags: _tagsFrom(wire),
      articleTemplate: read.articleTemplate,
      articleFontPreset: read.articleFontPreset,
      referral: referral,
    );
  }

  /// 文章详情/沉浸水合路径：从 [ContentPostDetailPayload] 构建带富渲染载荷的统一视图。
  ///
  /// 公共字段（作者/统计/标题/封面）走 [fromDto] 同源口径；文章块/卡片/文档/分页
  /// 由 [projectArticleDetailViewFromPayload] 直接投影为 [ContentArticleRender] 并
  /// 挂载到 [ContentSurfaceView.article]。
  static ContentSurfaceView fromArticleDetailPayload(
    ContentPostDetailPayload payload, {
    required String fallbackArticleId,
    ContentSurfaceReferral referral = const ContentSurfaceReferral(),
  }) {
    final wire = payload.mergedArticleWireMap;
    final dto = postBaseDtoFromMap(wire);
    final base = fromDto(dto, wire: wire, referral: referral);
    return base.copyWith(
      article: projectArticleDetailViewFromPayload(
        payload,
        fallbackArticleId: fallbackArticleId,
      ),
    );
  }

  /// 媒体形态判别：仅用 `PostBaseDto` 的契约派生 getter（无 `is/as`）。
  static ContentSurfaceKind _kindFor(PostBaseDto dto) {
    if (dto.isVideoLike) {
      return ContentSurfaceKind.video;
    }
    if (dto.isArticleLike) {
      return ContentSurfaceKind.article;
    }
    if (dto.hasImages) {
      return ContentSurfaceKind.image;
    }
    return ContentSurfaceKind.micro;
  }

  static List<String> _tagsFrom(Map<String, dynamic>? wire) {
    final raw = wire?['tagRefs'];
    if (raw is List) {
      return raw.whereType<String>().toList(growable: false);
    }
    return const <String>[];
  }
}
