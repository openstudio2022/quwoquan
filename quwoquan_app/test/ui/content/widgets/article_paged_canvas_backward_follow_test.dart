import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

void main() {
  testWidgets(
    'single-page backward drag stays on shared curl path without legacy debug overlay',
    (tester) async {
      const pages = <ArticlePageData>[
        ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
        ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ];

      await tester.pumpWidget(
        const MaterialApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: SizedBox(
                width: 430,
                height: 900,
                child: ArticleReadOnlyBookDeck(
                  pages: pages,
                  initialPage: 1,
                  template: ArticleTemplatePreset.journal,
                  fontPreset: ArticleFontPreset.clean,
                  metrics: ArticleCanvasMetrics(
                    aspectRatio: 0.72,
                    outerPadding: EdgeInsets.all(8),
                    contentPadding: EdgeInsets.fromLTRB(16, 20, 16, 16),
                    headerReservedHeight: 0,
                    footerReservedHeight: 0,
                    wrapImageGap: 12,
                    wrapImageMaxWidth: 132,
                    fullWidthImageAspectRatio: 4 / 3,
                    journalImageAspectRatio: 1,
                    inlineImageSpacing: 8,
                  ),
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await tester.pump();
      await gesture.moveBy(const Offset(40, -8));
      await tester.pump();

      expect(find.byType(PageflipBookBackwardDebugOverlay), findsNothing);
      expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
      expect(find.text('第一页正文'), findsWidgets);
      expect(find.text('第二页正文'), findsWidgets);
      await gesture.moveBy(const Offset(80, -10));
      await tester.pump();

      expect(find.byType(PageflipBookBackwardDebugOverlay), findsNothing);
      expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
      expect(find.text('第一页正文'), findsWidgets);
      expect(find.text('第二页正文'), findsWidgets);

      await gesture.up();
      await tester.pumpAndSettle();
    },
  );
}
