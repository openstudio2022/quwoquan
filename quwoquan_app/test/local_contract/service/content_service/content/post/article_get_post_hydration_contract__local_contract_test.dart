import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/runtime/config/cloud_runtime_config.dart';
import 'package:quwoquan_app/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/runtime/transport/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/runtime/transport/http/cloud_http_client.dart';
import 'package:quwoquan_app/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_reader_remote.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_detail_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_detail_payload.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_post_view_data.dart';
import 'package:quwoquan_app/service/content_service/content/post/adapters/post_view_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';
import '../../../../../support/service/content_service/content/post/content_post_typed_doubles.dart';

ContentPostViewData _articlePost(String postId) => contentPostViewDataBuilder(
  postId: postId,
  contentType: 'article',
  title: '结构化长文',
  body: '用于验证详情 hydration 的摘要。',
  articleTemplate: 'journal',
  articleFontPreset: 'serif',
);

InMemoryContentPostDetailReader _articleReader(
  ContentPostViewData post, {
  String? markdown,
}) {
  final detail = contentPostDetailPayloadBuilder(
    post: post,
    articleMarkdown:
        markdown ??
        '# ${post.title}\n\n## 测试章节\n\n${post.body}\n\n用于验证 typed detail hydration。',
  );
  return InMemoryContentPostDetailReader(
    InMemoryContentPostStore(
      posts: <ContentPostViewData>[post],
      details: <String, ContentPostDetailPayload>{post.id: detail},
    ),
  );
}

