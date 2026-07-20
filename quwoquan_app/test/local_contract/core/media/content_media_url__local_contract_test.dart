import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';

void main() {
  const imageKey =
      'media/image/s/image-primary-0001/post/content-image-0001/cover.png';
  const videoKey =
      'media/video/s/video-primary-0001/post/video-content-0001/source.mp4';

  MediaEndpointConfig endpoints({
    required String image,
    required String video,
  }) {
    return MediaEndpointConfig(
      avatarBaseUrl: image,
      imageBaseUrl: image,
      videoBaseUrl: video,
      attachmentBaseUrl: image,
    );
  }

  group('MediaDeliveryResolver', () {
    test('只将公开 image slice key 与注入 image endpoint 组合', () {
      final resolved = MediaDeliveryResolver(
        endpoints(
          image: 'https://image.example.com',
          video: 'https://video.example.com',
        ),
      ).resolve(imageKey, kind: MediaDeliveryKind.image, version: 7);

      expect(resolved.url, 'https://image.example.com/$imageKey?v=7');
      expect(resolved.kind, MediaDeliveryKind.image);
      expect(resolved.version, 7);
    });

    test('视频类型由调用方声明，解析器不会从路径或扩展名猜测', () {
      final resolved = MediaDeliveryResolver(
        endpoints(
          image: 'https://image.example.com',
          video: 'https://video.example.com',
        ),
      ).resolve(videoKey, kind: MediaDeliveryKind.video, version: 3);

      expect(resolved.url, 'https://video.example.com/$videoKey?v=3');
      expect(resolved.kind, MediaDeliveryKind.video);
    });

    test('四份独立 endpoint 配置只改变 authority', () {
      final endpointPairs = <({String image, String video})>[
        (
          image: 'https://alpha-image.quwoquan-env.test:17100',
          video: 'https://alpha-video.quwoquan-env.test:17100',
        ),
        (
          image: 'https://beta-image.quwoquan-env.test:18100',
          video: 'https://beta-video.quwoquan-env.test:18100',
        ),
        (
          image: 'https://gamma-image.quwoquan-env.test:19100',
          video: 'https://gamma-video.quwoquan-env.test:19100',
        ),
        (image: 'https://cdn.quwoquan.com', video: 'https://cdn.quwoquan.com'),
      ];

      final urls = endpointPairs
          .map(
            (pair) =>
                MediaDeliveryResolver(
                  endpoints(image: pair.image, video: pair.video),
                ).resolve(
                  videoKey,
                  kind: MediaDeliveryKind.video,
                  assetId: 'content-video-primary',
                  version: 1,
                  sha256:
                      'sha256:0cd83d944a6ca7822b4a8306cecc60a36e859b041f6702c6a1ad9ead78924451',
                ),
          )
          .toList(growable: false);

      final pathQueries = urls
          .map(
            (reference) =>
                (reference.deliveryUri.path, reference.deliveryUri.query),
          )
          .toSet();
      expect(pathQueries, hasLength(1));
      expect(
        urls.map((reference) => reference.deliveryUri.authority).toSet(),
        hasLength(4),
      );
      expect(
        urls.map((reference) => reference.cacheIdentity).toSet(),
        hasLength(4),
      );
    });

    test('拒绝未注入 origin、非 HTTPS、非 canonical path 与 kind 错配', () {
      final resolver = MediaDeliveryResolver(
        endpoints(
          image: 'https://image.example.com',
          video: 'https://video.example.com',
        ),
      );

      expect(
        resolver.tryResolve(
          'https://third-party.example.com/$imageKey',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          'http://image.example.com/$imageKey',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          '//image.example.com/$imageKey',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          'media/image/s/image-primary-0001/../cover.png',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(imageKey, kind: MediaDeliveryKind.video),
        isNull,
      );
    });
  });

  group('legacy string bridge', () {
    test('未注入运行时端点时不构造网络候选', () {
      expect(
        resolveContentMediaUrlCandidates(
          imageKey,
          imageCdnBaseUrl: '',
          videoCdnBaseUrl: '',
        ),
        isEmpty,
      );
      expect(
        resolveContentVideoUrlCandidates(
          videoKey,
          imageCdnBaseUrl: '',
          videoCdnBaseUrl: '',
        ),
        isEmpty,
      );
    });

    test('返回唯一注入 endpoint URL，不再生成 gateway 或主机候选', () {
      expect(
        resolveContentVideoUrlCandidates(
          videoKey,
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image.example.com',
          videoCdnBaseUrl: 'https://video.example.com',
        ),
        <String>['https://video.example.com/$videoKey'],
      );
    });

    test('拒绝未受信任 absolute URL，保留本地图片预览来源', () {
      expect(
        resolveContentMediaUrl(
          'https://third-party.example.com/$imageKey',
          imageCdnBaseUrl: 'https://image.example.com',
        ),
        isEmpty,
      );
      expect(
        resolveContentMediaUrlCandidates('file:///tmp/photo.jpg'),
        <String>['file:///tmp/photo.jpg'],
      );
    });
  });
}
