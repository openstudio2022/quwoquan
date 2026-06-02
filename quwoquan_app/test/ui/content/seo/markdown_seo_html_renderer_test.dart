import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/ui/content/seo/markdown_seo_html_renderer.dart';

void main() {
  group('MarkdownSeoHtmlRenderer', () {
    const renderer = MarkdownSeoHtmlRenderer();

    test('renders safe HTML and SEO metadata from QWQ markdown', () {
      final doc = renderer.render(
        const MarkdownSeoRenderInput(
          postId: 'post_seo_1',
          title: '川西自驾笔记',
          summary: '从雪山到藏寨的三天路线。',
          authorName: '阿宁',
          createdAtIso: '2026-06-02T00:00:00.000Z',
          articleMarkdownDigest: 'sha256:abc',
          coverUrl: 'https://cdn.example.com/cover.jpg',
          articleMarkdown: '''
---
title: 川西自驾笔记
summary: 从雪山到藏寨的三天路线。
coverImage: asset://cover
---
# 川西自驾笔记

第一段正文，包含[来源](https://example.com/source)。

> 适合第一次去川西的朋友。

:::figure id="cover" layout="wrapRight" caption="清晨的藏寨"
asset://cover
:::

:::gallery ids="bridge,street" layout="masonry"
:::

:::callout type="tip" title="提示"
清晨出发更稳。
:::
''',
          articleAssetManifest: <String, Object?>{
            'assets': <Object?>[
              <String, Object?>{
                'assetId': 'cover',
                'cdnUrl': 'https://cdn.example.com/cover.jpg',
              },
              <String, Object?>{
                'assetId': 'bridge',
                'cdnUrl': 'https://cdn.example.com/bridge.jpg',
              },
              <String, Object?>{
                'assetId': 'street',
                'cdnUrl': 'https://cdn.example.com/street.jpg',
              },
            ],
          },
        ),
      );

      expect(doc.indexable, isTrue);
      expect(doc.canonicalUrl, AppPublicContentLinks.postWebUrl('post_seo_1'));
      expect(doc.html, contains('<h1>川西自驾笔记</h1>'));
      expect(doc.html, contains('<p>第一段正文，包含'));
      expect(doc.html, contains('<blockquote>适合第一次去川西的朋友。</blockquote>'));
      expect(doc.html, contains('<figure>'));
      expect(doc.html, contains('https://cdn.example.com/cover.jpg'));
      expect(doc.html, contains('class="qwq-gallery"'));
      expect(doc.html, contains('class="qwq-callout"'));
      expect(doc.openGraph['og:title'], '川西自驾笔记');
      expect(doc.openGraph['og:url'], doc.canonicalUrl);
      expect(doc.jsonLd['@type'], 'Article');
      expect(doc.jsonLd['identifier'], 'sha256:abc');
      expect(
        doc.referencedAssetUrls,
        contains('https://cdn.example.com/bridge.jpg'),
      );
    });

    test('escapes arbitrary HTML and unsafe asset URLs', () {
      final doc = renderer.render(
        const MarkdownSeoRenderInput(
          postId: 'post_escape',
          title: '安全测试',
          articleMarkdown: '''
# <script>alert(1)</script>

正文包含 <img src=x onerror=alert(1)>。

![bad](javascript:alert(1))
''',
        ),
      );

      expect(doc.html, isNot(contains('<script>')));
      expect(doc.html, contains('&lt;script&gt;alert(1)&lt;/script&gt;'));
      expect(doc.html, contains('&lt;img src=x onerror=alert(1)&gt;'));
      expect(doc.html, isNot(contains('javascript:alert')));
    });

    test('private content is not indexable and exposes no HTML body', () {
      final doc = renderer.render(
        const MarkdownSeoRenderInput(
          postId: 'private_seo',
          title: '仅自己可见',
          visibility: 'private',
          articleMarkdown: '# 私密正文\n\n不应公开。',
        ),
      );

      expect(doc.indexable, isFalse);
      expect(doc.html, isEmpty);
      expect(doc.openGraph, isEmpty);
      expect(doc.jsonLd, isEmpty);
    });

    test('circle visible content exposes controlled preview only', () {
      final doc = renderer.render(
        const MarkdownSeoRenderInput(
          postId: 'circle_preview',
          title: '圈内可见路线',
          summary: '公开页只展示摘要。',
          visibility: 'circle_visible',
          articleMarkdown: '# 圈内可见路线\n\n完整正文不应该进入公开 HTML。',
        ),
      );

      expect(doc.indexable, isFalse);
      expect(doc.html, contains('class="qwq-controlled-preview"'));
      expect(doc.html, contains('公开页只展示摘要。'));
      expect(doc.html, isNot(contains('完整正文不应该进入公开 HTML')));
      expect(doc.openGraph['og:url'], doc.canonicalUrl);
    });
  });
}
