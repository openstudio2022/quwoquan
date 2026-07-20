import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/cloud/runtime/config/cloud_runtime_environment.dart';
import 'package:quwoquan_app/cloud/runtime/context/cloud_client_context.dart';
import 'package:quwoquan_app/cloud/runtime/executor/cloud_operation_client_factory.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/runtime/observability/cloud_operation_telemetry.dart';
import 'package:quwoquan_app/cloud/services/content/remote/post_reader_remote.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import '../../../../support/cloud_services/content/content_mock_data.dart';
import 'package:quwoquan_app/ui/content/models/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/services/post_view_projection.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';
import '../../../../support/cloud_services/content/mock_content_repository.dart';

void main() {
  group('Article getPost hydration contract', () {
    test('Mock getPost 暴露 ContentPostDetailWireDto 文章扩展字段', () async {
      final mockRepo = MockContentRepository();
      final detail = await mockRepo.getPost(postId: 'web-dev');
      expect(detail.detailWire.articleTemplate, isNotNull);
      expect(detail.detailWire.articleMarkdown, isNotNull);
      expect(detail.detailWire.articleMarkdown, contains('#'));
      expect(detail.detailWire.articleAssetManifest, isNotNull);
    });

    test('Mock getPost 与 Remote getPost 投射结果保持一致', () async {
      final dtoFixture = ContentMockData.discoveryArticleData.firstWhere((
        item,
      ) {
        final digest = item.articleMarkdownDigest;
        return digest != null && digest.isNotEmpty;
      });
      final postId =
          dtoFixture.toDiscoveryWireMap()['id']?.toString() ??
          'article_contract_post';
      final mockRepo = MockContentRepository();
      final mockDetail = await mockRepo.getPost(postId: postId);
      final rawFixture = _getPostResponseFromAppProjection(
        mockDetail.mergedArticleWireMap,
      );
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
      final mockRepo = MockContentRepository();
      final detail = await mockRepo.getPost(
        postId: 'alpha_article_top_three_images',
      );
      final view = projectArticleDetailViewFromPayload(
        detail,
        fallbackArticleId: 'alpha_article_top_three_images',
      );
      final imageNodes = view.document.nodes
          .where((node) => node.isFigure)
          .toList(growable: false);

      expect(imageNodes, hasLength(3));
      expect(
        imageNodes.every(
          (node) =>
              node.imageUrl.startsWith('http://') ||
              node.imageUrl.startsWith('https://'),
        ),
        isTrue,
      );
      expect(
        view.contentBlocks.where((block) => block.type == 'image'),
        isNotEmpty,
      );
    });

    test('summary snapshot 在 hydration 后切到 canonical articleMarkdown', () {
      const summaryRaw = <String, dynamic>{
        'id': 'article_hydration_switch',
        'type': 'article',
        'authorId': 'writer_1',
        'displayName': '水合作者',
        'avatarUrl': 'https://example.com/avatar.jpg',
        'title': '分发标题',
        'body': '分发摘要正文',
        'coverUrl': 'https://example.com/cover.jpg',
      };
      const hydratedRaw = <String, dynamic>{
        'id': 'article_hydration_switch',
        'type': 'article',
        'authorId': 'writer_1',
        'displayName': '水合作者',
        'avatarUrl': 'https://example.com/avatar.jpg',
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

Map<String, dynamic> _getPostResponseFromAppProjection(
  Map<String, dynamic> projection,
) {
  final response = Map<String, dynamic>.from(projection);
  response
    ..remove('id')
    ..remove('type')
    ..remove('identity')
    ..remove('displayName')
    ..remove('avatarUrl')
    ..addAll(<String, dynamic>{
      'postId': projection['id'],
      'contentType': projection['type'],
      'contentIdentity': projection['identity'],
      'authorDisplayName': projection['displayName'],
      'authorAvatarUrl': projection['avatarUrl'],
    });
  return response;
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
