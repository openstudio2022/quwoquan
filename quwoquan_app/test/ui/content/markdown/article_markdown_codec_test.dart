import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/markdown/article_markdown_codec.dart';

void main() {
  group('ArticleMarkdownCodec', () {
    test('uses cover variant for cover and display variant for body figures', () {
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
              'variants': <String, Object?>{
                'cover': <String, Object?>{
                  'cdnUrl': 'https://cdn.example.com/cover-card.webp',
                },
                'display': <String, Object?>{
                  'cdnUrl': 'https://cdn.example.com/cover-display.webp',
                },
                'original': <String, Object?>{
                  'objectKey':
                      'media/objects/sha256/aa/aa/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa.jpg',
                  'requiresAccess': true,
                },
              },
            },
          ],
        },
      );

      expect(document.coverImageUrl, 'https://cdn.example.com/cover-card.webp');
      final figure = document.nodes.where((node) => node.isFigure).single;
      expect(figure.assetId, 'cover');
      expect(figure.imageUrl, 'https://cdn.example.com/cover-display.webp');
      expect(figure.imageUrl, isNot(contains('original')));
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
      expect(
        serialized,
        contains('@[灵隐寺](entity:sight:west_lake)'),
      );
      expect(
        serialized,
        contains('@[河坊街](entity:restaurant:night_market)'),
      );
    });

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
