import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/avatar_image_url.dart';

void main() {
  const avatarKey =
      'media/avatar/s/avatar-primary-0001/persona/persona-primary/v1/avatar.png';

  group('resolveAvatarImageUrl', () {
    test('未注入运行时端点时不构造头像网络候选', () {
      expect(
        resolveAvatarImageUrlCandidates(avatarKey, avatarCdnBaseUrl: ''),
        isEmpty,
      );
    });

    test('只使用注入的 avatar endpoint，不生成 gateway 候选', () {
      expect(
        resolveAvatarImageUrlCandidates(
          avatarKey,
          gatewayBaseUrl: 'https://api.example.com',
          avatarCdnBaseUrl: 'https://avatar.example.com',
        ),
        <String>['https://avatar.example.com/$avatarKey'],
      );
    });

    test('显式版本与路径内唯一版本不一致时 fail-closed', () {
      expect(
        resolveAvatarImageUrl(
          'https://avatar.example.com/media/avatar/s/avatar-primary-0001/persona/persona-primary/v3/avatar.png',
          avatarCdnBaseUrl: 'https://avatar.example.com',
          avatarVersion: 18,
        ),
        isEmpty,
      );
    });

    test('拒绝无版本路径与 query 版本信封', () {
      expect(
        resolveAvatarImageUrl(
          'media/avatar/s/avatar-primary-0001/persona/persona-primary/avatar.png',
          avatarCdnBaseUrl: 'https://avatar.example.com',
        ),
        isEmpty,
      );
      expect(
        resolveAvatarImageUrl(
          '$avatarKey?v=1',
          avatarCdnBaseUrl: 'https://avatar.example.com',
        ),
        isEmpty,
      );
    });

    test('拒绝未注入的 absolute origin、明文 HTTP 和占位文本', () {
      expect(
        resolveAvatarImageUrl(
          'https://third-party.example.com/$avatarKey',
          avatarCdnBaseUrl: 'https://avatar.example.com',
        ),
        isEmpty,
      );
      expect(
        resolveAvatarImageUrl(
          'http://avatar.example.com/$avatarKey',
          avatarCdnBaseUrl: 'https://avatar.example.com',
        ),
        isEmpty,
      );
      expect(
        resolveAvatarImageUrl(
          '未设置头像',
          avatarCdnBaseUrl: 'https://avatar.example.com',
        ),
        isEmpty,
      );
    });

    test('data image 仍作为本地预览保留，不参与网络 URL 解析', () {
      const dataUri = 'data:image/png;base64,AA==';
      expect(resolveAvatarImageUrlCandidates(dataUri), <String>[dataUri]);
    });
  });
}
