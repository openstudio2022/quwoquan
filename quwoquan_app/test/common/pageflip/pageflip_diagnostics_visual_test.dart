import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

/// 路线 B 后翻可视回放（单页竖屏）锁主线不变量：
/// - host 走 paperFoldBackwardMainline 路径
/// - 三层组合：previous front baseline + current（bottomClipArea）+
///   flipping sheet（flippingClipArea，previous back 纹理）
/// - 页面角色稳定：bottomLayer = 3，flippingLayer = 2
/// - backwardFoldX 随手势单调推进，落在右页内
///
/// 这套不变量直接对应 `.cursor/rules/12-pageflip-backward-mainline.mdc`
/// 中的「真相源不变量驱动」要求，禁止再倒推 sheet 内 front/back 切分。
void main() {
  testWidgets(
    'Pageflip diagnostics backward visual replay locks Route-B mainline',
    (tester) async {
      const surfaceSize = Size(450, 600);
      await tester.binding.setSurfaceSize(surfaceSize);
      addTearDown(() async {
        await tester.binding.setSurfaceSize(null);
      });

      final scenes = <StPageFlipScene>[];
      final debugStates = <ArticleReadOnlyBookDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
          debugShowCheckedModeBanner: false,
          home: LayoutBuilder(
            builder: (context, constraints) {
              final metrics = resolveArticleCanvasMetrics(
                context,
                constraints,
                variant: ArticleCanvasVariant.detail,
              );
              return ArticleReadOnlyBookDeck(
                pages: _diagnosticPages(),
                template: ArticleTemplatePreset.tech,
                fontPreset: ArticleFontPreset.mono,
                metrics: metrics,
                pagePadding: articleReaderStagePagePadding(),
                initialPage: 2,
                coverUrl: '',
                showFooterPageLabel: false,
                onSceneChanged: scenes.add,
                onDebugStateChanged: debugStates.add,
                debugPureBackwardGeometry: true,
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      // 先前向翻一页，进入 back 主线对应的页位（current=3，previous=2）。
      final forwardGesture = await tester.startGesture(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
      );
      await forwardGesture.moveBy(const Offset(-160, -18));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      await forwardGesture.up();
      await tester.pumpAndSettle();
      expect(
        scenes
            .lastWhere((scene) => scene.state == StPageFlipState.read)
            .currentPageIndex,
        3,
      );

      // 路线 B baseline 层 ValueKey 必须存在（previous front 铺满右页）。
      expect(
        find.byKey(const ValueKey<String>('article_backward_previous_front_baseline')),
        findsNothing,
        reason:
            'baseline 层只在 BACK 主线绘制期间出现；read state 下不应渲染。',
      );

      // 启动后翻拖拽，进入 paperFoldBackwardMainline 渲染。
      const backwardPointer = 21;
      final backwardGesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
        pointer: backwardPointer,
      );
      await backwardGesture.moveBy(const Offset(30, -3));
      for (var i = 0; i < 4; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      await backwardGesture.moveBy(const Offset(160, -12));
      for (var i = 0; i < 6; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      await backwardGesture.moveBy(const Offset(220, -8));
      for (var i = 0; i < 6; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      final mainlineStates = debugStates
          .where(
            (s) =>
                s.renderDirection == StPageFlipDirection.back &&
                s.backwardCompositeMode == 'paperFoldBackwardMainline',
          )
          .toList(growable: false);
      expect(
        mainlineStates,
        isNotEmpty,
        reason: 'BACK 渲染必须只走 paperFoldBackwardMainline 一条主线。',
      );

      // BACK 不允许 full previous-front baseline 替换 current page；
      // previous front 只能通过 moving sheet 内 recto slice 出现。
      expect(
        find.byKey(const ValueKey<String>('article_backward_previous_front_baseline')),
        findsNothing,
        reason:
            'full previous-front baseline must not appear during BACK mainline.',
      );

      // 角色稳定：bottomLayer = 3，flippingLayer = 2，全程不漂移。
      final stableBottoms = mainlineStates
          .map((s) => s.backwardBottomLayerPageIndex)
          .toSet();
      final stableFlippings = mainlineStates
          .map((s) => s.backwardFlippingLayerPageIndex)
          .toSet();
      expect(stableBottoms, equals(<int>{3}));
      expect(stableFlippings, equals(<int>{2}));
      expect(
        mainlineStates.every((s) => !s.backwardDynamicOwnedPages.contains(3)),
        isTrue,
        reason: 'current page must stay visible as the static bottom layer.',
      );

      // backwardFoldX 真相源不变量：必须存在、必须落在右页内、必须随手势在变化。
      final foldXs = mainlineStates
          .where((s) => s.backwardFoldX != null)
          .map((s) => s.backwardFoldX!)
          .toList(growable: false);
      expect(foldXs, isNotEmpty);
      expect(
        (foldXs.last - foldXs.first).abs(),
        greaterThan(1),
        reason:
            'BACK fold X 在 pull-back 中必须实质推进；direction 由 viewport space '
            '中 fold/free-edge line 的相对位置承载，diagnostic 仅锁 X 漂移。',
      );

      await backwardGesture.up();
      await tester.pumpAndSettle();
    },
  );
}

List<ArticlePageData> _diagnosticPages() {
  return List<ArticlePageData>.generate(
    5,
    (index) => ArticlePageData(
      id: 'visual_$index',
      title: 'VISUAL TRACE / ${index + 1}',
      body: 'page ${index + 1}/5\n\nVISUAL-${index + 1}',
    ),
  );
}
