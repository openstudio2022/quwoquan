import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/content_read_model_projection.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_view_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

/// runtime/di 统一展示模型映射器：`ContentPostViewData (+ wire)` → [ContentSurfaceView]。
///
/// 标题/正文/封面/长文模板字段复用 [ContentPostViewData] 的 canonical 投影，
/// 媒体 URL 在此展示边界解析，作者/统计复用其契约派生 getter，
/// 确保四 surface 同源、字段口径与 metadata 投影一致。禁止对 DTO 子类做
/// `is/as/whereType`。
class ContentSurfaceViewMapper {
  const ContentSurfaceViewMapper._();

  static ContentSurfaceView fromDto(
    ContentPostViewData dto, {
    Map<String, dynamic>? wire,
    ContentSurfaceReferral referral = const ContentSurfaceReferral(),
    MediaDeliveryResolver? mediaResolver,
  }) {
    final endpoints = MediaEndpointConfig.tryCreateAvailable(
      avatarBaseUrl: CloudRuntimeConfig.mediaAvatarCdnBaseUrl,
      imageBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
      videoBaseUrl: CloudRuntimeConfig.mediaVideoCdnBaseUrl,
      attachmentBaseUrl: CloudRuntimeConfig.mediaImageCdnBaseUrl,
    );
    final resolver =
        mediaResolver ??
        (endpoints == null ? null : MediaDeliveryResolver(endpoints));

    final title = dto.normalizedTitle.isEmpty ? null : dto.normalizedTitle;
    final body = dto.normalizedBody.isEmpty ? null : dto.normalizedBody;

    final projectedCover = resolver?.tryResolve(
      dto.mediaCoverUrl,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
    );
    final mediaCover = resolver?.tryResolve(
      dto.mediaCoverUrl,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
    );
    final mediaThumbnail = resolver?.tryResolve(
      dto.mediaThumbnailUrl,
      kind: MediaDeliveryKind.image,
      assetId: dto.id,
    );
    final mediaVideo = resolver?.tryResolve(
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
            delivery: _contentDelivery(coverReference),
            aspectRatio: dto.aspectRatio,
          );

    final images = dto.mediaImageUrls
        .map(
          (raw) => resolver?.tryResolve(
            raw,
            kind: MediaDeliveryKind.image,
            assetId: dto.id,
          ),
        )
        .whereType<MediaDeliveryReference>()
        .map(
          (reference) => ContentImageRef(
            delivery: _contentDelivery(reference),
            aspectRatio: dto.aspectRatio,
          ),
        )
        .toList(growable: false);

    final ContentVideoRef? video = mediaVideo != null
        ? ContentVideoRef(
            delivery: _contentDelivery(mediaVideo),
            thumbnail: mediaVideoCover == null
                ? null
                : _contentDelivery(mediaVideoCover),
            durationMs: dto.durationMs,
            aspectRatio: dto.aspectRatio,
          )
        : null;

    final authorAvatar = resolver?.tryResolve(
      dto.avatarUrl,
      kind: MediaDeliveryKind.avatar,
      assetId: dto.personaId,
    );
    final authorBackground = resolver?.tryResolve(
      dto.authorBackgroundUrl,
      kind: MediaDeliveryKind.background,
      assetId: dto.personaId,
    );

    return ContentSurfaceView(
      postId: dto.id,
      kind: _kindFor(dto),
      contentType: dto.type,
      contentIdentity: dto.identity,
      author: ContentAuthorRef(
        id: dto.personaId,
        displayName: dto.displayName,
        avatar: authorAvatar == null ? null : _contentDelivery(authorAvatar),
        background: authorBackground == null
            ? null
            : _contentDelivery(authorBackground),
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
      articleTemplate: dto.articleTemplate,
      articleFontPreset: dto.articleFontPreset,
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
    final dto = contentPostViewDataFromReadModelMap(wire);
    final base = fromDto(dto, wire: wire, referral: referral);
    return base.copyWith(
      article: projectArticleDetailViewFromPayload(
        payload,
        fallbackArticleId: fallbackArticleId,
      ),
    );
  }

  /// 媒体形态判别：仅用 `ContentPostViewData` 的契约派生 getter（无 `is/as`）。
  static ContentSurfaceKind _kindFor(ContentPostViewData dto) {
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

  static ContentDeliveryRef _contentDelivery(MediaDeliveryReference reference) {
    return ContentDeliveryRef(
      url: reference.url,
      assetId: reference.assetId,
      version: reference.version,
      sha256: reference.sha256,
    );
  }
}
