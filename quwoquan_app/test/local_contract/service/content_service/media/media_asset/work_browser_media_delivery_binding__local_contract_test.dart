// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/multi-carrier-release/spec.md#gwt-016
//
// DEC-033 四路投影媒体交付绑定薄改（沉浸浏览媒体路）：
// WorkBrowserMediaViewData 必须保留契约 `PostMediaItem` 的
// accessMode 与 coverAssetId，缺席时为 null，不以 postId 冒充。

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/domain/work_browser_view_data.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

import '../../../../../support/service/content_service/content/post/content_post_contract_fixture.dart';

const _videoUrl = 'media/video/s/fixture/video1/v1/clip.mp4';

void main() {
  group('WorkBrowserMediaViewData.fromWire — 媒体交付绑定保留', () {
    test('signed_grant 绑定在场时 accessMode 与 coverAssetId 完整透传', () {
      const wire = PostMediaItem(
        kind: 'video',
        url: _videoUrl,
        mediaAssetId: 'asset-video-1',
        accessMode: MediaDeliveryAccessMode.signedGrant,
        coverUrl: 'media/image/s/fixture/video1/v1/poster.jpg',
        coverAssetId: 'asset-poster-1',
      );

      final view = WorkBrowserMediaViewData.fromWire(wire);

      expect(view.mediaAssetId, 'asset-video-1');
      expect(view.accessMode, MediaDeliveryAccessMode.signedGrant);
      expect(view.coverAssetId, 'asset-poster-1');
    });

    test('存量 public 投影未携带绑定字段时缺席为 null', () {
      const wire = PostMediaItem(kind: 'video', url: _videoUrl);

      final view = WorkBrowserMediaViewData.fromWire(wire);

      expect(view.mediaAssetId, isNull);
      expect(view.accessMode, isNull);
      expect(view.coverAssetId, isNull);
    });
  });

  group('WorkBrowserViewData.fromPost — 绑定透传与缺席不造值', () {
    test('supplemental mediaItems 保留 accessMode 与 coverAssetId', () {
      final post = ContentPostViewData.fromWire(
        contentPostProjectionFixture(postId: 'video1', contentType: 'video'),
      );

      final view = WorkBrowserViewData.fromPost(
        post,
        supplemental: <String, Object?>{
          'mediaItems': <Map<String, Object?>>[
            <String, Object?>{
              'kind': 'video',
              'url': _videoUrl,
              'mediaAssetId': 'asset-video-1',
              'accessMode': 'signed_grant',
              'coverAssetId': 'asset-poster-1',
            },
          ],
        },
      );

      expect(view.mediaItems, hasLength(1));
      expect(view.mediaItems.single.mediaAssetId, 'asset-video-1');
      expect(
        view.mediaItems.single.accessMode,
        MediaDeliveryAccessMode.signedGrant,
      );
      expect(view.mediaItems.single.coverAssetId, 'asset-poster-1');
      // 不以 postId 冒充媒体资产标识。
      expect(view.mediaItems.single.mediaAssetId, isNot('video1'));
    });

    test('videoItems 合成回退项时绑定字段保持缺席，不造值', () {
      final post = ContentPostViewData.fromWire(
        contentPostProjectionFixture(
          postId: 'video-legacy',
          contentType: 'video',
          videoUrl: _videoUrl,
        ),
      );

      final view = WorkBrowserViewData.fromPost(post);
      final fallback = view.videoItems.single;

      // 顶层 wire 未携带 mediaAssetId/accessMode 时保持缺席。
      expect(fallback.mediaAssetId, isNull);
      expect(fallback.accessMode, isNull);
      expect(fallback.coverAssetId, isNull);
    });
  });
}
