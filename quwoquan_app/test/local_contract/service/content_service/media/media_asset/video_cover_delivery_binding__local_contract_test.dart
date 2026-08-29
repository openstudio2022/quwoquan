// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/work_browser_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show MediaDeliveryAccessMode;

/// 视频封面的 typed 交付绑定（DEC-033）。
///
/// 封面是独立于视频轨的资产：它的资产身份是 `coverAssetId`，不是视频的
/// `mediaAssetId`，更不是 post 标识。本用例锁定绑定的取值来源，防止回潮到
/// 「用视频资产身份换封面短签」或「以对象标识冒充媒体资产标识」。
MediaDeliveryBinding coverBindingOf(WorkBrowserMediaViewData item) {
  return MediaDeliveryBinding(
    assetId: item.coverAssetId?.trim() ?? '',
    accessMode: item.accessMode,
    publicUrl: item.coverUrl?.trim() ?? '',
  );
}

void main() {
  group('视频封面 typed 交付绑定', () {
    test('私有视频的封面绑定取 coverAssetId，不取视频 mediaAssetId', () {
      const item = WorkBrowserMediaViewData(
        kind: 'video',
        url: 'media/video/private/clip.mp4',
        coverUrl: 'media/image/private/cover.jpg',
        coverAssetId: 'cover-asset-1',
        mediaAssetId: 'video-asset-1',
        accessMode: MediaDeliveryAccessMode.signedGrant,
      );

      final binding = coverBindingOf(item);

      expect(binding.assetId, 'cover-asset-1');
      expect(binding.assetId, isNot('video-asset-1'));
      expect(binding.isSignedGrant, isTrue);
    });

    test('私有视频但封面资产身份缺席时判否，不回退公开路', () {
      const item = WorkBrowserMediaViewData(
        kind: 'video',
        url: 'media/video/private/clip.mp4',
        coverUrl: 'media/image/private/cover.jpg',
        coverAssetId: null,
        mediaAssetId: 'video-asset-1',
        accessMode: MediaDeliveryAccessMode.signedGrant,
      );

      final binding = coverBindingOf(item);

      expect(binding.isSignedGrant, isFalse);
      // 声明为私有交付却没有封面资产身份属投影自相矛盾：落判否，
      // 不得因为 publicUrl 在场就走公开路把授权判定跳过。
      expect(binding.isSignedGrantWithoutAsset, isTrue);
    });

    test('公开视频的封面走公开路', () {
      const item = WorkBrowserMediaViewData(
        kind: 'video',
        url: 'media/video/public/clip.mp4',
        coverUrl: 'media/image/public/cover.jpg',
        coverAssetId: 'cover-asset-2',
        mediaAssetId: 'video-asset-2',
        accessMode: MediaDeliveryAccessMode.public,
      );

      final binding = coverBindingOf(item);

      expect(binding.isSignedGrant, isFalse);
      expect(binding.isSignedGrantWithoutAsset, isFalse);
      expect(binding.publicUrl, 'media/image/public/cover.jpg');
    });

    test('契约缺席 accessMode（存量投影）走公开路', () {
      const item = WorkBrowserMediaViewData(
        kind: 'video',
        url: 'media/video/public/clip.mp4',
        coverUrl: 'media/image/public/cover.jpg',
        accessMode: null,
      );

      final binding = coverBindingOf(item);

      expect(binding.isSignedGrant, isFalse);
      expect(binding.isSignedGrantWithoutAsset, isFalse);
      expect(binding.publicUrl, 'media/image/public/cover.jpg');
    });

    test('封面 URL 缺席即缺席绑定，不猜一条 URL', () {
      const item = WorkBrowserMediaViewData(
        kind: 'video',
        url: 'media/video/public/clip.mp4',
        coverUrl: null,
        accessMode: null,
      );

      final binding = coverBindingOf(item);

      expect(binding.publicUrl, isEmpty);
      expect(binding.assetId, isEmpty);
      expect(binding.isSignedGrant, isFalse);
    });
  });
}
