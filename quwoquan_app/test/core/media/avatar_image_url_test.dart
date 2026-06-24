import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';

void main() {
  group('resolveAvatarImageUrl', () {
    test('drops arbitrary absolute avatar URLs', () {
      expect(resolveAvatarImageUrl('https://cdn.example.com/u.png'), isEmpty);
    });

    test('resolves media paths against non-loopback avatar CDN first', () {
      expect(
        resolveAvatarImageUrl(
          '/media/avatar/s/archived-avatar/conversation/conv_1/v2/hash.png?v=2',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://beta-media.example.com/',
        ),
        'https://beta-media.example.com/media/avatar/s/archived-avatar/conversation/conv_1/v2/hash.png?v=2',
      );
    });

    test('uses explicit avatar CDN for local media paths', () {
      expect(
        resolveAvatarImageUrl(
          'media/avatar/s/archived-avatar/default/group/v1/default.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080/',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088/',
        ),
        'https://127.0.0.1:18088/media/avatar/s/archived-avatar/default/group/v1/default.png',
      );
    });

    test('appends avatarVersion to cache key when raw path lacks query', () {
      expect(
        resolveAvatarImageUrl(
          'media/avatar/s/archived-avatar/user/u1/v1/profile.png',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://cdn.example.com',
          avatarVersion: 12,
        ),
        'https://cdn.example.com/media/avatar/s/archived-avatar/user/u1/v1/profile.png?v=12',
      );
    });

    test('overrides stale v query with explicit avatarVersion', () {
      expect(
        resolveAvatarImageUrl(
          'https://cdn.example.com/media/avatar/s/archived-avatar/user/u1/v1/profile.png?v=3',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://cdn.example.com',
          avatarVersion: 18,
        ),
        'https://cdn.example.com/media/avatar/s/archived-avatar/user/u1/v1/profile.png?v=18',
      );
    });

    test('uses explicit beta avatar CDN when both bases are loopback', () {
      expect(
        resolveAvatarImageUrl(
          '/media/avatar/s/archived-avatar/beta-avatar.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080/',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088/',
        ),
        'https://127.0.0.1:18088/media/avatar/s/archived-avatar/beta-avatar.png',
      );
      expect(
        resolveAvatarImageUrlCandidates(
          '/media/avatar/s/archived-avatar/beta-avatar.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080/',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088/',
        ),
        <String>[
          'https://127.0.0.1:18088/media/avatar/s/archived-avatar/beta-avatar.png',
          'https://127.0.0.1:18080/media/avatar/s/archived-avatar/beta-avatar.png',
        ],
      );
    });

    test('expands secure local env domains to HTTPS loopback candidates', () {
      expect(
        resolveAvatarImageUrlCandidates(
          'media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          gatewayBaseUrl: 'https://alpha-api.quwoquan-env.test:17000',
          avatarCdnBaseUrl: 'https://alpha-avatar.quwoquan-env.test:17100',
        ),
        <String>[
          'https://localhost:17100/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://127.0.0.1:17100/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://10.0.2.2:17100/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://alpha-avatar.quwoquan-env.test:17100/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://localhost:17000/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://127.0.0.1:17000/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://10.0.2.2:17000/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
          'https://alpha-api.quwoquan-env.test:17000/media/avatar/s/archived-avatar/circle/demo/v1/avatar.png',
        ],
      );
    });

    test(
      'rejects non-url placeholder text so UI uses fallback intentionally',
      () {
        expect(
          resolveAvatarImageUrl(
            '契',
            gatewayBaseUrl: 'https://beta-gateway.example.com',
            avatarCdnBaseUrl: 'https://beta-media.example.com',
          ),
          isEmpty,
        );
      },
    );

    test('keeps loopback absolute media URLs on https for iPad beta', () {
      expect(
        resolveAvatarImageUrl(
          'https://127.0.0.1:18088/media/avatar/s/archived-avatar/conversation/conv_1/v3/hash.png?v=3',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://beta-gateway.example.com',
        ),
        'https://beta-gateway.example.com/media/avatar/s/archived-avatar/conversation/conv_1/v3/hash.png?v=3',
      );
    });

    test('keeps beta simulator media port when avatar CDN matches https loopback', () {
      expect(
        resolveAvatarImageUrl(
          'https://127.0.0.1:18088/media/avatar/s/archived-avatar/beta-avatar.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088',
        ),
        'https://127.0.0.1:18088/media/avatar/s/archived-avatar/beta-avatar.png',
      );
      expect(
        resolveAvatarImageUrlCandidates(
          'https://127.0.0.1:18088/media/avatar/s/archived-avatar/beta-avatar.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088',
        ),
        <String>[
          'https://127.0.0.1:18088/media/avatar/s/archived-avatar/beta-avatar.png',
          'https://127.0.0.1:18080/media/avatar/s/archived-avatar/beta-avatar.png',
        ],
      );
    });

    test('rewrites untrusted absolute media URLs through configured base', () {
      expect(
        resolveAvatarImageUrl(
          'https://media.example.com/media/avatar/s/archived-avatar/user/u1/v1/profile.png',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://cdn.example.com',
        ),
        'https://cdn.example.com/media/avatar/s/archived-avatar/user/u1/v1/profile.png',
      );
    });

    test('rewrites archived mock seed avatars to archived fixture avatars', () {
      final candidates = resolveAvatarImageUrlCandidates(
        'media/avatar/s/mock/seed/u_1599566150163-29194dcaad36/v1/avatar.jpg',
        gatewayBaseUrl: 'https://127.0.0.1:18080',
        avatarCdnBaseUrl: 'https://127.0.0.1:18088',
      );
      expect(candidates, hasLength(2));
      expect(
        candidates.first,
        startsWith(
          'https://127.0.0.1:18088/media/avatar/s/archived-avatar/user/fixture_user_',
        ),
      );
      expect(candidates.first, isNot(contains('/mock/seed/')));
      expect(
        candidates.last,
        startsWith(
          'https://127.0.0.1:18080/media/avatar/s/archived-avatar/user/fixture_user_',
        ),
      );
      expect(candidates.last, isNot(contains('/mock/seed/')));
    });

    test(
      'rewrites archived mock user avatars and malformed archived seed avatars',
      () {
        final mockUserCandidates = resolveAvatarImageUrlCandidates(
          'media/avatar/s/mock/user/user_001/v1/avatar.png',
          gatewayBaseUrl: 'https://127.0.0.1:18080',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088',
        );
        expect(mockUserCandidates, hasLength(2));
        expect(
          mockUserCandidates.first,
          startsWith(
            'https://127.0.0.1:18088/media/avatar/s/archived-avatar/user/fixture_user_',
          ),
        );
        expect(mockUserCandidates.join('\n'), isNot(contains('/mock/user/')));

        final malformedArchivedCandidates = resolveAvatarImageUrlCandidates(
          'media/avatar/s/archived-avatar/seed/u_1599566150163-29194dcaad36/v1/avatar.jpg',
          gatewayBaseUrl: 'https://127.0.0.1:18080',
          avatarCdnBaseUrl: 'https://127.0.0.1:18088',
        );
        expect(malformedArchivedCandidates, hasLength(2));
        expect(
          malformedArchivedCandidates.first,
          startsWith(
            'https://127.0.0.1:18088/media/avatar/s/archived-avatar/user/fixture_user_',
          ),
        );
        expect(
          malformedArchivedCandidates.join('\n'),
          isNot(contains('/archived-avatar/seed/')),
        );
      },
    );

    test('drops non-media absolute URLs from untrusted hosts', () {
      expect(
        resolveAvatarImageUrl(
          'https://example.com/profile-avatar.png',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://cdn.example.com',
        ),
        isEmpty,
      );
    });
  });
}
