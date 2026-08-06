// spec_ref: specs/feature-tree/runtime/runtime-media/spec.md#sit-002

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/adaptive_video_delivery.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/platform/platform_capabilities.dart';

void main() {
  final resolver = MediaDeliveryResolver(
    MediaEndpointConfig(
      avatarBaseUrl: 'https://cdn.example.invalid',
      imageBaseUrl: 'https://cdn.example.invalid',
      videoBaseUrl: 'https://cdn.example.invalid',
      attachmentBaseUrl: 'https://cdn.example.invalid',
    ),
  );

  MediaDeliveryReference video(
    String path, {
    String assetId = 'asset-video-001',
    int version = 3,
  }) => resolver.resolve(
    path,
    kind: MediaDeliveryKind.video,
    assetId: assetId,
    version: version,
  );

  final progressive = video(
    'media/video/s/asset/asset-video-001/v3/source.mp4',
  );
  final adaptive = video(
    'media/video/s/asset/asset-video-001/v3/hls/master.m3u8',
  );

  test('能力与 flag 开启时 HLS 优先且 progressive MP4 永远是第二候选', () {
    final candidates = AdaptiveVideoDeliverySet(
      progressive: progressive,
      adaptive: adaptive,
      adaptiveDescriptorVersion: 1,
    ).candidates(featureEnabled: true, capabilities: CapabilityProfile.mobile);

    expect(candidates, <MediaDeliveryReference>[adaptive, progressive]);
  });

  test('flag、capability 或 descriptor 任一未满足时只使用 P0', () {
    final delivery = AdaptiveVideoDeliverySet(
      progressive: progressive,
      adaptive: adaptive,
      adaptiveDescriptorVersion: 1,
    );

    expect(
      delivery.candidates(
        featureEnabled: false,
        capabilities: CapabilityProfile.mobile,
      ),
      <MediaDeliveryReference>[progressive],
    );
    expect(
      delivery.candidates(
        featureEnabled: true,
        capabilities: CapabilityProfile.web,
      ),
      <MediaDeliveryReference>[progressive],
    );
    expect(
      AdaptiveVideoDeliverySet(
        progressive: progressive,
        adaptive: adaptive,
      ).candidates(
        featureEnabled: true,
        capabilities: CapabilityProfile.mobile,
      ),
      <MediaDeliveryReference>[progressive],
    );
  });

  test('不同 asset/version 的 adaptive 引用不得进入候选链', () {
    final mismatchedAsset = video(
      'media/video/s/asset/asset-video-002/v3/hls/master.m3u8',
      assetId: 'asset-video-002',
    );
    final mismatchedVersion = video(
      'media/video/s/asset/asset-video-001/v4/hls/master.m3u8',
      version: 4,
    );

    for (final candidate in <MediaDeliveryReference>[
      mismatchedAsset,
      mismatchedVersion,
    ]) {
      expect(
        AdaptiveVideoDeliverySet(
          progressive: progressive,
          adaptive: candidate,
          adaptiveDescriptorVersion: 1,
        ).candidates(
          featureEnabled: true,
          capabilities: CapabilityProfile.mobile,
        ),
        <MediaDeliveryReference>[progressive],
      );
    }
  });
}
