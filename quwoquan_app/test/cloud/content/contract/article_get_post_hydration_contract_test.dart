import 'dart:convert';

import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:quwoquan_app/cloud/runtime/http/cloud_http_client.dart';
import 'package:quwoquan_app/cloud/services/content/content_repository.dart';
import 'package:quwoquan_app/cloud/services/content/feed_item_discovery_wire_map.dart';
import 'package:quwoquan_app/cloud/services/content/mock/content_mock_data.dart';
import 'package:quwoquan_app/ui/content/article_detail_view.dart';
import 'package:quwoquan_app/ui/content/post_view_projection.dart';

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
          dtoFixture.toDiscoveryWireMap()['postId']?.toString() ??
          'article_contract_post';
      final mockRepo = MockContentRepository();
      final mockDetail = await mockRepo.getPost(postId: postId);
      final rawFixture = mockDetail.mergedArticleWireMap;
      final remoteRepo = RemoteContentRepository(
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
        baseUrl: 'https://example.com',
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
      expect(remoteView.title, equals(mockView.title));
      expect(remoteView.description, equals(mockView.description));
      expect(remoteView.template, equals(mockView.template));
      expect(remoteView.fontPreset, equals(mockView.fontPreset));
      expect(remoteView.pages.length, equals(mockView.pages.length));
      expect(
        remoteView.contentBlocks.map((block) => block.type).toList(),
        equals(mockView.contentBlocks.map((block) => block.type).toList()),
      );
    });

    test('summary snapshot 在 hydration 后切到 canonical articleMarkdown', () {
      const summaryRaw = <String, dynamic>{
        'postId': 'article_hydration_switch',
        'contentType': 'article',
        'authorId': 'writer_1',
        'displayName': '水合作者',
        'authorAvatarUrl': 'https://example.com/avatar.jpg',
        'title': '分发标题',
        'body': '分发摘要正文',
        'coverUrl': 'https://example.com/cover.jpg',
      };
      const hydratedRaw = <String, dynamic>{
        'postId': 'article_hydration_switch',
        'contentType': 'article',
        'authorId': 'writer_1',
        'displayName': '水合作者',
        'authorAvatarUrl': 'https://example.com/avatar.jpg',
        'title': '分发标题',
        'body': '分发摘要正文',
        'coverUrl': 'https://example.com/cover.jpg',
        'articleMarkdown':
            '---\ntitle: 水合后标题\n---\n\n# 水合后标题\n\n## 水合章节\n\n水合后正文第一段。\n\n水合后正文第二段。\n',
        'articleMarkdownVersion': 'qwq-rich-md/1',
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

      expect(before.documentSource, ArticleDetailDocumentSource.body);
      expect(before.description, equals('分发摘要正文'));
      expect(after.documentSource, ArticleDetailDocumentSource.markdown);
      expect(after.title, equals('水合后标题'));
      expect(after.description, contains('水合后正文第一段'));
    });
  });
}
