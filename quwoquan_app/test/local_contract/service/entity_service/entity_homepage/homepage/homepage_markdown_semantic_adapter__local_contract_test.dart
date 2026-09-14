// spec_ref: specs/feature-tree/discovery-content/object-homepage-coverage-scaling/spec.md
import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/qwq_markdown.dart';
import 'package:quwoquan_app/service/entity_service/entity_homepage/homepage/presentation/homepage_introduction_page.dart';

const _fixture = '''---
markdownDialect: qwq-rich-md
---
# 标题

正文 **加粗**。

- 列表项

> 引用

:::callout title="提示"
提示内容
:::

```dart
print('safe');
```

| 名称 | 值 |
| --- | --- |
| 甲 | 一 |

:::groupedDirectory
## 分组
- 条目
:::

术语
: 定义

[^1]: 脚注

:::figure caption="图注"
asset://figure-1
:::

:::gallery ids="gallery-1,gallery-2"
:::
''';

void main() {
  test('旧的 MarkdownLite 旁路已删除', () {
    final source = Uri.file(
      'lib/service/entity_service/entity_homepage/homepage/presentation/'
      'homepage_introduction_page_content.dart',
    ).toFilePath();
    expect(File(source).readAsStringSync(), isNot(contains('_MarkdownLite')));
  });

  test(
    'Homepage adapter 与 article parser 的 kind/order/text/fingerprint 一致',
    () {
      final article = const QwqMarkdownParser()
          .parse(_fixture, requireVersion: true)
          .document;
      final homepage = HomepageMarkdownDocumentAdapter.parse(_fixture);

      expect(homepage.isAvailable, isTrue);
      expect(
        homepage.semanticKinds,
        article.semanticEnvelope!.nodes.map((node) => node.kind.name).toList(),
      );
      expect(
        homepage.semanticTexts,
        article.semanticEnvelope!.nodes
            .map((node) => node.attributes['text']?.toString() ?? '')
            .toList(),
      );
      expect(
        homepage.semanticFingerprint,
        article.semanticEnvelope!.semanticFingerprint,
      );
      expect(
        homepage.requiredCapabilities,
        article.semanticEnvelope!.requiredCapabilities,
      );
      expect(
        homepage.semanticKinds,
        containsAllInOrder(<String>[
          'heading',
          'paragraph',
          'listItem',
          'blockquote',
          'callout',
          'codeBlock',
          'table',
          'groupedDirectory',
          'definitionList',
          'footnoteDefinition',
          'figure',
          'gallery',
        ]),
      );
    },
  );

  test('缺版本、未知版本与 raw HTML 均 fail closed', () {
    expect(HomepageMarkdownDocumentAdapter.parse('正文').isAvailable, isFalse);
    expect(
      HomepageMarkdownDocumentAdapter.parse('''---
markdownDialect: future-markdown
---
正文''').isAvailable,
      isFalse,
    );
    expect(
      HomepageMarkdownDocumentAdapter.parse('''---
markdownDialect: qwq-rich-md
---
<script>alert(1)</script>''').isAvailable,
      isFalse,
    );
  });

  testWidgets('不可用正文显示 typed 终态且不展示 raw HTML', (tester) async {
    const rawHtml = '<script>alert(1)</script>';
    await tester.pumpWidget(
      const CupertinoApp(
        home: CupertinoPageScaffold(
          child: HomepageMarkdownContent(
            markdown: '---\nmarkdownDialect: qwq-rich-md\n---\n$rawHtml',
          ),
        ),
      ),
    );
    await tester.pump();

    expect(
      find.bySemanticsIdentifier('homepage_markdown_semantic_unavailable'),
      findsOneWidget,
    );
    expect(find.textContaining(rawHtml), findsNothing);
  });

  testWidgets('viewport 宽度只改变几何，不改变 semantic 序列', (tester) async {
    final expected = HomepageMarkdownDocumentAdapter.parse(_fixture);
    for (final width in <double>[320, 768]) {
      await tester.binding.setSurfaceSize(Size(width, 900));
      await tester.pumpWidget(
        const CupertinoApp(
          home: CupertinoPageScaffold(
            child: SingleChildScrollView(
              child: HomepageMarkdownContent(markdown: _fixture),
            ),
          ),
        ),
      );
      await tester.pump();
      final actual = HomepageMarkdownDocumentAdapter.parse(_fixture);
      expect(actual.semanticKinds, expected.semanticKinds);
      expect(actual.semanticTexts, expected.semanticTexts);
      expect(actual.semanticFingerprint, expected.semanticFingerprint);
      expect(find.text('名称'), findsOneWidget);
      expect(find.text('分组'), findsOneWidget);
    }
    await tester.binding.setSurfaceSize(null);
  });
}
