import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/markdown/qwq_markdown.dart';

void main() {
  group('MarkdownPaginationEngine', () {
    const parser = QwqMarkdownParser();
    const engine = MarkdownPaginationEngine();

    test('同一 Markdown 在不同视口可得到稳定有序分页', () {
      final document = parser.parse('''
# 标题

第一段正文内容较长，用于撑开分页估算单位，确保分页模型不会打乱块顺序。

:::figure id="cover" layout="wrapLeft" caption="封面"
asset://cover
:::

第二段正文继续描述路线和拍摄建议。
''').document;

      final compactPages = engine.paginate(
        document: document,
        profile: const QwqMarkdownPaginationProfile(viewportSize: Size(390, 640)),
      );
      final widePages = engine.paginate(
        document: document,
        profile: const QwqMarkdownPaginationProfile(viewportSize: Size(820, 1024)),
      );

      expect(compactPages, isNotEmpty);
      expect(widePages, isNotEmpty);
      expect(
        compactPages.expand((page) => page.blockIds),
        document.blocks.map((block) => block.id),
      );
      expect(
        widePages.expand((page) => page.blockIds),
        document.blocks.map((block) => block.id),
      );
      final compactFigure = compactPages
          .expand((page) => page.blocks)
          .firstWhere((block) => block.kind == QwqMarkdownBlockKind.figure);
      expect(compactFigure.assetRef!.layout, QwqMarkdownImageLayout.fullWidth);
      expect(compactFigure.attributes['layoutDowngradedFrom'], 'wrapLeft');
    });

    testWidgets('ImmersiveMarkdownReader 渲染 Markdown page surface', (tester) async {
      final document = parser.parse('''
# 西湖

第一段正文。

:::callout type="tip" title="拍摄建议"
上午九点前出发。
:::
''').document;

      await tester.pumpWidget(
        CupertinoApp(
          home: SizedBox(
            width: 390,
            height: 640,
            child: ImmersiveMarkdownReader(document: document),
          ),
        ),
      );

      expect(find.text('西湖'), findsOneWidget);
      expect(find.text('第一段正文。'), findsOneWidget);
      expect(find.text('拍摄建议'), findsOneWidget);
    });
  });
}
