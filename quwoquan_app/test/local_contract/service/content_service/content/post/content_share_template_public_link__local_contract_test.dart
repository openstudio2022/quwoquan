// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/entity-link-templates-metadata/spec.md#gwt-001
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-001.t1
// spec_ref: specs/feature-tree/runtime/runtime-client-foundation/public-content-web-entry/spec.md#gwt-001.t2
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/runtime/transport/links/app_public_content_links.dart';
import 'package:quwoquan_app/runtime/di/content_surface_view_mapper.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/content_share_template.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

ContentPostViewData _post({
  required String id,
  required String contentType,
  required String identity,
  required String authorId,
  required String displayName,
  String? title,
  required String body,
  String? summary,
}) => ContentPostViewData.fromWire(
  ContentPostProjection(
    postId: id,
    contentType: contentType,
    contentIdentity: identity,
    assistantUsePolicy: AssistantUsePolicy.inherit,
    authorId: authorId,
    authorDisplayName: displayName,
    authorAvatarUrl: '',
    authorRoleLabel: '',
    authorIdentityTags: const <String>[],
    authorVerified: false,
    title: title,
    body: body,
    summary: summary,
    coverUrl: '',
    articleTemplate: contentType == 'article' ? 'gentle' : null,
    articleFontPreset: contentType == 'article' ? 'clean' : null,
    likeCount: 0,
    commentCount: 0,
    shareCount: 0,
    createdAt: DateTime(2026, 6, 2),
  ),
);

void main() {
  setUp(() {
    CloudRuntimeConfig.hydrateFromNativeRuntimePackageForTest(
      const <String, String>{
        'PUBLIC_WEB_BASE_URL': 'https://public.example.test',
      },
    );
  });
  tearDown(CloudRuntimeConfig.clearNativeRuntimePackageForTest);

  group('ContentShareTemplate public links', () {
    test(
      'public content keeps app deep link but defaults to HTTPS landing URL',
      () {
        final template = ContentShareTemplateBuilder.build(
          surfaceView: ContentSurfaceViewMapper.fromDto(
            _post(
              id: 'moment_public_link',
              contentType: 'micro',
              identity: 'moment',
              authorId: 'user_public_link',
              displayName: '阿宁',
              body: '公开分享链路应该指向 Web 公共页',
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
              _post(
                id: 'work_circle_link',
                contentType: 'article',
                identity: 'work',
                authorId: 'user_circle_link',
                displayName: '洛白',
                title: '已退役可见性',
                body: '该值必须失败关闭。',
                summary: '该值必须失败关闭',
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
          _post(
            id: 'private_link',
            contentType: 'article',
            identity: 'work',
            authorId: 'user_private',
            displayName: '周周',
            title: '私密内容',
            body: '仅自己可见',
            summary: '仅自己可见',
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
