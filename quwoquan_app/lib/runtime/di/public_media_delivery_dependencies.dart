import 'package:flutter/painting.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

export 'package:quwoquan_app/runtime/platform/media/public_media_delivery_port.dart';
import 'package:quwoquan_app/runtime/config/app_content_source.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/config/generated/offline_content_bundle_identity.g.dart';
import 'package:quwoquan_app/runtime/config/offline_content_bundle.dart';
import 'package:quwoquan_app/runtime/config/offline_content_failure.dart';
import 'package:quwoquan_app/runtime/platform/media/bundled_image_provider.dart';
import 'package:quwoquan_app/runtime/platform/media/public_media_delivery_port.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

/// 与现有 native runtime hydration 同生存期；换文档后不复用旧媒体 authority。
PublicMediaDeliveryPort get publicMediaDelivery {
  final identity = CloudRuntimeConfig.runtimeConfigPackageDigest;
  if (_identity != identity) {
    _selected =
        CloudRuntimeConfig.contentSource == AppContentSource.bundledSnapshot
        ? _BundledPublicMediaDelivery()
        : _RemotePublicMediaDelivery(MediaEndpointConfig.fromRuntimeConfig());
    _identity = identity;
  }
  return _selected!;
}

String? _identity;
PublicMediaDeliveryPort? _selected;

/// 页面仅消费所选媒体能力；端点 override 仍经同一 Remote 严格解析边界。
final publicMediaDeliveryProvider = Provider<PublicMediaDeliveryPort>((ref) {
  final endpoints = ref.watch(mediaEndpointConfigProvider);
  return endpoints == null
      ? publicMediaDelivery
      : _RemotePublicMediaDelivery(endpoints);
});

final class _RemotePublicMediaDelivery implements PublicMediaDeliveryPort {
  const _RemotePublicMediaDelivery(this.endpoints);
  @override
  final MediaEndpointConfig endpoints;
  @override
  MediaDeliveryReference? tryResolve(
    String? reference, {
    required MediaDeliveryKind kind,
    String assetId = '',
    int version = 0,
    String? sha256,
  }) => MediaDeliveryResolver(endpoints).tryResolve(
    reference,
    kind: kind,
    assetId: assetId,
    version: version,
    sha256: sha256,
  );
  @override
  List<String> candidates(
    String reference,
    MediaDeliveryKind kind, {
    int version = 0,
  }) {
    final resolved = MediaDeliveryResolver(endpoints)
        .tryResolve(reference, kind: kind, version: version);
    return resolved == null ? const [] : [resolved.url];
  }

  @override
  ImageProvider<Object>? verifiedImageProvider(String reference) => null;
  @override
  Future<String?> verifiedVideoPath(
    String reference, {
    MediaDeliveryReference? binding,
  }) async {
    if (binding?.bundleDigest != null) {
      throw const OfflineContentFailure('bundle_video_authority_mismatch');
    }
    return null;
  }
}

final class _BundledPublicMediaDelivery implements PublicMediaDeliveryPort {
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
  ImageProvider<Object> verifiedImageProvider(String reference) =>
      BundledImageProvider(
        reference: reference,
        digest: offlineContentManifestDigest,
        loadBundle: _bundle,
      );
  @override
  Future<String> verifiedVideoPath(
    String reference, {
    MediaDeliveryReference? binding,
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
    return asset.materializeVideo();
  }
}