void main() {
  setUp(() {
    CloudRuntimeConfig.hydrateFromNativeRuntimePackage(const <String, String>{
      'MEDIA_AVATAR_CDN_BASE_URL': 'https://media.example.com/avatar',
      'MEDIA_IMAGE_CDN_BASE_URL': 'https://media.example.com/image',
      'MEDIA_VIDEO_CDN_BASE_URL': 'https://media.example.com/video',
    }, enforceNativeLaunchBinding: false);
  });

  tearDown(CloudRuntimeConfig.clearNativeRuntimePackageForTest);

  group('Article getPost hydration contract', () {
    test('Mock getPost 暴露 canonical ContentPostDetailPayload 文章扩展字段', () async {
      final post = _articlePost('web-dev');
      final reader = _articleReader(post);
      final detail = await reader.getPost(postId: post.id);
      expect(detail.detailWire.articleTemplate, isNotNull);
      expect(detail.detailWire.articleMarkdown, isNotNull);
      expect(detail.detailWire.articleMarkdown, contains('#'));
      expect(detail.detailWire.articleAssetManifest, isNotNull);
    });

    test('Mock getPost 与 Remote getPost 投射结果保持一致', () async {
      final dtoFixture = _articlePost('article-remote-roundtrip');
      final postId = dtoFixture.id;
      final reader = _articleReader(dtoFixture);
      final mockDetail = await reader.getPost(postId: postId);
      final rawFixture = mockDetail.detailWire.toWire();
      final remoteRepo = RemoteContentPostReaderAdapter(
        client: buildGeneratedCloudOperationClient(
          httpClient: CloudHttpClient(
            client: MockClient((request) async {
              return http.Response(
                jsonEncode(rawFixture),
                200,
                headers: const <String, String>{
                  'content-type': 'application/json',
                },
              );
            }),
          ),
          clientContextProvider: const _ArticleTestClientContext(),
          telemetrySink: const _NoopCloudOperationTelemetrySink(),
          environment: CloudRuntimeEnvironment(
            environment: CloudEnvironment.gamma,
            gatewayBaseUri: Uri.parse('https://example.com'),
          ),
        ),
        invocationContext: (clientPageId) => CloudOperationInvocationContext(
          surfaceId: AppUiSurfaces.workBrowser.id,
          routeId: AppUiSurfaces.workBrowser.routeId,
          clientPageId: clientPageId,
          actor: const CloudOperationActorContext(),
        ),
      );
      final remoteDetail = await remoteRepo.getPost(postId: postId);
      final mockView = projectArticleDetailViewFromPayload(
        mockDetail,
        fallbackArticleId: postId,
      );
      final remoteView = projectArticleDetailViewFromPayload(
        remoteDetail,
        fallbackArticleId: postId,
      );

      expect(remoteView.documentSource, ArticleDetailDocumentSource.markdown);
      expect(remoteView.document.title, equals(mockView.document.title));
      expect(remoteView.document.body, equals(mockView.document.body));
      expect(remoteView.template, equals(mockView.template));
      expect(remoteView.fontPreset, equals(mockView.fontPreset));
      expect(remoteView.pages.length, equals(mockView.pages.length));
      expect(
        remoteView.contentBlocks.map((block) => block.type).toList(),
        equals(mockView.contentBlocks.map((block) => block.type).toList()),
      );
    });

    test('Mock getPost 覆盖上文下三图文章详情', () async {
      final post = _articlePost('article-top-three-images');
      final reader = _articleReader(
        post,
        markdown: '''
# 上文下三图

这里是图片之前的正文。

![图片一](https://media.example.com/image/one.jpg)

![图片二](https://media.example.com/image/two.jpg)

![图片三](https://media.example.com/image/three.jpg)
''',
      );
      final detail = await reader.getPost(postId: post.id);
      final view = projectArticleDetailViewFromPayload(
        detail,
        fallbackArticleId: post.id,
      );
      final imageNodes = view.document.nodes
          .where((node) => node.isFigure)
          .toList(growable: false);

      expect(imageNodes, hasLength(3));
      expect(
        imageNodes.every((node) => node.imageUrl.trim().isNotEmpty),
        isTrue,
      );
      expect(
        view.contentBlocks.where((block) => block.type == 'image'),
        isNotEmpty,
      );
    });

    test('summary snapshot 在 hydration 后切到 canonical articleMarkdown', () {
      const summaryRaw = <String, dynamic>{
        'postId': 'article_hydration_switch',
        'contentType': 'article',
        'contentIdentity': 'work',
        'authorId': 'writer_1',
        'authorDisplayName': '水合作者',
        'authorAvatarUrl': 'https://example.com/avatar.jpg',
        'title': '分发标题',
        'body': '分发摘要正文',
        'coverUrl': 'https://example.com/cover.jpg',
      };
      const hydratedRaw = <String, dynamic>{
        'postId': 'article_hydration_switch',
        'contentType': 'article',
        'contentIdentity': 'work',
        'authorId': 'writer_1',
        'authorDisplayName': '水合作者',
        'authorAvatarUrl': 'https://example.com/avatar.jpg',
        'title': '分发标题',
        'body': '分发摘要正文',
        'coverUrl': 'https://example.com/cover.jpg',
        'articleMarkdown':
            '---\ntitle: 水合后标题\n---\n\n# 水合后标题\n\n## 水合章节\n\n水合后正文第一段。\n\n水合后正文第二段。\n',
        'markdownDialect': 'qwq-rich-md',
        'articleAssetManifest': <String, dynamic>{'assets': []},
        'articleRenderProfile': <String, dynamic>{'template': 'journal'},
      };

      final before = projectArticleDetailView(
        summaryRaw,
        fallbackArticleId: 'article_hydration_switch',
      );
      final after = projectArticleDetailView(
        hydratedRaw,
        fallbackArticleId: 'article_hydration_switch',
      );

      expect(before.documentSource, ArticleDetailDocumentSource.empty);
      expect(before.contentHtml, isEmpty);
      expect(before.pages.single.body, isEmpty);
      expect(before.pages.single.title, equals('分发标题'));
      expect(after.documentSource, ArticleDetailDocumentSource.markdown);
      expect(after.document.title, equals('水合后标题'));
      expect(after.document.body, contains('水合后正文第一段'));
    });
  });
}

final class _ArticleTestClientContext implements CloudClientContextProvider {
  const _ArticleTestClientContext();

  @override
  CloudClientContextSnapshot snapshot() {
    return const CloudClientContextSnapshot(
      sessionId: 'article-hydration-session',
      deviceActorId: 'article-hydration-device',
      platform: 'test',
      appVersion: 'test',
      locale: 'zh-CN',
    );
  }
}

final class _NoopCloudOperationTelemetrySink
    implements CloudOperationTelemetrySink {
  const _NoopCloudOperationTelemetrySink();

  @override
  void record(CloudOperationTelemetryEvent event) {}
}
