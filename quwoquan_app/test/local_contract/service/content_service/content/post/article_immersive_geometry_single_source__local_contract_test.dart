// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-015
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-015.t1
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-015.t2
//
// 沉浸文章分页与渲染的几何单源（REQ-016）：
// 分页引擎消费的画布几何（宽高比、内容内边距、stage 宽度）必须与
// 渲染 metrics 同源。历史缺陷：分页按 0.72 固定纸比与不含
// topPaperReservedHeight 的 contentPadding 切片，而渲染按真实视口比与
// 实际预留高度铺排，导致每页系统性欠满约 25%。
import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_article_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/content_surface_view.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_flow_layout_engine.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/works_viewer_article.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/templates/article_reader_template_theme.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/works_immersive_viewer_paging.dart';

import '../../../../../support/service/content_service/content/post/content_post_test_builder.dart';

const double _surfaceWidth = 390;
const double _surfaceHeight = 844;
const double _topChromeSafeInset = 47;

ArticleDocumentData _longDocument() {
  final nodes = <ArticleDocumentNode>[
    const ArticleDocumentNode(
      id: 'doc_title',
      type: ArticleDocumentNodeType.documentTitle,
      text: '几何单源验证长文',
    ),
    for (var index = 0; index < 36; index += 1)
      ArticleDocumentNode(
        id: 'p_$index',
        type: ArticleDocumentNodeType.paragraph,
        text:
            '第 $index 段：湖面在清晨的薄雾里缓慢展开，木船沿着岸线滑行，'
            '桨声把水面划出细长的纹路。远处的山脊被光线勾出轮廓，'
            '村落的屋顶次第亮起来，一天的叙事就从这里开始。',
      ),
  ];
  return ArticleDocumentData(nodes: nodes);
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  group('沉浸文章几何单源（GWT-015）', () {
    testWidgets('分页页数等于以渲染几何驱动引擎的页数（分页/渲染同源）', (tester) async {
      await tester.binding.setSurfaceSize(
        const Size(_surfaceWidth, _surfaceHeight),
      );
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final document = _longDocument();
      const template = ArticleTemplatePreset.gentle;
      const fontPreset = ArticleFontPreset.clean;
      const paperTexture = ArticlePaperTexture.darkPaper;
      var resolvedPageCount = 0;

      await tester.pumpWidget(
        CupertinoApp(
          home: SizedBox.expand(
            child: buildWorksViewerArticle(
              post: contentPostViewDataBuilder(
                postId: 'geometry-single-source',
                contentType: 'article',
                title: '几何单源验证长文',
                body: '',
              ),
              article: ContentArticleRender(
                document: document,
                template: template,
                fontPreset: fontPreset,
              ),
              timeLine: '',
              paperTexture: paperTexture,
              enablePageCurl: false,
              onPageChanged: (_) {},
              onResolvedPageCountChanged: (count) => resolvedPageCount = count,
              topChromeSafeInset: _topChromeSafeInset,
              reserveContentIntersection: false,
            ),
          ),
        ),
      );
      await tester.pump();

      // 期望页数：以「渲染消费的同一几何」直接驱动分页引擎。
      final context = tester.element(find.byType(PostWorksViewerArticle));
      final bottomClearance =
          WorksImmersiveContentLayout.overlayBottomClearance(
            context,
            includeIntersection: false,
            gap: AppSpacing.containerMd,
          );
      final contentConstraints = BoxConstraints(
        maxWidth: _surfaceWidth,
        maxHeight: _surfaceHeight - bottomClearance,
      );
      final topPaperReservedHeight =
          _topChromeSafeInset +
          AppSpacing.appChromeTopBarHeight(context) +
          AppSpacing.intraGroupSm;
      final renderMetricsView = resolveImmersiveArticleCanvasMetricsView(
        context,
        contentConstraints,
        topPaperReservedHeight: topPaperReservedHeight,
      );
      final renderMetrics = ArticleCanvasMetrics.fromView(renderMetricsView);
      final typography = resolveArticleTypographyForPaper(
        context,
        paperTexture,
        fontPreset,
      );
      // 渲染 pagePadding 为 zero（immersive edge-to-edge），
      // 纸面 stage 宽度即内容区全宽。
      final stageWidth = contentConstraints.maxWidth;
      final expectedPages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
        document: document,
        metrics: renderMetrics,
        stageWidth: stageWidth,
        titleStyle: typography.titleStyle,
        bodyStyle: typography.bodyStyle,
        viewportSliceHeight: renderMetrics
            .contentSizeForStageWidth(stageWidth)
            .height,
      ).length;

      expect(resolvedPageCount, greaterThan(0));
      expect(
        resolvedPageCount,
        expectedPages,
        reason:
            '分页必须与渲染消费同一几何真相源（GWT-015）：'
            '页数不一致说明分页仍按 0.72 纸比或错误 stage 宽度切片',
      );
    });

    testWidgets('多屏幕比例下分页与渲染派生的 content size 完全相等', (tester) async {
      // GWT-015 GIVEN：长屏约 0.45、设计稿比 0.72、平板 4:3。
      const viewports = <Size>[Size(390, 866), Size(390, 542), Size(1024, 768)];
      await tester.pumpWidget(
        CupertinoApp(home: Builder(builder: (context) => const SizedBox())),
      );
      final context = tester.element(find.byType(SizedBox));
      const topPaperReservedHeight = 90.0;

      for (final viewport in viewports) {
        final contentConstraints = BoxConstraints(
          maxWidth: viewport.width,
          maxHeight: viewport.height,
        );
        final view = resolveImmersiveArticleCanvasMetricsView(
          context,
          contentConstraints,
          topPaperReservedHeight: topPaperReservedHeight,
        );
        final paginationContentSize = ArticleCanvasMetrics.fromView(view)
            .contentSizeForStageWidth(viewport.width);

        // 渲染内容区：纸面铺满视口（immersive edge-to-edge），
        // 内容区 = 视口 - contentPadding（含顶部预留）。
        final renderContentWidth =
            viewport.width -
            view.contentPadding.left -
            view.contentPadding.right;
        final renderContentHeight =
            viewport.height -
            (AppSpacing.containerLg + topPaperReservedHeight) -
            AppSpacing.containerMd;
        expect(
          paginationContentSize.width,
          moreOrLessEquals(renderContentWidth, epsilon: 0.5),
          reason: '${viewport.width}x${viewport.height} 下分页内容宽必须等于渲染内容宽',
        );
        expect(
          paginationContentSize.height,
          moreOrLessEquals(renderContentHeight, epsilon: 0.5),
          reason:
              '${viewport.width}x${viewport.height} 下分页内容高必须等于渲染内容高，'
              '不得回落到 0.72 固定纸比',
        );
      }
    });

    testWidgets('除最后一页外每页尾部余量小于下一个内容块高度', (tester) async {
      await tester.binding.setSurfaceSize(
        const Size(_surfaceWidth, _surfaceHeight),
      );
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        CupertinoApp(home: Builder(builder: (context) => const SizedBox())),
      );
      final context = tester.element(find.byType(SizedBox));
      const contentConstraints = BoxConstraints(
        maxWidth: _surfaceWidth,
        maxHeight: 700,
      );
      final view = resolveImmersiveArticleCanvasMetricsView(
        context,
        contentConstraints,
        topPaperReservedHeight: 90,
      );
      final metrics = ArticleCanvasMetrics.fromView(view);
      final typography = resolveArticleTypographyForPaper(
        context,
        ArticlePaperTexture.darkPaper,
        ArticleFontPreset.clean,
      );
      final document = _longDocument();
      const stageWidth = _surfaceWidth;
      final sliceHeight = metrics.contentSizeForStageWidth(stageWidth).height;
      final structuralPages = ArticleFlowLayoutEngine.buildStructuralPages(
        document: document,
        metrics: metrics,
        stageWidth: stageWidth,
        titleStyle: typography.titleStyle,
        bodyStyle: typography.bodyStyle,
      );
      final runs = ArticleFlowLayoutEngine.computeRunsFromPages(
        structuralPages,
        document: document,
        metrics: metrics,
        stageWidth: stageWidth,
        titleStyle: typography.titleStyle,
        bodyStyle: typography.bodyStyle,
      );
      final slices = ArticleFlowLayoutEngine.sliceForViewport(
        runs,
        sliceHeight,
      );

      expect(slices.length, greaterThan(1), reason: '长文必须产生多页才能验证欠满度');
      for (var index = 0; index < slices.length - 1; index += 1) {
        final usedHeight = slices[index].fold<double>(
          0,
          (sum, run) => sum + run.measuredHeight,
        );
        final slack = sliceHeight - usedHeight;
        final nextBlockHeight = slices[index + 1].first.measuredHeight;
        expect(
          slack,
          lessThan(nextBlockHeight + 1),
          reason:
              '第 ${index + 1} 页尾部余量 $slack 不得容得下下一内容块 '
              '$nextBlockHeight（GWT-015 页面饱满）',
        );
      }
    });
  });
}
