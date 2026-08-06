import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';
import 'package:quwoquan_app/runtime/transport/media/media_load_failure_cache.dart';

/// UAT 契约桩：证明沉浸视频旅程依赖的交付与负缓存合同在测试图中可组装。
///
/// 完整 Patrol/设备旅程需 alpha media edge + Simulator CA；本文件锁定
/// 分钟级与小时边界 canary 必须使用 manifest 可达相对 key，且 404 不会无限重打。
void main() {
  test('沉浸视频旅程使用 125 秒与小时边界受控媒体引用', () {
    final resolver = MediaDeliveryResolver(
      MediaEndpointConfig(
        avatarBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
        imageBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
        videoBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
        attachmentBaseUrl: 'https://cdn.alpha.quwoquan.com:17100',
      ),
    );
    final seekVideo = resolver.resolve(
      'media/video/s/media-canary-seek-125s/v1/source.mp4',
      kind: MediaDeliveryKind.video,
      assetId: 'media-canary-seek-125s',
      version: 1,
    );
    final previewManifest = resolver.resolve(
      'media/video/s/media-canary-seek-125s/v1/preview/manifest.json',
      kind: MediaDeliveryKind.video,
      assetId: 'media-canary-seek-125s',
      version: 1,
    );
    final hourVideo = resolver.resolve(
      'media/video/s/media-canary-hour-boundary-3595s/v1/source.mp4',
      kind: MediaDeliveryKind.video,
      assetId: 'media-canary-hour-boundary-3595s',
      version: 1,
    );
    expect(seekVideo.url, contains('cdn.alpha.quwoquan.com'));
    expect(seekVideo.url, contains('media-canary-seek-125s'));
    expect(previewManifest.url, contains('/preview/manifest.json'));
    expect(hourVideo.url, contains('media-canary-hour-boundary-3595s'));
    expect(seekVideo.url, isNot(contains('mock/seed')));
    expect(hourVideo.url, isNot(contains('mock/seed')));
  });

  test('封面 404 负缓存后同 identity 不再请求', () {
    final cache = MediaLoadFailureCache(
      defaultCooldown: const Duration(seconds: 60),
      now: () => DateTime.utc(2026, 7, 16, 12),
    );
    const identity =
        'https://cdn.alpha.quwoquan.com:17100/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png';
    cache.recordFailure(
      identity,
      error: Exception('HttpExceptionWithStatus(404): Invalid statusCode: 404'),
      candidateUrl: identity,
    );
    expect(cache.shouldSkipNetwork(identity), isTrue);
  });
}
