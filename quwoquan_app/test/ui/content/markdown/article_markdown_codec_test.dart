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
  });
}
