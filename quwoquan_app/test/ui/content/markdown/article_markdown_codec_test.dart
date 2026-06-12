import 'package:flutter_test/flutter_test.dart';
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

清晨从@[灵隐寺](entity:homepage/homepage_sight_west_lake)出发，再去@[河坊街](entity:homepage/homepage_restaurant_night_market)。
''');

      final paragraph = document.nodes
          .where((node) => node.text.contains('灵隐寺'))
          .single;
      expect(paragraph.text, contains('清晨从灵隐寺出发'));
      expect(paragraph.text, isNot(contains('entity:homepage')));
      expect(paragraph.spans, hasLength(2));
      expect(paragraph.spans.first.kind, 'entity');
      expect(paragraph.spans.first.targetType, 'homepage');
      expect(paragraph.spans.first.targetId, 'homepage_sight_west_lake');
      expect(paragraph.spans.first.displayText, '灵隐寺');

      final serialized = ArticleMarkdownCodec.serializeDocument(document);
      expect(
        serialized,
        contains('@[灵隐寺](entity:homepage/homepage_sight_west_lake)'),
      );
      expect(
        serialized,
        contains('@[河坊街](entity:homepage/homepage_restaurant_night_market)'),
      );
    });
  });
}
