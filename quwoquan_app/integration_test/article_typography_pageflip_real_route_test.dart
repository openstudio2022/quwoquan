library;

import 'dart:io';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

const _artifactDirectory =
    '/Users/zhaoyuxi/Projects/quwoquan/quwoquan_app/build/pageflip_m2_acceptance';
const _fixtureImagePath = '/Users/zhaoyuxi/Projects/quwoquan/sim_current.png';

void main() {
  final binding = IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Typography deck pageflip backward keyframes', (tester) async {
    if (Platform.isAndroid) {
      await binding.convertFlutterSurfaceToImage();
    }

    await tester.pumpWidget(
      const MaterialApp(
        home: CupertinoPageScaffold(
          backgroundColor: Colors.black,
          child: SafeArea(
            child: ArticleReadOnlyBookDeck(
              pages: _pages,
              template: ArticleTemplatePreset.journal,
              fontPreset: ArticleFontPreset.clean,
              paperTexture: ArticlePaperTexture.eyeCare,
              showFooterPageLabel: false,
              pagePadding: EdgeInsets.zero,
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
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));

    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);

    await _takeAndPersistScreenshot(binding, 'm2_typography_start');

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    await _takeAndPersistScreenshot(binding, 'm2_typography_forward_page2');

    final backwardHotzone = find.byKey(
      TestKeys.articlePageCurlHotzoneBottomLeft,
    );
    final gesture = await tester.startGesture(
      tester.getBottomLeft(backwardHotzone) + const Offset(6, -6),
    );
    await tester.pump(const Duration(milliseconds: 32));
    await gesture.moveBy(const Offset(72, -8));
    await tester.pump(const Duration(milliseconds: 64));
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
    await _takeAndPersistScreenshot(binding, 'm2_typography_backward_quarter');

    await gesture.moveBy(const Offset(76, -10));
    await tester.pump(const Duration(milliseconds: 64));
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
    await _takeAndPersistScreenshot(binding, 'm2_typography_backward_half');

    await gesture.moveBy(const Offset(80, -10));
    await tester.pump(const Duration(milliseconds: 64));
    await _takeAndPersistScreenshot(
      binding,
      'm2_typography_backward_three_quarter',
    );

    await gesture.up();
    await tester.pumpAndSettle();
    await _takeAndPersistScreenshot(binding, 'm2_typography_backward_commit');

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    final abortGesture = await tester.startGesture(
      tester.getBottomLeft(backwardHotzone) + const Offset(6, -6),
    );
    await tester.pump(const Duration(milliseconds: 32));
    await abortGesture.moveBy(const Offset(98, -10));
    await tester.pump(const Duration(milliseconds: 64));
    await _takeAndPersistScreenshot(
      binding,
      'm2_typography_backward_abort_hold',
    );

    await abortGesture.up();
    await tester.pumpAndSettle();
    await _takeAndPersistScreenshot(
      binding,
      'm2_typography_backward_abort_reset',
    );
  });
}

String _paragraph(int index) {
  return '第${index + 1}段 这一段用于 M2 单页回翻验收，反复强调图片、正文、段落节奏与分页稳定性。'
      '回翻时上一页需要从左向右逐步铺开，同时当前页应被连续遮挡而不是闪切。'
      '为了让 typography 预览稳定地产生多页，这里重复补充几句说明文字：'
      '前翻已经冻结，本轮只验证回翻 soft 主线、卷边跟手性、背面纹理与 abort 回弹。'
      '如果渲染仍出现整页缩放或平面直角结构，就说明 M2 仍未达标。';
}

const List<ArticlePageData> _pages = <ArticlePageData>[
  ArticlePageData(
    id: 'page_1',
    title: '第一页标题',
    body: '${_page1BodyA}${_page1BodyB}',
    imageUrl: _fixtureImagePath,
    imageLayout: 'fullWidth',
    caption: '第一页示意图',
  ),
  ArticlePageData(
    id: 'page_2',
    title: '第二页标题',
    body: '${_page2BodyA}${_page2BodyB}',
    imageUrl: _fixtureImagePath,
    imageLayout: 'fullWidth',
    caption: '第二页整图',
  ),
  ArticlePageData(id: 'page_3', title: '第三页标题', body: _page3Body),
];

const String _page1BodyA = '第一页正文。回翻 commit 后应自然落回这一页。';
const String _page1BodyB = '重点看背面是否连续卷出，以及当前页是否被逐步替换。';
const String _page2BodyA = '第二页正文。这里是 1/4、1/2、3/4 回翻关键帧的基准页。';
const String _page2BodyB = '重点看 front/back 纹理是否稳定，是否仍有平面直角感。';
const String _page3Body = '第三页正文。仅用于保证前翻后仍有后续页面。';

Future<void> _takeAndPersistScreenshot(
  IntegrationTestWidgetsFlutterBinding binding,
  String name,
) async {
  final bytes = await binding.takeScreenshot(name);
  final file = File('$_artifactDirectory/$name.png');
  file.parent.createSync(recursive: true);
  await file.writeAsBytes(bytes, flush: true);
}
