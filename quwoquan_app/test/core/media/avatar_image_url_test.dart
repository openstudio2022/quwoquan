import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';

void main() {
  group('resolveAvatarImageUrl', () {
    test('keeps absolute http/https avatar URLs', () {
      expect(
        resolveAvatarImageUrl('https://cdn.example.com/u.png'),
        'https://cdn.example.com/u.png',
      );
      expect(
        resolveAvatarImageUrl('http://media.example.com/u.png'),
        'http://media.example.com/u.png',
      );
    });

    test('resolves media paths against non-loopback avatar CDN first', () {
      expect(
        resolveAvatarImageUrl(
          '/media/avatar/conversation/conv_1/v2/hash.png?v=2',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://beta-media.example.com/',
        ),
        'https://beta-media.example.com/media/avatar/conversation/conv_1/v2/hash.png?v=2',
      );
    });

    test('uses explicit avatar CDN for local media paths', () {
      expect(
        resolveAvatarImageUrl(
          'media/avatar/default/group/v1/default.png',
          gatewayBaseUrl: 'http://127.0.0.1:18080/',
          avatarCdnBaseUrl: 'http://127.0.0.1:18088/',
        ),
        'http://127.0.0.1:18088/media/avatar/default/group/v1/default.png',
      );
    });

    test('uses explicit beta avatar CDN when both bases are loopback', () {
      expect(
        resolveAvatarImageUrl(
          '/media/avatar/beta-avatar.png',
          gatewayBaseUrl: 'http://127.0.0.1:18080/',
          avatarCdnBaseUrl: 'http://127.0.0.1:18088/',
        ),
        'http://127.0.0.1:18088/media/avatar/beta-avatar.png',
      );
      expect(
        resolveAvatarImageUrlCandidates(
          '/media/avatar/beta-avatar.png',
          gatewayBaseUrl: 'http://127.0.0.1:18080/',
          avatarCdnBaseUrl: 'http://127.0.0.1:18088/',
        ),
        <String>[
          'http://127.0.0.1:18088/media/avatar/beta-avatar.png',
          'http://127.0.0.1:18080/media/avatar/beta-avatar.png',
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

    test('rewrites loopback absolute media URLs for iPad beta', () {
      expect(
        resolveAvatarImageUrl(
          'http://127.0.0.1:18088/media/avatar/conversation/conv_1/v3/hash.png?v=3',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://beta-gateway.example.com',
        ),
        'https://beta-gateway.example.com/media/avatar/conversation/conv_1/v3/hash.png?v=3',
      );
    });

    test(
      'keeps beta simulator media port when avatar CDN matches loopback',
      () {
        expect(
          resolveAvatarImageUrl(
            'http://127.0.0.1:18088/media/avatar/beta-avatar.png',
            gatewayBaseUrl: 'http://127.0.0.1:18080',
            avatarCdnBaseUrl: 'http://127.0.0.1:18088',
          ),
          'http://127.0.0.1:18088/media/avatar/beta-avatar.png',
        );
        expect(
          resolveAvatarImageUrlCandidates(
            'http://127.0.0.1:18088/media/avatar/beta-avatar.png',
            gatewayBaseUrl: 'http://127.0.0.1:18080',
            avatarCdnBaseUrl: 'http://127.0.0.1:18088',
          ),
          <String>[
            'http://127.0.0.1:18088/media/avatar/beta-avatar.png',
            'http://127.0.0.1:18080/media/avatar/beta-avatar.png',
          ],
        );
      },
    );

    test('rewrites http media URLs when configured avatar base is https', () {
      expect(
        resolveAvatarImageUrl(
          'http://media.example.com/media/avatar/user/u1/v1/profile.png',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://cdn.example.com',
        ),
        'https://cdn.example.com/media/avatar/user/u1/v1/profile.png',
      );
    });

    test('keeps non-media absolute URLs unchanged', () {
      expect(
        resolveAvatarImageUrl(
          'http://example.com/profile-avatar.png',
          gatewayBaseUrl: 'https://beta-gateway.example.com',
          avatarCdnBaseUrl: 'https://cdn.example.com',
        ),
        'http://example.com/profile-avatar.png',
      );
    });
  });
}
