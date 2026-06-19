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
          gatewayBaseUrl: 'http://127.0.0.1:18080/',
          imageCdnBaseUrl: 'http://127.0.0.1:18088/',
        ),
        'http://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
      );
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'http://127.0.0.1:18080/',
          imageCdnBaseUrl: 'http://127.0.0.1:18088/',
        ),
        <String>[
          'http://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'http://localhost:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'http://10.0.2.2:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'http://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'http://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'http://10.0.2.2:18080/media/image/s/archived-image/post/demo/v1/cover.png',
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
          'https://10.0.2.2:18088/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          'https://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          'https://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
          'https://10.0.2.2:18080/media/image/s/archived-image/post/demo/v1/cover.png?v=2',
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
        gatewayBaseUrl: 'http://127.0.0.1:18080',
        imageCdnBaseUrl: 'http://127.0.0.1:18088',
      );
      expect(candidates, isNotEmpty);
      expect(
        candidates.first,
        startsWith(
          'http://127.0.0.1:18088/media/image/s/archived-image/post/fixture_',
        ),
      );
      expect(candidates.join('\n'), isNot(contains('/mock/seed/')));
    });

    test(
      'rewrites malformed archived seed images to archived fixture images',
      () {
        final candidates = resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/seed/p_1501785888041-af3ef285b470/v1/image.jpg',
          gatewayBaseUrl: 'http://127.0.0.1:18080',
          imageCdnBaseUrl: 'http://127.0.0.1:18088',
        );
        expect(candidates, isNotEmpty);
        expect(
          candidates.first,
          startsWith(
            'http://127.0.0.1:18088/media/image/s/archived-image/post/fixture_',
          ),
        );
        expect(candidates.join('\n'), isNot(contains('/archived-image/seed/')));
      },
    );

    test('rewrites archived mock videos to archived playable sample', () {
      final candidates = resolveContentMediaUrlCandidates(
        'media/video/s/mock/seed/v_demo/v1/play.mp4',
        gatewayBaseUrl: 'http://127.0.0.1:18080',
        imageCdnBaseUrl: 'http://127.0.0.1:18088',
        videoCdnBaseUrl: 'http://127.0.0.1:18088',
      );
      expect(candidates, <String>[
        'http://127.0.0.1:18088/media/video/s/archived-video/beta-sample.mp4',
        'http://localhost:18088/media/video/s/archived-video/beta-sample.mp4',
        'http://10.0.2.2:18088/media/video/s/archived-video/beta-sample.mp4',
        'http://127.0.0.1:18080/media/video/s/archived-video/beta-sample.mp4',
        'http://localhost:18080/media/video/s/archived-video/beta-sample.mp4',
        'http://10.0.2.2:18080/media/video/s/archived-video/beta-sample.mp4',
      ]);
    });

    test('rewrites alpha mock example videos to archived playable sample', () {
      final candidates = resolveContentMediaUrlCandidates(
        'media/video/s/mock/example/0ebb6c7e7d9e/v1/video.mp4',
        gatewayBaseUrl: 'http://127.0.0.1:18080',
        imageCdnBaseUrl: 'http://127.0.0.1:18088',
        videoCdnBaseUrl: 'http://127.0.0.1:18088',
      );
      expect(candidates, isNotEmpty);
      expect(
        candidates.first,
        'http://127.0.0.1:18088/media/video/s/archived-video/beta-sample.mp4',
      );
      expect(candidates.join('\n'), isNot(contains('/mock/example/')));
    });

    test('supports Android emulator private host ordering', () {
      expect(
        resolveContentMediaUrlCandidates(
          'media/image/s/archived-image/post/demo/v1/cover.png',
          gatewayBaseUrl: 'https://10.0.2.2:18080/',
          imageCdnBaseUrl: 'https://10.0.2.2:18088/',
        ),
        <String>[
          'https://10.0.2.2:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://127.0.0.1:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18088/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://10.0.2.2:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://127.0.0.1:18080/media/image/s/archived-image/post/demo/v1/cover.png',
          'https://localhost:18080/media/image/s/archived-image/post/demo/v1/cover.png',
        ],
      );
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
    });

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
          'https://image-cdn.example.com/media/image/s/archived-image/post/demo/v1/cover.png',
        ),
        isFalse,
      );
    });
  });
}
