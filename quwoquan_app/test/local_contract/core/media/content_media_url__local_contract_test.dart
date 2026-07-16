import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';

void main() {
  group('resolveContentMediaUrl', () {
    test('drops non-media absolute URLs from untrusted hosts', () {
      expect(
        resolveContentMediaUrl(
          'https://static.example.com/banner.png',
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image-cdn.example.com',
        ),
        isEmpty,
      );
    });

    test('prefers image CDN first for non-loopback image media', () {
      expect(
        resolveContentMediaUrl(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image-cdn.example.com/',
        ),
        'https://image-cdn.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
      );
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image-cdn.example.com/',
        ),
        <String>[
          'https://image-cdn.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://api.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
    });

    test('keeps explicit local media base first for loopback image media', () {
      expect(
        resolveContentMediaUrl(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080/',
          imageCdnBaseUrl: 'https://127.0.0.1:18088/',
        ),
        'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
      );
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080/',
          imageCdnBaseUrl: 'https://127.0.0.1:18088/',
        ),
        <String>[
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
    });

    test('keeps loopback absolute media URLs aligned to explicit media base', () {
      expect(
        resolveContentMediaUrl(
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          gatewayBaseUrl: 'https://127.0.0.1:18080',
          imageCdnBaseUrl: 'https://127.0.0.1:18088',
        ),
        'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
      );
      expect(
        resolveContentMediaUrlCandidates(
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          gatewayBaseUrl: 'https://127.0.0.1:18080',
          imageCdnBaseUrl: 'https://127.0.0.1:18088',
        ),
        <String>[
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          'https://localhost:18088/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          'https://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          'https://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
        ],
      );
    });

    test('uses video CDN family for video media paths', () {
      expect(
        resolveContentMediaUrl(
          'media/video/s/archived-video/post/demo/v1/play.mp4',
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image-cdn.example.com',
          videoCdnBaseUrl: 'https://video-cdn.example.com',
        ),
        'https://video-cdn.example.com/media/video/s/archived-video/post/demo/v1/play.mp4',
      );
      expect(
        resolveContentMediaUrlCandidates(
          'media/video/s/archived-video/post/demo/v1/play.mp4',
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image-cdn.example.com',
          videoCdnBaseUrl: 'https://video-cdn.example.com',
        ),
        <String>[
          'https://video-cdn.example.com/media/video/s/archived-video/post/demo/v1/play.mp4',
          'https://api.example.com/media/video/s/archived-video/post/demo/v1/play.mp4',
        ],
      );
    });

    test('video resolver rejects image cover paths across local envs', () {
      const imageObjectKey =
          'media/image/s/archived-image/post/fixture_photo_002/v1/cover.png';
      final cases = <({String api, String image, String video})>[
        (
          api: 'alpha-api.quwoquan-env.test:17000',
          image: 'alpha-image.quwoquan-env.test:17100',
          video: 'alpha-video.quwoquan-env.test:17100',
        ),
        (
          api: 'beta-api.quwoquan-env.test:18000',
          image: 'beta-image.quwoquan-env.test:18100',
          video: 'beta-video.quwoquan-env.test:18100',
        ),
        (
          api: 'gamma-api.quwoquan-env.test:19000',
          image: 'gamma-image.quwoquan-env.test:19100',
          video: 'gamma-video.quwoquan-env.test:19100',
        ),
        (
          api: 'prod-api.quwoquan-env.test:20000',
          image: 'prod-image.quwoquan-env.test:20100',
          video: 'prod-video.quwoquan-env.test:20100',
        ),
      ];

      for (final scenario in cases) {
        expect(
          resolveContentVideoUrlCandidates(
            imageObjectKey,
            gatewayBaseUrl: 'https://${scenario.api}',
            imageCdnBaseUrl: 'https://${scenario.image}',
            videoCdnBaseUrl: 'https://${scenario.video}',
          ),
          isEmpty,
          reason: scenario.api,
        );
        expect(
          resolveContentVideoUrlCandidates(
            'https://${scenario.image}/$imageObjectKey',
            gatewayBaseUrl: 'https://${scenario.api}',
            imageCdnBaseUrl: 'https://${scenario.image}',
            videoCdnBaseUrl: 'https://${scenario.video}',
          ),
          isEmpty,
          reason: scenario.image,
        );
      }
    });

    test('video resolver keeps playable video paths across local envs', () {
      const videoObjectKey = 'media/video/s/archived-video/beta-sample.mp4';
      final cases = <({String api, String video})>[
        (
          api: 'alpha-api.quwoquan-env.test:17000',
          video: 'alpha-video.quwoquan-env.test:17100',
        ),
        (
          api: 'beta-api.quwoquan-env.test:18000',
          video: 'beta-video.quwoquan-env.test:18100',
        ),
        (
          api: 'gamma-api.quwoquan-env.test:19000',
          video: 'gamma-video.quwoquan-env.test:19100',
        ),
        (
          api: 'prod-api.quwoquan-env.test:20000',
          video: 'prod-video.quwoquan-env.test:20100',
        ),
      ];

      for (final scenario in cases) {
        final videoPort = scenario.video.split(':').last;
        final apiPort = scenario.api.split(':').last;
        expect(
          resolveContentVideoUrlCandidates(
            videoObjectKey,
            gatewayBaseUrl: 'https://${scenario.api}',
            videoCdnBaseUrl: 'https://${scenario.video}',
          ),
          <String>[
            'https://127.0.0.1:$videoPort/$videoObjectKey',
            'https://localhost:$videoPort/$videoObjectKey',
            'https://${scenario.video}/$videoObjectKey',
            'https://127.0.0.1:$apiPort/$videoObjectKey',
            'https://localhost:$apiPort/$videoObjectKey',
            'https://${scenario.api}/$videoObjectKey',
          ],
          reason: scenario.api,
        );
      }
    });

    test('rewrites untrusted absolute media URLs through configured base', () {
      expect(
        resolveContentMediaUrlCandidates(
          'https://third-party.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://api.example.com',
          imageCdnBaseUrl: 'https://image-cdn.example.com',
        ),
        <String>[
          'https://image-cdn.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://api.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
    });

    test('rewrites archived mock seed images to archived fixture images', () {
      final candidates = resolveContentMediaUrlCandidates(
        'media/image/s/mock/seed/p_1501785888041-af3ef285b470/v1/image.jpg',
        gatewayBaseUrl: 'https://127.0.0.1:18080',
        imageCdnBaseUrl: 'https://127.0.0.1:18088',
      );
      expect(candidates, isNotEmpty);
      expect(
        candidates.first,
        startsWith(
          'https://127.0.0.1:18088/media/image/s/archived-image/post/fixture_',
        ),
      );
      expect(candidates.join('\n'), isNot(contains('/mock/seed/')));
    });

    test('rewrites malformed archived seed images to archived fixture images', () {
      final candidates = resolveContentMediaUrlCandidates(
        'media/image/s/archived-image/seed/p_1501785888041-af3ef285b470/v1/image.jpg',
        gatewayBaseUrl: 'https://127.0.0.1:18080',
        imageCdnBaseUrl: 'https://127.0.0.1:18088',
      );
      expect(candidates, isNotEmpty);
      expect(
        candidates.first,
        startsWith(
          'https://127.0.0.1:18088/media/image/s/archived-image/post/fixture_',
        ),
      );
      expect(candidates.join('\n'), isNot(contains('/archived-image/seed/')));
    });

    test('rewrites archived mock videos to archived playable sample', () {
      final candidates = resolveContentMediaUrlCandidates(
        'media/video/s/mock/seed/v_demo/v1/play.mp4',
        gatewayBaseUrl: 'https://127.0.0.1:18080',
        imageCdnBaseUrl: 'https://127.0.0.1:18088',
        videoCdnBaseUrl: 'https://127.0.0.1:18088',
      );
      expect(candidates, <String>[
        'https://127.0.0.1:18088/media/video/s/archived-video/beta-sample.mp4',
        'https://localhost:18088/media/video/s/archived-video/beta-sample.mp4',
        'https://127.0.0.1:18080/media/video/s/archived-video/beta-sample.mp4',
        'https://localhost:18080/media/video/s/archived-video/beta-sample.mp4',
      ]);
    });

    test('rewrites alpha mock example videos to archived playable sample', () {
      final candidates = resolveContentMediaUrlCandidates(
        'media/video/s/mock/example/0ebb6c7e7d9e/v1/video.mp4',
        gatewayBaseUrl: 'https://127.0.0.1:18080',
        imageCdnBaseUrl: 'https://127.0.0.1:18088',
        videoCdnBaseUrl: 'https://127.0.0.1:18088',
      );
      expect(candidates, isNotEmpty);
      expect(
        candidates.first,
        'https://127.0.0.1:18088/media/video/s/archived-video/beta-sample.mp4',
      );
      expect(candidates.join('\n'), isNot(contains('/mock/example/')));
    });

    test('normalizes secure Android-emulator media base to loopback HTTPS', () {
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://10.0.2.2:18080/',
          imageCdnBaseUrl: 'https://10.0.2.2:18088/',
        ),
        <String>[
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
    });

    test('upgrades cleartext Android-emulator media base to loopback HTTPS', () {
      const cleartextScheme = 'http';
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: '$cleartextScheme://10.0.2.2:18080/',
          imageCdnBaseUrl: '$cleartextScheme://10.0.2.2:18088/',
        ),
        <String>[
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
    });

    test('expands secure local env domains by manifest port profile', () {
      const objectKey = 'media/image/s/archived-image/post/demo/v1/cover.png';
      final cases = <({String api, String image})>[
        (
          api: 'alpha-api.quwoquan-env.test:17000',
          image: 'alpha-image.quwoquan-env.test:17100',
        ),
        (
          api: 'beta-api.quwoquan-env.test:18000',
          image: 'beta-image.quwoquan-env.test:18100',
        ),
        (
          api: 'gamma-api.quwoquan-env.test:19000',
          image: 'gamma-image.quwoquan-env.test:19100',
        ),
        (
          api: 'prod-api.quwoquan-env.test:20000',
          image: 'prod-image.quwoquan-env.test:20100',
        ),
      ];

      for (final scenario in cases) {
        final imagePort = scenario.image.split(':').last;
        final apiPort = scenario.api.split(':').last;
        final candidates = resolveContentMediaUrlCandidates(
          objectKey,
          gatewayBaseUrl: 'https://${scenario.api}',
          imageCdnBaseUrl: 'https://${scenario.image}',
        );
        expect(candidates, <String>[
          'https://127.0.0.1:$imagePort/$objectKey',
          'https://localhost:$imagePort/$objectKey',
          'https://${scenario.image}/$objectKey',
          'https://127.0.0.1:$apiPort/$objectKey',
          'https://localhost:$apiPort/$objectKey',
          'https://${scenario.api}/$objectKey',
        ], reason: scenario.api);
        expect(candidates.join('\n'), isNot(contains('https://10.0.2.2')));
      }
    });

    test('keeps prod-hosted remote https media base candidates', () {
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://118.31.239.122:19000/',
          imageCdnBaseUrl: 'https://118.31.239.122:19100/',
        ),
        <String>[
          'https://118.31.239.122:19100/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://118.31.239.122:19000/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
      expect(
        resolveContentMediaUrlCandidates(
          'media/video/s/archived-video/beta-sample.mp4',
          gatewayBaseUrl: 'https://118.31.239.122:19000/',
          imageCdnBaseUrl: 'https://118.31.239.122:19100/',
          videoCdnBaseUrl: 'https://118.31.239.122:19100/',
        ),
        <String>[
          'https://118.31.239.122:19100/media/video/s/archived-video/beta-sample.mp4',
          'https://118.31.239.122:19000/media/video/s/archived-video/beta-sample.mp4',
        ],
      );
    });

    test(
      'loopback transport plane omits unresolvable canonical env.test hosts',
      () {
        expect(
          resolveContentMediaUrlCandidates(
            'https://alpha-image.quwoquan-env.test:17100/media/image/s/archived-image/post/demo/v1/cover.png',
            gatewayBaseUrl: 'https://localhost:17000',
            imageCdnBaseUrl: 'https://localhost:17100',
          ),
          <String>[
            'https://127.0.0.1:17100/media/image/s/archived-image/post/demo/v1/cover.png',
            'https://localhost:17100/media/image/s/archived-image/post/demo/v1/cover.png',
            'https://127.0.0.1:17000/media/image/s/archived-image/post/demo/v1/cover.png',
            'https://localhost:17000/media/image/s/archived-image/post/demo/v1/cover.png',
          ],
        );
        expect(
          resolveContentMediaUrlCandidates(
            'media/image/s/archived-image/post/demo/v1/cover.png',
            gatewayBaseUrl: 'https://alpha-api.localhost:17000',
            imageCdnBaseUrl: 'https://alpha-image.localhost:17100',
          ),
          <String>[
            'https://alpha-image.localhost:17100/media/image/s/archived-image/post/demo/v1/cover.png',
            'https://alpha-api.localhost:17000/media/image/s/archived-image/post/demo/v1/cover.png',
          ],
        );
      },
    );

    test('identifies private dev content media URLs', () {
      expect(
        isPrivateDevContentMediaUrl(
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
        ),
        isTrue,
      );
      expect(
        isPrivateDevContentMediaUrl(
          'https://10.0.2.2:18080/media/image/s/archived-image/post/demo/v1/cover.png',
        ),
        isTrue,
      );
      expect(
        isPrivateDevContentMediaUrl(
          'https://alpha-image.quwoquan-env.test:17100/media/image/s/archived-image/post/demo/v1/cover.png',
        ),
        isTrue,
      );
      expect(
        isPrivateDevContentMediaUrl(
          'https://image-cdn.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
        ),
        isFalse,
      );
    });
  });
}
