// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-003
// spec_ref: specs/feature-tree/discovery-content/content-type-framework/markdown-article-kernel/spec.md#gwt-004
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_markdown_codec.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/application/public/media_asset_manifest_resolver.dart';
import 'package:quwoquan_app/runtime/transport/media/content_media_url.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart';

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
          assistantUsePolicy: AssistantUsePolicy.exclude,
        );

        expect(markdown, contains('summary: "用户确认摘要"'));
        expect(markdown, contains('tag_refs:'));
        expect(markdown, contains('- "Topic/旅行/城市漫步"'));
        expect(markdown, contains('entity_refs:'));
        expect(markdown, contains('- "entity:sight:west_lake"'));
        expect(markdown, contains('assistantUsePolicy: exclude'));

        final parsed = ArticleMarkdownCodec.parseDocument(markdown);
        expect(parsed.title, '西湖一日游');
        expect(parsed.body, contains('正文内容'));
      },
    );
  });

  group('ArticleMarkdownCodec — 行内样式 roundtrip（GWT-002）', () {
    test('样式 span 序列化为成对记号，重新解析后样式等价不丢失', () {
      const text = '清晨出发去看雪山日照金山';
      final document = ArticleDocumentData(
        nodes: <ArticleDocumentNode>[
          const ArticleDocumentNode(
            id: 'p1',
            type: ArticleDocumentNodeType.paragraph,
            text: text,
            spans: <ArticleInlineSpan>[
              ArticleInlineSpan(start: 0, end: 4, bold: true),
              ArticleInlineSpan(start: 6, end: 8, italic: true),
              ArticleInlineSpan(start: 8, end: 10, bold: true, italic: true),
              ArticleInlineSpan(start: 10, end: 12, underline: true),
            ],
          ),
        ],
      );

      final markdown = ArticleMarkdownCodec.serializeDocument(document);
      expect(markdown, contains('**清晨出发**'));
      expect(markdown, contains('*雪山*'));
      expect(markdown, contains('***日照***'));
      expect(markdown, contains('++金山++'));

      final reparsed = ArticleMarkdownCodec.parseDocument(markdown);
      final paragraph = reparsed.nodes
          .where((node) => node.text.contains('清晨出发'))
          .single;
      // 记号不得以字面量残留在正文。
      expect(paragraph.text, text);
      final boldSpan = paragraph.spans.singleWhere(
        (span) => span.bold && !span.italic,
      );
      expect(paragraph.text.substring(boldSpan.start, boldSpan.end), '清晨出发');
      final italicSpan = paragraph.spans.singleWhere(
        (span) => span.italic && !span.bold,
      );
      expect(paragraph.text.substring(italicSpan.start, italicSpan.end), '雪山');
      final boldItalicSpan = paragraph.spans.singleWhere(
        (span) => span.bold && span.italic,
      );
      expect(
        paragraph.text.substring(boldItalicSpan.start, boldItalicSpan.end),
        '日照',
      );
      final underlineSpan = paragraph.spans.singleWhere(
        (span) => span.underline,
      );
      expect(
        paragraph.text.substring(underlineSpan.start, underlineSpan.end),
        '金山',
      );
    });

    test('样式记号与 mention 共存，mention 段原子不被切分', () {
      final document = ArticleMarkdownCodec.parseDocument('''
---
title: 混排样式
---
# 混排样式

**强烈推荐**去@[灵隐寺](entity:sight:west_lake)走走，~~不要~~一定要带相机。
''');
      final paragraph = document.nodes
          .where((node) => node.text.contains('强烈推荐'))
          .single;
      expect(paragraph.text, '强烈推荐去灵隐寺走走，不要一定要带相机。');
      final mention = paragraph.spans.singleWhere(
        (span) => span.isInlineMention,
      );
      expect(
        paragraph.text.substring(mention.start, mention.end),
        '灵隐寺',
      );
      final bold = paragraph.spans.singleWhere((span) => span.bold);
      expect(paragraph.text.substring(bold.start, bold.end), '强烈推荐');
      final strike = paragraph.spans.singleWhere(
        (span) => span.strikethrough,
      );
      expect(paragraph.text.substring(strike.start, strike.end), '不要');

      // 再序列化：三种记号原样写回。
      final serialized = ArticleMarkdownCodec.serializeDocument(document);
      expect(serialized, contains('**强烈推荐**'));
      expect(serialized, contains('@[灵隐寺](entity:sight:west_lake)'));
      expect(serialized, contains('~~不要~~'));
    });

    test('未闭合记号按字面量处理不吞字，病态输入不 crash', () {
      final document = ArticleMarkdownCodec.parseDocument('''
---
title: 边界输入
---
# 边界输入

今天股价 *上涨了，明天呢。

评分是 5*4=20 而 3**2=9 也对。
''');
      final first = document.nodes
          .where((node) => node.text.contains('上涨'))
          .single;
      // 单个未闭合 `*` 保留为字面量。
      expect(first.text, contains('*上涨了'));
      expect(first.spans.where((span) => !span.isInlineMention), isEmpty);

      final second = document.nodes
          .where((node) => node.text.contains('评分'))
          .single;
      // 数学表达式里的成对 `*` 会被识别为斜体区段——这是成对语义的
      // 已知代价，但正文字符必须一个不丢。
      expect(second.text.replaceAll(' ', ''), contains('5'));
      expect(second.text, contains('=20'));
      expect(second.text, contains('=9'));
    });

    test('富块不做有损压缩：quote/callout/code 保留块语义并原样写回（GWT-003）', () {
      // 同构数据工程供稿形态：quote、callout 指令与 fenced code。
      final document = ArticleMarkdownCodec.parseDocument('''
---
title: 富块保真
---
# 富块保真

正文开头一段。

> 山不在高，有仙则名。

:::callout
出发前请确认门票预约成功。
:::

```dart
void main() { print('hello'); }
```
''');
      final quote = document.nodes.singleWhere(
        (node) => node.type == ArticleDocumentNodeType.quote,
      );
      expect(quote.text, '山不在高，有仙则名。');
      final callout = document.nodes.singleWhere(
        (node) => node.type == ArticleDocumentNodeType.callout,
      );
      expect(callout.text, '出发前请确认门票预约成功。');
      final code = document.nodes.singleWhere(
        (node) => node.type == ArticleDocumentNodeType.codeBlock,
      );
      expect(code.text, contains("print('hello')"));
      expect(code.codeLanguage, 'dart');

      // 投影不压缩：三类以自身类型进入 contentBlocks 与正文可搜索文本。
      final blockTypes = document.contentBlocks
          .map((block) => block.type)
          .toSet();
      expect(blockTypes, contains(ArticleDocumentBlockType.quote));
      expect(blockTypes, contains(ArticleDocumentBlockType.callout));
      expect(blockTypes, contains(ArticleDocumentBlockType.codeBlock));
      expect(document.body, contains('山不在高'));

      // 序列化原样写回（编辑器加载不降级）。
      final serialized = ArticleMarkdownCodec.serializeDocument(document);
      expect(serialized, contains('> 山不在高，有仙则名。'));
      expect(serialized, contains(':::callout'));
      expect(serialized, contains('```dart'));
      expect(serialized, contains("print('hello')"));

      // 再解析等价（roundtrip 收敛）。
      final reparsed = ArticleMarkdownCodec.parseDocument(serialized);
      expect(
        reparsed.nodes
            .where(
              (node) =>
                  node.type == ArticleDocumentNodeType.quote ||
                  node.type == ArticleDocumentNodeType.callout ||
                  node.type == ArticleDocumentNodeType.codeBlock,
            )
            .length,
        3,
      );
    });

    test('分段真相源：样式与 mention 重叠时字符级合成正确', () {
      const text = '前往灵隐寺的路上';
      const spans = <ArticleInlineSpan>[
        ArticleInlineSpan(start: 0, end: 8, bold: true),
        ArticleInlineSpan(
          start: 2,
          end: 5,
          kind: 'entity',
          targetType: 'entity',
          targetId: 'entity:sight:west_lake',
          displayText: '灵隐寺',
        ),
      ];
      final segments = resolveArticleInlineSegments(text, spans);
      expect(segments, hasLength(3));
      expect(segments[0].bold, isTrue);
      expect(segments[0].mention, isNull);
      expect(text.substring(segments[1].start, segments[1].end), '灵隐寺');
      expect(segments[1].mention, isNotNull);
      expect(segments[2].bold, isTrue);
    });
  });

  group('ArticleMarkdownCodec — 链接与嵌套列表 roundtrip（GWT-004）', () {
    test('链接解析为原子 link span，序列化写回 [text](url)', () {
      const markdown = '''
---
title: "t"
---

行程详见 [官网攻略](https://example.com/guide) 一文。
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final paragraph = parsed.nodes
          .where((node) => node.text.contains('官网攻略'))
          .single;
      expect(paragraph.text, '行程详见 官网攻略 一文。');
      final linkSpan = paragraph.spans.single;
      expect(linkSpan.kind, 'link');
      expect(linkSpan.isLink, isTrue);
      expect(linkSpan.targetId, 'https://example.com/guide');
      expect(
        paragraph.text.substring(linkSpan.start, linkSpan.end),
        '官网攻略',
      );

      final reserialized = ArticleMarkdownCodec.serializeDocument(
        ArticleDocumentData(nodes: parsed.nodes),
      );
      expect(
        reserialized,
        contains('[官网攻略](https://example.com/guide)'),
      );
    });

    test('恶意 scheme 不产生 link span，按字面量输出', () {
      const markdown = '''
---
title: "t"
---

点这里 [中奖](javascript:alert(1)) 领取。
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final paragraph = parsed.nodes
          .where((node) => node.text.contains('中奖'))
          .single;
      expect(paragraph.spans.where((span) => span.isLink), isEmpty);
      expect(paragraph.text, contains('[中奖](javascript:alert(1))'));
    });

    test('链接段与样式段共存：link 段原子不被样式记号切分', () {
      const markdown = '''
---
title: "t"
---

**强调 [链接](https://a.b/c) 收尾**
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final paragraph = parsed.nodes
          .where((node) => node.text.contains('链接'))
          .single;
      final segments = resolveArticleInlineSegments(
        paragraph.text,
        paragraph.spans,
      );
      final linkSegment = segments.singleWhere(
        (segment) => segment.mention?.isLink == true,
      );
      expect(
        paragraph.text.substring(linkSegment.start, linkSegment.end),
        '链接',
      );
      expect(
        segments.where((segment) => segment.bold && segment.mention == null),
        isNotEmpty,
      );
    });

    test('嵌套列表 roundtrip：两空格/级缩进与 listDepth 互相还原', () {
      const markdown = '''
---
title: "t"
---

- 顶层项
  - 一级嵌套
    - 二级嵌套
1. 顶层有序
  2. 一级有序
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final bullets = parsed.nodes
          .where((node) => node.type == ArticleDocumentNodeType.bulletItem)
          .toList();
      expect(bullets.map((node) => node.listDepth), <int>[0, 1, 2]);
      final ordered = parsed.nodes
          .where((node) => node.type == ArticleDocumentNodeType.orderedItem)
          .toList();
      expect(ordered.map((node) => node.listDepth), <int>[0, 1]);

      final reserialized = ArticleMarkdownCodec.serializeDocument(
        ArticleDocumentData(nodes: parsed.nodes),
      );
      expect(reserialized, contains('\n- 顶层项'));
      expect(reserialized, contains('\n  - 一级嵌套'));
      expect(reserialized, contains('\n    - 二级嵌套'));
      expect(reserialized, contains('\n  '));

      // 再解析一轮：嵌套结构不漂移。
      final reparsed = ArticleMarkdownCodec.parseDocument(reserialized);
      final reparsedBullets = reparsed.nodes
          .where((node) => node.type == ArticleDocumentNodeType.bulletItem)
          .toList();
      expect(reparsedBullets.map((node) => node.listDepth), <int>[0, 1, 2]);
    });

    test('站内实体链接转 canonical entity mention（数据工程真实供稿形态）', () {
      // fixture 取自 quwoquan_data 真实发布物形态：H1 与正文均含
      // [label](/entity/<domain>/<etype>/<name>) 站内链接。
      const markdown = '''
---
title: "杭州西湖攻略"
markdownDialect: qwq-rich-md
---

# [杭州西湖](/entity/地点/景区/杭州西湖)攻略

真正牵动期待的却是[杭州西湖](/entity/地点/景区/杭州西湖)——湖面与堤桥叠在一起。
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      // H1 剥离链接记号后与 frontmatter title 相同：跳过重复标题，
      // 不再渲染裸记号 heading。
      expect(
        parsed.nodes.where(
          (node) =>
              node.type == ArticleDocumentNodeType.headingMajor &&
              node.text.contains('杭州西湖攻略'),
        ),
        isEmpty,
        reason: 'H1 与 title 相同时必须跳过（链接记号不参与比较）',
      );
      expect(parsed.title, '杭州西湖攻略');

      final paragraph = parsed.nodes
          .where((node) => node.text.contains('湖面与堤桥'))
          .single;
      expect(paragraph.text, contains('真正牵动期待的却是杭州西湖——'));
      expect(paragraph.text, isNot(contains('[')));
      final mention = paragraph.spans.single;
      expect(mention.kind, 'entity');
      expect(mention.isInlineMention, isTrue);
      expect(
        mention.targetId,
        'entity:景区:杭州西湖',
        reason: '必须与数据工程 canonical 规则一致（跳过 domain 段）',
      );
      expect(
        paragraph.text.substring(mention.start, mention.end),
        '杭州西湖',
      );

      // 序列化统一写回 canonical mention 记号。
      final reserialized = ArticleMarkdownCodec.serializeDocument(
        ArticleDocumentData(nodes: parsed.nodes),
      );
      expect(reserialized, contains('@[杭州西湖](entity:景区:杭州西湖)'));
      expect(reserialized, isNot(contains('](/entity/')));
    });

    test('不合形态的站内路径按字面量保留，不产生 span', () {
      const markdown = '''
---
title: "t"
---

破损链接 [某地](/entity/只有一段) 保持字面量。
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final paragraph = parsed.nodes
          .where((node) => node.text.contains('某地'))
          .single;
      expect(paragraph.spans, isEmpty);
      expect(paragraph.text, contains('[某地](/entity/只有一段)'));
    });

    test('段落对齐 :::align 指令与分隔线 --- roundtrip', () {
      const markdown = '''
---
title: "t"
---

普通段落。

:::align value="center"
居中的段落文本
:::

---

:::align value="right"
右对齐段落
:::
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final centered = parsed.nodes
          .where((node) => node.text.contains('居中的段落文本'))
          .single;
      expect(centered.type, ArticleDocumentNodeType.paragraph);
      expect(centered.textAlign, 'center');
      final right = parsed.nodes
          .where((node) => node.text.contains('右对齐段落'))
          .single;
      expect(right.textAlign, 'right');
      final plain = parsed.nodes
          .where((node) => node.text.contains('普通段落'))
          .single;
      expect(plain.textAlign, '');
      expect(
        parsed.nodes.where(
          (node) => node.type == ArticleDocumentNodeType.divider,
        ),
        hasLength(1),
        reason: '--- 必须进入 Document 模型为 divider 节点',
      );

      final reserialized = ArticleMarkdownCodec.serializeDocument(
        ArticleDocumentData(nodes: parsed.nodes),
      );
      expect(reserialized, contains(':::align value="center"'));
      expect(reserialized, contains(':::align value="right"'));
      expect(reserialized, contains('\n---\n'));

      final reparsed = ArticleMarkdownCodec.parseDocument(reserialized);
      expect(
        reparsed.nodes
            .where((node) => node.text.contains('居中的段落文本'))
            .single
            .textAlign,
        'center',
        reason: '对齐 roundtrip 不得漂移',
      );
      expect(
        reparsed.nodes.where(
          (node) => node.type == ArticleDocumentNodeType.divider,
        ),
        hasLength(1),
      );
    });

    test('超深缩进夹紧到 2 级，不产生越界深度', () {
      const markdown = '''
---
title: "t"
---

        - 超深嵌套项
''';
      final parsed = ArticleMarkdownCodec.parseDocument(markdown);
      final bullet = parsed.nodes
          .where((node) => node.type == ArticleDocumentNodeType.bulletItem)
          .single;
      expect(bullet.listDepth, 2);
    });
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
