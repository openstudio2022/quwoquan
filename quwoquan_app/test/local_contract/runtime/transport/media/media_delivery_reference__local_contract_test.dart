// spec_ref: specs/feature-tree/runtime/runtime-media/media-upload-and-storage/spec.md#gwt-002

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/transport/media/media_delivery_reference.dart';

void main() {
  const archivedAvatarKey =
      'media/avatar/s/archived-avatar/user/fixture_user_current/v1/avatar.png';
  const archivedImageKey =
      'media/image/s/archived-image/post/fixture_photo_001/v1/cover.png';
  const primaryVideoKey =
      'media/video/s/video-primary-0001/post/video-content-0001/v1/source.mp4';
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
          avatar: 'https://cdn.alpha.example.invalid:17100/media/avatar',
          image: 'https://cdn.alpha.example.invalid:17100/media/image',
          video: 'https://cdn.alpha.example.invalid:17100/media/video',
        ),
        (
          avatar: 'https://cdn.beta.example.invalid:18100/media/avatar',
          image: 'https://cdn.beta.example.invalid:18100/media/image',
          video: 'https://cdn.beta.example.invalid:18100/media/video',
        ),
        (
          avatar: 'https://cdn.gamma.example.invalid:19100/media/avatar',
          image: 'https://cdn.gamma.example.invalid:19100/media/image',
          video: 'https://cdn.gamma.example.invalid:19100/media/video',
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
      expect(pathQueries.single.$2, isEmpty);
      expect(
        urls.map((reference) => reference.deliveryUri.authority).toSet(),
        hasLength(4),
      );
    });

    test('attachment 由同一 CDN origin 的 /media/attachment slice 解析', () {
      final resolver = MediaDeliveryResolver(
        endpoints(
          avatar: 'https://cdn.example.invalid/media/avatar',
          image: 'https://cdn.example.invalid/media/image',
          video: 'https://cdn.example.invalid/media/video',
        ),
      );
      final reference = resolver.resolve(
        'media/attachment/s/asset/attachment_001/v1/source.pdf',
        kind: MediaDeliveryKind.attachment,
        assetId: 'attachment_001',
        version: 1,
      );
      expect(
        reference.url,
        'https://cdn.example.invalid/media/attachment/s/asset/'
        'attachment_001/v1/source.pdf',
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

    test('路径版本是唯一缓存身份，版本 query、无版本路径与漂移均 fail-closed', () {
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
      expect(avatar.version, 1);

      final image = resolver.resolve(
        archivedImageKey,
        kind: MediaDeliveryKind.image,
        version: 1,
      );
      expect(image.url, 'https://image.example.com/$archivedImageKey');
      expect(image.version, 1);

      final video = resolver.resolve(
        primaryVideoKey,
        kind: MediaDeliveryKind.video,
        version: 1,
      );
      expect(video.url, 'https://video.example.com/$primaryVideoKey');
      expect(video.kind, MediaDeliveryKind.video);

      expect(
        resolver.tryResolve(
          archivedImageKey,
          kind: MediaDeliveryKind.image,
          version: 9,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          '$archivedImageKey?v=1',
          kind: MediaDeliveryKind.image,
          version: 1,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          'media/image/s/archived-image/post/fixture_photo_001/cover.png',
          kind: MediaDeliveryKind.image,
          version: 1,
        ),
        isNull,
      );
      expect(
        resolver.tryResolve(
          '$archivedImageKey?sign=untrusted&t=1',
          kind: MediaDeliveryKind.image,
        ),
        isNull,
      );
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
