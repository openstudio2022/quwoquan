import 'package:flutter/painting.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';

/// 平台差异由获取器封装，消费方只创建已准入的 controller。
final class PlayableVideoSource {
  const PlayableVideoSource({
    required this.label,
    required this.createController,
  });
  factory PlayableVideoSource.cachedFile(
    String path, {
    VideoViewType? viewType,
  }) => PlayableVideoSource(
    label: 'cache',
    createController: () =>
        AppVideoPlayerControllerFactory.localFilePath(path, viewType: viewType),
  );
  factory PlayableVideoSource.network(
    Uri uri, {
    VideoFormat? formatHint,
    VideoViewType? viewType,
  }) => PlayableVideoSource(
    label: 'network',
    createController: () => AppVideoPlayerControllerFactory.networkUri(
      uri,
      formatHint: formatHint,
      viewType: viewType,
    ),
  );
  final String label;
  final AppVideoPlayerControllerHandle Function() createController;
}

/// 已选定 authority 的公开媒体读取能力；调用方不选择环境或回退来源。
abstract interface class PublicMediaDeliveryPort {
  MediaEndpointConfig? get endpoints;
  MediaDeliveryReference? tryResolve(
    String? reference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  });
  List<String> candidates(
    String reference,
    MediaDeliveryKind kind, {
    int version = 0,
  });
  Future<SignedMediaDeliveryLease> acquireLease(
    String reference, {
    required MediaDeliveryBinding binding,
    required MediaDeliveryKind kind,
    bool refresh = false,
  });
  Future<ImageProvider<Object>> acquireImage(
    String reference, {
    required MediaDeliveryBinding binding,
    CdnImagePreset profile = CdnImagePreset.none,
    bool refresh = false,
  });
  ImageProvider<Object> imageProvider(
    String reference, {
    CdnImagePreset profile = CdnImagePreset.none,
    MediaDeliveryKind kind = MediaDeliveryKind.image,
    String? cacheKey,
    SignedMediaDeliveryLease? lease,
  });
  Future<List<PlayableVideoSource>> playableSources(
    String reference, {
    MediaDeliveryReference? binding,
    SignedMediaDeliveryLease? lease,
    VideoViewType? viewType,
  });
  Future<Map<String, dynamic>> loadJson(
    String reference, {
    required MediaDeliveryReference binding,
  });
}
