import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';
import 'package:quwoquan_app/core/media/media_load_failure_cache.dart';

/// UAT 契约桩：证明沉浸视频旅程依赖的交付与负缓存合同在测试图中可组装。
///
/// 完整 Patrol/设备旅程需 alpha media edge + Simulator CA；本文件锁定
/// 「自然摄影师」类内容必须使用 manifest 可达相对 key，且 404 不会无限重打。
void main() {
  test('沉浸视频旅程媒体引用必须是 video-primary + archived cover', () {
    final resolver = MediaDeliveryResolver(
      MediaEndpointConfig(
        avatarBaseUrl: 'https://alpha-avatar.quwoquan-env.test:17100',
        imageBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
        videoBaseUrl: 'https://alpha-video.quwoquan-env.test:17100',
        attachmentBaseUrl: 'https://alpha-image.quwoquan-env.test:17100',
      ),
    );
    final video = resolver.resolve(
      'media/video/s/video-primary-0001/post/video-content-0001/source.mp4',
      kind: MediaDeliveryKind.video,
      version: 1,
    );
    final cover = resolver.resolve(
      'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png',
      kind: MediaDeliveryKind.image,
      version: 1,
    );
    expect(video.url, contains('alpha-video.quwoquan-env.test'));
    expect(video.url, contains('video-primary-0001'));
    expect(cover.url, contains('archived-image'));
    expect(video.url, isNot(contains('mock/seed')));
    expect(cover.url, isNot(contains('mock/seed')));
  });

  test('封面 404 负缓存后同 identity 不再请求', () {
    final cache = MediaLoadFailureCache(
      defaultCooldown: const Duration(seconds: 60),
      now: () => DateTime.utc(2026, 7, 16, 12),
    );
    const identity =
        'https://alpha-image.quwoquan-env.test:17100/media/image/s/archived-image/post/fixture_photo_001/v1/cover.png';
    cache.recordFailure(
      identity,
      error: Exception('HttpExceptionWithStatus(404): Invalid statusCode: 404'),
      candidateUrl: identity,
    );
    expect(cache.shouldSkipNetwork(identity), isTrue);
  });
}
