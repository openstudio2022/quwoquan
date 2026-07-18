import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/media_delivery_reference.dart';

void main() {
  const archivedAvatarKey =
      'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png';
  const archivedImageKey =
      'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png';
  const primaryVideoKey =
      'media/video/s/video-primary-0001/post/video-content-0001/source.mp4';
  const casObjectKey =
      'media/objects/sha256/aa/bb/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg';

  MediaEndpointConfig endpoints({
    required String avatar,
    required String image,
    required String video,
  }) {
    return MediaEndpointConfig(
      avatarBaseUrl: avatar,
      imageBaseUrl: image,
      videoBaseUrl: video,
      attachmentBaseUrl: image,
    );
  }

  group('MediaDeliveryReference naming contract', () {
    test('相对 key + 四份不同 MediaEndpointConfig 仅 authority 不同', () {
      final endpointPairs = <({String avatar, String image, String video})>[
        (
          avatar: 'https://alpha-avatar.example.test:17100',
          image: 'https://alpha-image.example.test:17100',
          video: 'https://alpha-video.example.test:17100',
        ),
        (
          avatar: 'https://beta-avatar.example.test:18100',
          image: 'https://beta-image.example.test:18100',
          video: 'https://beta-video.example.test:18100',
        ),
        (
          avatar: 'https://gamma-avatar.example.test:19100',
          image: 'https://gamma-image.example.test:19100',
          video: 'https://gamma-video.example.test:19100',
        ),
        (
          avatar: 'https://cdn.example.com',
          image: 'https://cdn.example.com',
          video: 'https://cdn.example.com',
        ),
      ];

      final urls = endpointPairs
          .map(
            (pair) =>
                MediaDeliveryResolver(
                  endpoints(
                    avatar: pair.avatar,
                    image: pair.image,
                    video: pair.video,
                  ),
                ).resolve(
                  archivedImageKey,
                  kind: MediaDeliveryKind.image,
                  assetId: 'content-cover-primary',
                  version: 1,
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
      expect(pathQueries.single.$1, '/$archivedImageKey');
      expect(pathQueries.single.$2, 'v=1');
      expect(
        urls.map((reference) => reference.deliveryUri.authority).toSet(),
        hasLength(4),
      );
    });

    test('拒绝 http、//、..、CAS path 与 kind 错配', () {
      final resolver = MediaDeliveryResolver(
        endpoints(
          avatar: 'https://avatar.example.com',
          image: 'https://image.example.com',
          video: 'https://video.example.com',
        ),
      );

      expect(
        resolver.tryResolve(
          'http://image.example.com/$archivedImageKey',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          '//image.example.com/$archivedImageKey',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          'media/image/s/archived-image/../cover.png',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(casObjectKey, kind: MediaDeliveryKind.image),
        isNull,
      );
      expect(
        () => resolver.resolve(casObjectKey, kind: MediaDeliveryKind.image),
        throwsA(
          isA<MediaDeliveryResolutionException>().having(
            (error) => error.failure,
            'failure',
            MediaDeliveryResolutionFailure.invalidCanonicalPath,
          ),
        ),
      );
      expect(
        resolver.tryResolve(archivedImageKey, kind: MediaDeliveryKind.video),
        isNull,
      );
      expect(
        resolver.tryResolve(primaryVideoKey, kind: MediaDeliveryKind.image),
        isNull,
      );
    });

    test('version>0 写入 v query；合法 archived/primary key 成功', () {
      final resolver = MediaDeliveryResolver(
        endpoints(
          avatar: 'https://avatar.example.com',
          image: 'https://image.example.com',
          video: 'https://video.example.com',
        ),
      );

      final avatar = resolver.resolve(
        archivedAvatarKey,
        kind: MediaDeliveryKind.avatar,
        version: 0,
      );
      expect(avatar.url, 'https://avatar.example.com/$archivedAvatarKey');
      expect(avatar.deliveryUri.query, isEmpty);

      final image = resolver.resolve(
        archivedImageKey,
        kind: MediaDeliveryKind.image,
        version: 9,
      );
      expect(image.url, 'https://image.example.com/$archivedImageKey?v=9');
      expect(image.version, 9);

      final video = resolver.resolve(
        primaryVideoKey,
        kind: MediaDeliveryKind.video,
        version: 3,
      );
      expect(video.url, 'https://video.example.com/$primaryVideoKey?v=3');
      expect(video.kind, MediaDeliveryKind.video);
    });

    test('视频首帧缩略图显式走 video authority，不把视频误投 image host', () {
      final resolver = MediaDeliveryResolver(
        endpoints(
          avatar: 'https://avatar.example.com',
          image: 'https://image.example.com',
          video: 'https://video.example.com',
        ),
      );

      final thumbnail = resolver.resolve(
        '$primaryVideoKey?variant=thumb&t=0',
        kind: MediaDeliveryKind.image,
      );

      expect(thumbnail.deliveryUri.origin, 'https://video.example.com');
      expect(thumbnail.deliveryUri.path, '/$primaryVideoKey');
      expect(thumbnail.deliveryUri.queryParameters, <String, String>{
        'variant': 'thumb',
        't': '0',
      });
      expect(thumbnail.kind, MediaDeliveryKind.image);
      expect(
        resolver.tryResolve(
          '$primaryVideoKey?variant=preview',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
    });
  });
}
