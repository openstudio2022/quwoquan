import 'package:quwoquan_app/runtime/di/public_media_delivery_dependencies.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/content_surface_view_mapper.dart'
    as domain;

/// 仅注入已选媒体能力；映射算法与资产绑定事实仍唯一由 domain 拥有。
class ContentSurfaceViewMapper {
  const ContentSurfaceViewMapper._();

  static ContentSurfaceView fromDto(
    ContentPostViewData dto, {
    Map<String, dynamic>? wire,
    ContentSurfaceReferral referral = const ContentSurfaceReferral(),
    MediaDeliveryResolver? mediaResolver,
  }) => domain.ContentSurfaceViewMapper.fromDto(
    dto,
    wire: wire,
    referral: referral,
    resolveMedia: mediaResolver?.tryResolve ?? publicMediaDelivery.tryResolve,
  );

  static ContentSurfaceView fromArticleDetailPayload(
    ContentPostDetailPayload payload, {
    required String fallbackArticleId,
    ContentSurfaceReferral referral = const ContentSurfaceReferral(),
  }) => domain.ContentSurfaceViewMapper.fromArticleDetailPayload(
    payload,
    fallbackArticleId: fallbackArticleId,
    referral: referral,
    resolveMedia: publicMediaDelivery.tryResolve,
  );
}
