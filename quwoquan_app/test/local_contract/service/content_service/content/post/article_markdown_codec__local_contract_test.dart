import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';

const MediaAssetManifestResolver _assetManifestResolver =
    MediaAssetManifestResolver(
      resolveReference: _resolveMediaReference,
      imageCdnBaseUrl: 'https://image.example.test',
    );

void main() {
  group('ArticleMarkdownCodec', () {
    test('resolves cover and figure from canonical public slice', () {
      final document = ArticleMarkdownCodec.parseDocument(
        '''
---
title: 媒体变体正文
coverImage: asset://cover
---
# 媒体变体正文

![封面](asset://cover)
''',
        assetManifest: const <String, dynamic>{
          'assets': <Object?>[
            <String, Object?>{
              'assetId': 'cover',
              'publicSliceKey':
                  'media/image/s/seo/cover_variants/v1/cover-display.webp',
            },
          ],
        },
        assetManifestResolver: _assetManifestResolver,
      );

      expect(document.coverImageUrl, contains('cover-display.webp'));
      final figure = document.nodes.where((node) => node.isFigure).single;
      expect(figure.assetId, 'cover');
      expect(figure.imageUrl, contains('cover-display.webp'));
    });

    test('parses entity labels into structured inline spans', () {
      final document = ArticleMarkdownCodec.parseDocument('''
---
title: 杭州一日游
---
# 杭州一日游

清晨从@[灵隐寺](entity:sight:west_lake)出发，再去@[河坊街](entity:restaurant:night_market)。
''');

      final paragraph = document.nodes
          .where((node) => node.text.contains('灵隐寺'))
          .single;
      expect(paragraph.text, contains('清晨从灵隐寺出发'));
      expect(paragraph.text, isNot(contains('entity:homepage')));
      expect(paragraph.spans, hasLength(2));
      expect(paragraph.spans.first.kind, 'entity');
      expect(paragraph.spans.first.targetType, 'entity');
      expect(paragraph.spans.first.targetId, 'entity:sight:west_lake');
      expect(paragraph.spans.first.displayText, '灵隐寺');

      final serialized = ArticleMarkdownCodec.serializeDocument(document);
      expect(serialized, contains('@[灵隐寺](entity:sight:west_lake)'));
      expect(serialized, contains('@[河坊街](entity:restaurant:night_market)'));
    });

    test(
      'parses tag mentions into clickable spans and keeps entity behavior',
      () {
        final document = ArticleMarkdownCodec.parseDocument('''
---
title: 城市漫步指南
---
# 城市漫步指南

午后沿着@[城市漫步](tag:topic:city_walk)的路线，顺便去@[灵隐寺](entity:sight:west_lake)。
''');

        final paragraph = document.nodes
            .where((node) => node.text.contains('午后沿着'))
            .single;
        expect(paragraph.text, contains('午后沿着城市漫步的路线'));
        expect(paragraph.text, isNot(contains('tag:')));
        expect(paragraph.text, isNot(contains('entity:')));
        expect(paragraph.spans, hasLength(2));

        final tagSpan = paragraph.spans.firstWhere(
          (span) => span.kind == 'tag',
        );
        expect(tagSpan.isTag, isTrue);
        expect(tagSpan.isEntity, isFalse);
        expect(tagSpan.isInlineMention, isTrue);
        expect(tagSpan.targetType, 'tag');
        expect(tagSpan.targetId, 'tag:topic:city_walk');
        expect(tagSpan.displayText, '城市漫步');

        final entitySpan = paragraph.spans.firstWhere(
          (span) => span.kind == 'entity',
        );
        expect(entitySpan.isEntity, isTrue);
        expect(entitySpan.isTag, isFalse);
        expect(entitySpan.targetType, 'entity');
        expect(entitySpan.targetId, 'entity:sight:west_lake');
        expect(entitySpan.displayText, '灵隐寺');

        final serialized = ArticleMarkdownCodec.serializeDocument(document);
        expect(serialized, contains('@[城市漫步](tag:topic:city_walk)'));
        expect(serialized, contains('@[灵隐寺](entity:sight:west_lake)'));

        // round-trip 保形：再次解析后 span 结构与目标一致。
        final reparsed = ArticleMarkdownCodec.parseDocument(serialized);
        final reparsedParagraph = reparsed.nodes
            .where((node) => node.text.contains('午后沿着'))
            .single;
        expect(
          reparsedParagraph.spans.map((span) => span.targetId).toList(),
          <String>['tag:topic:city_walk', 'entity:sight:west_lake'],
        );
        expect(
          reparsedParagraph.spans.map((span) => span.kind).toList(),
          <String>['tag', 'entity'],
        );
      },
    );

    test(
      'front matter preserves summary tag refs entity refs and assistant policy',
      () {
        final markdown = ArticleMarkdownCodec.serializeDocument(
          ArticleDocumentData(
            nodes: <ArticleDocumentNode>[
              ArticleDocumentNode(
                id: 'document_title',
                type: ArticleDocumentNodeType.documentTitle,
                text: '西湖一日游',
              ),
              ArticleDocumentNode(
                id: 'p1',
                type: ArticleDocumentNodeType.paragraph,
                text: '正文内容',
              ),
            ],
          ),
          summary: '用户确认摘要',
          tagRefs: const <String>['Topic/旅行/城市漫步'],
          entityRefs: const <String>['entity:sight:west_lake'],
          visibility: 'public',
          assistantUsePolicy: 'allow_summary',
        );

        expect(markdown, contains('summary: "用户确认摘要"'));
        expect(markdown, contains('tag_refs:'));
        expect(markdown, contains('- "Topic/旅行/城市漫步"'));
        expect(markdown, contains('entity_refs:'));
        expect(markdown, contains('- "entity:sight:west_lake"'));
        expect(markdown, contains('assistantUsePolicy: allow_summary'));

        final parsed = ArticleMarkdownCodec.parseDocument(markdown);
        expect(parsed.title, '西湖一日游');
        expect(parsed.body, contains('正文内容'));
      },
    );
  });
}

String _resolveMediaReference(
  String raw, {
  String? gatewayBaseUrl,
  String? imageCdnBaseUrl,
  String? videoCdnBaseUrl,
}) => resolveContentMediaUrl(
  raw,
  gatewayBaseUrl: gatewayBaseUrl,
  imageCdnBaseUrl: imageCdnBaseUrl,
  videoCdnBaseUrl: videoCdnBaseUrl,
);
