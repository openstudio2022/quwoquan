import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/cloud/runtime/generated/content/content_dtos.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/ui/content/models/content_surface_view_mapper.dart';
import 'package:quwoquan_app/ui/content/share/content_share_template.dart';

void main() {
  group('ContentShareTemplate public links', () {
    test(
      'public content keeps app deep link but defaults to HTTPS landing URL',
      () {
        final template = ContentShareTemplateBuilder.build(
          surfaceView: ContentSurfaceViewMapper.fromDto(
            MicroPostDto(
              id: 'moment_public_link',
              type: 'micro',
              identity: 'moment',
              assistantUsePolicy: 'inherit',
              authorId: 'user_public_link',
              displayName: '阿宁',
              avatarUrl: '',
              authorRoleLabel: '',
              authorIdentityTags: const <String>[],
              authorVerified: false,
              body: '公开分享链路应该指向 Web 公共页',
              imageUrls: const <String>[],
              likeCount: 0,
              commentCount: 0,
              shareCount: 0,
              createdAt: DateTime(2026, 6, 2),
            ),
          ),
          enableIdentityTemplate: true,
          visibility: 'public',
        );

        // landingUrl 以规范公网 URL 为基础，并追加单次分享归因参数。
        expect(
          template.landingUrl,
          startsWith(AppPublicContentLinks.postWebUrl('moment_public_link')),
        );
        expect(template.landingUrl, startsWith('https://'));
        expect(template.landingUrl, contains('share_id='));
        expect(template.landingUrl, contains('utm_source='));
        expect(template.shareId, isNotEmpty);
        expect(template.deeplink, 'quwoquan://content/post/moment_public_link');
        expect(template.deeplink, isNot(template.landingUrl));
      },
    );

    test(
      'retired circle visibility is rejected instead of generating a scoped link',
      () {
        expect(
          () => ContentShareTemplateBuilder.build(
            surfaceView: ContentSurfaceViewMapper.fromDto(
              ArticlePostDto(
                id: 'work_circle_link',
                type: 'article',
                identity: 'work',
                assistantUsePolicy: 'inherit',
                authorId: 'user_circle_link',
                displayName: '洛白',
                avatarUrl: '',
                authorRoleLabel: '',
                authorIdentityTags: const <String>[],
                authorVerified: false,
                title: '已退役可见性',
                body: '该值必须失败关闭。',
                summary: '该值必须失败关闭',
                coverUrl: '',
                articleTemplate: 'gentle',
                articleFontPreset: 'clean',
                likeCount: 0,
                commentCount: 0,
                shareCount: 0,
                createdAt: DateTime(2026, 6, 2),
              ),
            ),
            enableIdentityTemplate: true,
            visibility: 'circle-visible',
          ),
          throwsArgumentError,
        );
      },
    );

    test('private content does not expose public landing URL', () {
      final template = ContentShareTemplateBuilder.build(
        surfaceView: ContentSurfaceViewMapper.fromDto(
          ArticlePostDto(
            id: 'private_link',
            type: 'article',
            identity: 'work',
            assistantUsePolicy: 'inherit',
            authorId: 'user_private',
            displayName: '周周',
            avatarUrl: '',
            authorRoleLabel: '',
            authorIdentityTags: const <String>[],
            authorVerified: false,
            title: '私密内容',
            body: '仅自己可见',
            summary: '仅自己可见',
            coverUrl: '',
            articleTemplate: 'gentle',
            articleFontPreset: 'clean',
            likeCount: 0,
            commentCount: 0,
            shareCount: 0,
            createdAt: DateTime(2026, 6, 2),
          ),
        ),
        enableIdentityTemplate: true,
        visibility: 'private',
      );

      expect(template.isBlocked, isTrue);
      expect(template.landingUrl, isEmpty);
      expect(template.deeplink, isEmpty);
    });
  });
}
