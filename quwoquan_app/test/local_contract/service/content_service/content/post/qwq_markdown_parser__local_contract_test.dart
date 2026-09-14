import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown.dart';

void main() {
  group('QwqMarkdownParser', () {
    const parser = QwqMarkdownParser();

    test('解析标准 Markdown 与 front matter', () {
      final result = parser.parse('''
---
title: 西湖半日城市漫游
summary: 从湖滨到龙井路
template: journal
fontPreset: clean
coverImage: asset://cover
entity_refs:
  - trees/entities/地点/西湖.yaml
tag_refs:
  - trees/tags/主题/城市漫游.yaml
source_urls:
  - https://example.com/source
---
# 西湖半日城市漫游

第一段正文，包含[来源](https://example.com/source)。

1. 先到湖滨
- 再去断桥
> 适合清晨出发
![封面](asset://cover)
''');

      expect(result.isValid, isTrue);
      final document = result.document;
      expect(document.frontMatter.title, '西湖半日城市漫游');
      expect(
        document.frontMatter.entityRefs,
        contains('trees/entities/地点/西湖.yaml'),
      );
      expect(
        document.blocks.map((block) => block.kind),
        contains(QwqMarkdownBlockKind.heading),
      );
      expect(
        document.blocks.map((block) => block.kind),
        contains(QwqMarkdownBlockKind.orderedItem),
      );
      expect(
        document.blocks.map((block) => block.kind),
        contains(QwqMarkdownBlockKind.bulletItem),
      );
      expect(
        document.blocks.map((block) => block.kind),
        contains(QwqMarkdownBlockKind.quote),
      );
      expect(document.referencedAssetIds, contains('cover'));
    });

    test('解析 QWQ 富布局指令并保留布局意图', () {
      final result = parser.parse('''
:::figure id="cover" layout="wrapRight" caption="湖滨步道"
asset://cover
:::

:::callout type="tip" title="拍摄建议"
上午九点前湖面反光更柔和。
:::

:::gallery ids="bridge,street,tea" layout="masonry" caption="三个停留点"
:::
''');

      expect(result.isValid, isTrue);
      final blocks = result.document.blocks;
      expect(blocks[0].kind, QwqMarkdownBlockKind.figure);
      expect(blocks[0].assetRef!.assetId, 'cover');
      expect(blocks[0].assetRef!.layout, QwqMarkdownImageLayout.wrapRight);
      expect(blocks[1].kind, QwqMarkdownBlockKind.callout);
      expect(blocks[1].attributes['type'], 'tip');
      expect(blocks[2].kind, QwqMarkdownBlockKind.gallery);
      expect(blocks[2].assetRefs.map((asset) => asset.assetId), <String>[
        'bridge',
        'street',
        'tea',
      ]);
    });

    test('H1-H6 与 inline 由单一 parser 解析', () {
      final result = parser.parse('''
---
markdownDialect: qwq-rich-md
---
# H1
###### H6

**粗体** *斜体* `代码` ++下划线++ ~~删除~~ @[西湖](entity:sight:west_lake) [官网](https://example.com)
''');
      expect(result.isValid, isTrue);
      expect(
        result.document.blocks
            .where((block) => block.kind == QwqMarkdownBlockKind.heading)
            .map((block) => block.level),
        <int>[1, 6],
      );
      expect(
        result.document.blocks.last.inlines.map((inline) => inline.kind),
        containsAll(<QwqMarkdownInlineKind>[
          QwqMarkdownInlineKind.bold,
          QwqMarkdownInlineKind.italic,
          QwqMarkdownInlineKind.code,
          QwqMarkdownInlineKind.underline,
          QwqMarkdownInlineKind.strikethrough,
          QwqMarkdownInlineKind.mention,
          QwqMarkdownInlineKind.link,
        ]),
      );
    });

    test('raw HTML 与未闭合 code fence blocking', () {
      final html = parser.parse('''
---
markdownDialect: qwq-rich-md
---
正文 <span>bad</span> 尾部
''');
      expect(
        html.document.diagnostics.map((item) => item.code),
        contains('html_not_allowed'),
      );
      final fence = parser.parse('''
---
markdownDialect: qwq-rich-md
---
```dart
void main() {}
''');
      expect(
        fence.document.diagnostics.map((item) => item.code),
        contains('code_fence_unclosed'),
      );
    });

    test('typed AST 支持 table directory definition footnote', () {
      final result = parser.parse('''
---
markdownDialect: qwq-rich-md
---
| 名称 | 地址 |
| --- | ---: |
| 西湖 | 杭州 |

:::groupedDirectory
## 景点
- 西湖
:::

术语
: 定义内容

[^source]: 来源说明
''');
      final table = result.document.blocks.firstWhere(
        (block) => block.kind == QwqMarkdownBlockKind.table,
      );
      expect(table.table!.logicalGrid, <List<String>>[
        <String>['名称', '地址'],
        <String>['西湖', '杭州'],
      ]);
      expect(
        result.document.blocks.map((block) => block.kind),
        containsAll(<QwqMarkdownBlockKind>[
          QwqMarkdownBlockKind.groupedDirectory,
          QwqMarkdownBlockKind.definitionList,
          QwqMarkdownBlockKind.footnote,
        ]),
      );
      expect(result.document.isReadOnly, isTrue);
    });

    test('拒绝任意 HTML 和未知富布局指令', () {
      final result = parser.parse('''
<div>bad</div>

:::unknown
bad
:::
''');

      expect(result.isValid, isFalse);
      expect(
        result.document.diagnostics.map((diagnostic) => diagnostic.code),
        containsAll(<String>['html_not_allowed', 'directive_not_allowed']),
      );
    });
  });
}
