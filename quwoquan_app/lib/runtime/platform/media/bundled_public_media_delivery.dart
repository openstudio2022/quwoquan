import 'dart:convert';

import 'package:quwoquan_app/service/content_service/media/original_access_quota/domain/signed_media_delivery_lease.dart';

import 'package:quwoquan_app/runtime/transport/media/media_delivery_binding.dart';
import 'package:flutter/painting.dart';
import 'package:video_player/video_player.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/platform/media/app_image_cache_controller.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_image_provider.dart';
import 'package:quwoquan_app/runtime/platform/media/public_media_delivery_port.dart';
import 'package:quwoquan_app/runtime/platform/video_player_controller_factory.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

/// 仅由 Alpha composition root 导入，不进入在线依赖闭包。
final class BundledPublicMediaDelivery implements PublicMediaDeliveryPort {
  Future<OfflineContentBundle>? _loading;
  Future<OfflineContentBundle> _bundle() =>
      _loading ??= OfflineContentBundle.load().catchError((Object error) {
        _loading = null;
        throw error;
      });
  @override
  MediaEndpointConfig? get endpoints => null;
  @override
  MediaDeliveryReference? tryResolve(
    String? reference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  }) {
    try {
      return MediaDeliveryReference.bundled(
        reference ?? '',
        kind: kind,
        bundleDigest: offlineContentManifestDigest,
        assetId: assetId,
        version: version,
        sha256: sha256,
      );
    } on MediaDeliveryResolutionException {
      return null;
    }
  }

  @override
  List<String> candidates(
    String reference,
    MediaDeliveryKind kind, {
    int version = 0,
  }) {
    final resolved = tryResolve(reference, kind: kind, version: version);
    return resolved == null ? const [] : [resolved.url];
  }

  @override
  Future<SignedMediaDeliveryLease> acquireLease(
    String reference, {
    required MediaDeliveryBinding binding,
    required MediaDeliveryKind kind,
    bool refresh = false,
  }) async {
    throw const OfflineContentFailure('bundle_private_media_unavailable');
  }

  @override
  Future<ImageProvider<Object>> acquireImage(
    String reference, {
    required MediaDeliveryBinding binding,
    CdnImagePreset profile = CdnImagePreset.none,
    bool refresh = false,
  }) async {
    if (!binding.isPublic) {
      throw const FormatException('media access binding invalid');
    }
    return imageProvider(reference, profile: profile);
  }

  @override
  ImageProvider<Object> imageProvider(
    String reference, {
    CdnImagePreset profile = CdnImagePreset.none,
    MediaDeliveryKind kind = MediaDeliveryKind.image,
    String? cacheKey,
    SignedMediaDeliveryLease? lease,
  }) {
    if (lease != null) {
      throw const OfflineContentFailure('bundle_private_media_unavailable');
    }
    return BundledImageProvider(
      reference: reference,
      digest: offlineContentManifestDigest,
      loadBundle: _bundle,
    );
  }

  @override
  Future<List<PlayableVideoSource>> playableSources(
    String reference, {
    MediaDeliveryReference? binding,
    SignedMediaDeliveryLease? lease,
    VideoViewType? viewType,
  }) async {
    final delivery =
        binding ?? tryResolve(reference, kind: MediaDeliveryKind.video);
    final bundle = await _bundle();
    final asset = bundle.media.lookup(
      reference,
      assetId: delivery?.assetId ?? '',
    );
    if (delivery == null ||
        delivery.bundleDigest != bundle.digest ||
        delivery.kind != MediaDeliveryKind.video ||
        delivery.url != reference ||
        asset == null ||
        asset.kind != 'video' ||
        delivery.version != asset.version ||
        (delivery.sha256 != null && delivery.sha256 != asset.digest)) {
      throw const OfflineContentFailure('bundle_video_reference_invalid');
    }
    final path = await asset.materializeVideo();
    return [
      PlayableVideoSource(
        label: 'cache',
        createController: () => AppVideoPlayerControllerFactory.localFilePath(
          path,
          viewType: viewType,
        ),
      ),
    ];
  }

  @override
  Future<Map<String, dynamic>> loadJson(
    String reference, {
    required MediaDeliveryReference binding,
  }) async {
    final bundle = await _bundle();
    final asset = bundle.media.lookup(reference);
    if (reference != binding.sourceReference ||
        binding.bundleDigest != bundle.digest ||
        asset == null ||
        (binding.sha256 != null && binding.sha256 != asset.digest)) {
      throw const OfflineContentFailure('bundle_manifest_reference_invalid');
    }
    return jsonDecode(utf8.decode(await asset.readVerifiedBytes()))
        as Map<String, dynamic>;
  }
}
