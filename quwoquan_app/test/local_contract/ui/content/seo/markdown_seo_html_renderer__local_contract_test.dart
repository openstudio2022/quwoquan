import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/media/content_media_url.dart';
import 'package:quwoquan_app/core/links/app_public_content_links.dart';
import 'package:quwoquan_app/ui/content/seo/markdown_seo_html_renderer.dart';

void main() {
  group('MarkdownSeoHtmlRenderer', () {
    const renderer = MarkdownSeoHtmlRenderer();
    String resolvedMedia(String raw) => resolveContentMediaUrl(raw);

    test('renders safe HTML and SEO metadata from QWQ markdown', () {
      const article = '''
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
''';
      final articleDigest = _sha256Digest(article);
      final doc = renderer.render(
        MarkdownSeoRenderInput(
          postId: 'post_seo_1',
          title: '川西自驾笔记',
          summary: '从雪山到藏寨的三天路线。',
          authorName: '阿宁',
          createdAtIso: '2026-06-02T00:00:00.000Z',
          articleMarkdownDigest: articleDigest,
          coverUrl: 'https://cdn.example.com/ignored-cover.jpg',
          articleMarkdown: article,
          articleAssetManifest: <String, Object?>{
            'assets': <Object?>[
              <String, Object?>{
                'assetId': 'cover',
                'publicSliceKey': 'media/image/s/seo/post_seo_1/v1/cover.jpg',
              },
              <String, Object?>{
                'assetId': 'bridge',
                'publicSliceKey': 'media/image/s/seo/post_seo_1/v1/bridge.jpg',
              },
              <String, Object?>{
                'assetId': 'street',
                'publicSliceKey': 'media/image/s/seo/post_seo_1/v1/street.jpg',
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
      expect(
        doc.html,
        contains(resolvedMedia('media/image/s/seo/post_seo_1/v1/cover.jpg')),
      );
      expect(doc.html, contains('data-asset-id="cover"'));
      expect(doc.html, contains('class="qwq-gallery"'));
      expect(doc.html, contains('class="qwq-callout"'));
      expect(doc.openGraph['og:title'], '川西自驾笔记');
      expect(doc.openGraph['og:url'], doc.canonicalUrl);
      expect(doc.jsonLd['@type'], 'Article');
      expect(doc.jsonLd['identifier'], articleDigest);
      expect(
        doc.referencedAssetUrls,
        contains(resolvedMedia('media/image/s/seo/post_seo_1/v1/bridge.jpg')),
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

    test('resolves public slice asset manifest through shared resolver', () {
      final doc = renderer.render(
        const MarkdownSeoRenderInput(
          postId: 'post_object_key',
          title: '媒体发布测试',
          articleMarkdown: '''
# 媒体发布测试

![封面](asset://cover)
''',
          articleAssetManifest: <String, Object?>{
            'assets': <Object?>[
              <String, Object?>{
                'assetId': 'cover',
                'publicSliceKey':
                    'media/image/s/seo/post-object-key/v1/cover.jpg',
              },
            ],
          },
        ),
      );

      expect(
        doc.html,
        contains(
          resolvedMedia('media/image/s/seo/post-object-key/v1/cover.jpg'),
        ),
      );
      expect(doc.html, contains('data-asset-id="cover"'));
    });

    test('renders canonical public slice and keeps asset id for lookup', () {
      final doc = renderer.render(
        const MarkdownSeoRenderInput(
          postId: 'post_variants',
          title: '媒体变体测试',
          articleMarkdown: '''
# 媒体变体测试

![封面](asset://cover)
''',
          articleAssetManifest: <String, Object?>{
            'assets': <Object?>[
              <String, Object?>{
                'assetId': 'cover',
                'publicSliceKey':
                    'media/image/s/seo/post_variants/v1/cover-display.webp',
              },
            ],
          },
        ),
      );

      expect(
        doc.html,
        contains(
          'src="${resolvedMedia("media/image/s/seo/post_variants/v1/cover-display.webp")}"',
        ),
      );
      expect(doc.html, contains('data-asset-id="cover"'));
      expect(doc.html, isNot(contains('cover-full.webp')));
      expect(
        doc.referencedAssetUrls,
        contains(
          resolvedMedia(
            'media/image/s/seo/post_variants/v1/cover-display.webp',
          ),
        ),
      );
    });

    test('renders materialized pilot markdown with asset manifest closure', () {
      final root = Directory.systemTemp.createTempSync(
        'markdown_seo_html_renderer_pilot_',
      );
      addTearDown(() => root.deleteSync(recursive: true));
      final postDir = Directory(
        '${root.path}/posts/article/环线攻略/稻城亚丁·亚丁三神山徒步体验/1',
      )..createSync(recursive: true);
      final article = '''
---
title: 稻城亚丁·亚丁三神山徒步体验
summary: 高原徒步与雪山同框。
coverImage: asset://cover
---
# 稻城亚丁·亚丁三神山徒步体验

正文段落。

![封面](asset://cover)
''';
      File(
        '${postDir.path}/article.md',
      ).writeAsStringSync(article, encoding: utf8);
      File('${postDir.path}/assets/cover.jpg')
        ..createSync(recursive: true)
        ..writeAsStringSync('fake-cover', encoding: utf8);
      final renderManifest = <String, Object?>{
        'assets': <Object?>[
          <String, Object?>{
            'assetId': 'cover',
            'fileName': 'cover.jpg',
            'sourceAssetRef': 'source/cover.jpg',
            'publicSliceKey': 'media/image/s/runtime-preview/v1/cover.jpg',
          },
        ],
      };
      final articleDigest = _sha256Digest(article);
      File('${postDir.path}/manifest.json').writeAsStringSync(
        jsonEncode(<String, Object?>{
          'topicId': 'topic_pilot_daocheng',
          'publishTitle': '稻城亚丁·亚丁三神山徒步体验',
          'articleMarkdownDigest': articleDigest,
          'articleAssetManifest': renderManifest,
        }),
        encoding: utf8,
      );

      final doc = renderer.render(
        MarkdownSeoRenderInput(
          postId: 'topic_pilot_daocheng',
          title: '稻城亚丁·亚丁三神山徒步体验',
          articleMarkdownDigest: articleDigest,
          articleMarkdown: article,
          articleAssetManifest: renderManifest,
        ),
      );

      expect(doc.indexable, isTrue);
      expect(doc.html, contains('data-asset-id="cover"'));
      expect(
        doc.html,
        contains(resolvedMedia('media/image/s/runtime-preview/v1/cover.jpg')),
      );
      expect(doc.referencedAssetUrls, isNotEmpty);
      expect(doc.jsonLd['identifier'], articleDigest);
    });

    test('renders object-first layout sample with sourceAssetRef closure', () {
      // T4：新同构目录（entities/posts + 编号阶段 + 来源单元）下，
      // article.md + articleAssetManifest 渲染出带 data-asset-id 的图片，
      // 且每个 asset 的 sourceAssetRef 可相对 batch 根回查到来源单元里的原图。
      final batchDir = Directory.systemTemp.createTempSync(
        'markdown_seo_html_renderer_layout_',
      );
      addTearDown(() => batchDir.deleteSync(recursive: true));
      final postDir = Directory(
        '${batchDir.path}/posts/article/环线攻略/在海螺沟看冰川泡温泉/1',
      )..createSync(recursive: true);
      final article = '''
---
title: 在海螺沟看冰川泡温泉
summary: 冰川与温泉同框。
coverImage: asset://海螺沟_cover_01
---
# 在海螺沟看冰川泡温泉

正文。

![封面](asset://海螺沟_cover_01)
![细节](asset://海螺沟_detail_02)
''';
      File(
        '${postDir.path}/article.md',
      ).writeAsStringSync(article, encoding: utf8);
      final declaredAssets = <Map<String, Object?>>[
        <String, Object?>{
          'assetId': '海螺沟_cover_01',
          'fileName': '海螺沟_cover_01.jpg',
          'sourceAssetRef': 'source/海螺沟_cover_01.jpg',
          'publicSliceKey':
              'media/image/s/runtime-preview/topic-layout-sample/v1/cover-01.jpg',
        },
        <String, Object?>{
          'assetId': '海螺沟_detail_02',
          'fileName': '海螺沟_detail_02.jpg',
          'sourceAssetRef': 'source/海螺沟_detail_02.jpg',
          'publicSliceKey':
              'media/image/s/runtime-preview/topic-layout-sample/v1/detail-02.jpg',
        },
      ];
      for (final asset in declaredAssets) {
        final sourceAssetRef = asset['sourceAssetRef'] as String;
        final sourceFile = File('${batchDir.path}/$sourceAssetRef');
        sourceFile.parent.createSync(recursive: true);
        sourceFile.writeAsStringSync('fake-source-image', encoding: utf8);
      }
      final renderManifest = <String, Object?>{'assets': declaredAssets};
      final articleDigest = _sha256Digest(article);
      File('${postDir.path}/manifest.json').writeAsStringSync(
        jsonEncode(<String, Object?>{
          'topicId': 'topic_layout_sample',
          'publishTitle': '在海螺沟看冰川泡温泉',
          'articleMarkdownDigest': articleDigest,
          'articleAssetManifest': renderManifest,
          'assets': declaredAssets,
        }),
        encoding: utf8,
      );

      final doc = renderer.render(
        MarkdownSeoRenderInput(
          postId: 'topic_layout_sample',
          title: '在海螺沟看冰川泡温泉',
          articleMarkdownDigest: articleDigest,
          articleMarkdown: article,
          articleAssetManifest: renderManifest,
        ),
      );

      expect(doc.indexable, isTrue);
      // 机械收尾标题门：渲染结果不得包含被禁止的 “适合谁” 小标题。
      expect(doc.html, isNot(contains('适合谁')));

      // 每个发布 asset：渲染出 data-asset-id，且 sourceAssetRef 相对 batch 根可回查到原图。
      expect(declaredAssets, isNotEmpty);
      for (final asset in declaredAssets) {
        final assetId = asset['assetId'] as String;
        final sourceAssetRef = asset['sourceAssetRef'] as String;
        expect(doc.html, contains('data-asset-id="$assetId"'));
        expect(
          sourceAssetRef.startsWith('/'),
          isFalse,
          reason: '禁止绝对路径: $sourceAssetRef',
        );
        final sourceFile = File('${batchDir.path}/$sourceAssetRef');
        expect(
          sourceFile.existsSync(),
          isTrue,
          reason: '回查源图不存在: ${sourceFile.path}',
        );
      }
      expect(doc.referencedAssetUrls, isNotEmpty);
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

    test('retired Post visibility is rejected instead of exposed', () {
      expect(
        () => renderer.render(
          const MarkdownSeoRenderInput(
            postId: 'retired_visibility',
            title: '已退役可见性',
            visibility: 'circle_visible',
            articleMarkdown: '# 不应渲染',
          ),
        ),
        throwsArgumentError,
      );
    });
  });
}

String _sha256Digest(String payload) =>
    'sha256:${sha256.convert(utf8.encode(payload))}';
