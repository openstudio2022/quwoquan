import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_flow_layout_engine.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

void main() {
  const titleStyle = TextStyle(fontSize: 20, height: 1.3);
  const bodyStyle = TextStyle(fontSize: 16, height: 1.6);
  const sourcePage = ArticlePageData(id: 'source_page');

  test(
    'sliceForViewport packs multiple short runs into one slice when height allows',
    () {
      final runs = <ArticleFlowRun>[
        const ArticleFlowRun(
          id: 'a',
          fragment: ArticleLayoutFragment(
            kind: ArticleLayoutFragmentKind.body,
            text: 'x',
            textStyleKey: 'body',
          ),
          measuredHeight: 40,
          sourcePage: sourcePage,
          sourcePageIndex: 0,
        ),
        const ArticleFlowRun(
          id: 'b',
          fragment: ArticleLayoutFragment(
            kind: ArticleLayoutFragmentKind.body,
            text: 'y',
            textStyleKey: 'body',
          ),
          measuredHeight: 40,
          sourcePage: sourcePage,
          sourcePageIndex: 0,
        ),
        const ArticleFlowRun(
          id: 'c',
          fragment: ArticleLayoutFragment(
            kind: ArticleLayoutFragmentKind.body,
            text: 'z',
            textStyleKey: 'body',
          ),
          measuredHeight: 40,
          sourcePage: sourcePage,
          sourcePageIndex: 0,
        ),
      ];
      final slices = ArticleFlowLayoutEngine.sliceForViewport(
        runs,
        200,
        runGap: AppSpacing.intraGroupSm,
      );
      expect(slices.length, 1);
      expect(slices.first.length, 3);
    },
  );

  test('computeRuns does not emit one run per image by count alone', () {
    final doc = ArticleDocumentData(
      body: 'intro',
      assets: <ArticleDocumentAsset>[
        ArticleDocumentAsset(id: 'i1', offset: 5, imageUrl: '/a.jpg'),
        ArticleDocumentAsset(id: 'i2', offset: 5, imageUrl: '/b.jpg'),
      ],
    );
    const metrics = ArticleCanvasMetrics(
      aspectRatio: 0.72,
      outerPadding: EdgeInsets.zero,
      contentPadding: EdgeInsets.all(12),
      headerReservedHeight: 0,
      footerReservedHeight: 0,
      wrapImageGap: 8,
      wrapImageMaxWidth: 132,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: 8,
    );
    final runs = ArticleFlowLayoutEngine.computeRuns(
      document: doc,
      metrics: metrics,
      stageWidth: 400,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
    );
    final fullWidthRuns = runs
        .where(
          (ArticleFlowRun r) =>
              r.fragment.kind == ArticleLayoutFragmentKind.fullWidthImage,
        )
        .length;
    expect(fullWidthRuns, 2);
    expect(runs.length < fullWidthRuns * 3, isTrue);
  });

  test('buildPageSlicesForViewport returns unified slice ids and bindings', () {
    final doc = ArticleDocumentData(
      title: '统一分页标题',
      body: '第一页正文\n第二页正文\n第三页正文',
      assets: const <ArticleDocumentAsset>[
        ArticleDocumentAsset(id: 'asset_1', offset: 5, imageUrl: '/demo.jpg'),
      ],
    );
    const metrics = ArticleCanvasMetrics(
      aspectRatio: 0.72,
      outerPadding: EdgeInsets.zero,
      contentPadding: EdgeInsets.all(12),
      headerReservedHeight: 0,
      footerReservedHeight: 0,
      wrapImageGap: 8,
      wrapImageMaxWidth: 132,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: 8,
    );
    final pages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
      document: doc,
      metrics: metrics,
      stageWidth: 400,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      viewportSliceHeight: 180,
    );

    expect(pages, isNotEmpty);
    expect(pages.every((page) => page.id.startsWith('slice_')), isTrue);
    expect(pages.map((page) => page.id).toSet().length, pages.length);
    expect(pages.any((page) => page.binding?.bodyRange != null), isTrue);
    expect(
      pages.any(
        (page) => page.binding?.resolvedAssetIds.contains('asset_1') == true,
      ),
      isTrue,
    );
  });

  test('wrap fragments keep independent body bindings', () {
    final doc = ArticleDocumentData(
      title: '标题',
      body: '第一段第二段',
      assets: const <ArticleDocumentAsset>[
        ArticleDocumentAsset(
          id: 'asset_a',
          offset: 0,
          imageUrl: '/a.jpg',
          imageLayout: 'wrapLeft',
        ),
        ArticleDocumentAsset(
          id: 'asset_b',
          offset: 2,
          imageUrl: '/b.jpg',
          imageLayout: 'wrapLeft',
        ),
      ],
    );
    final anchor0 = doc.assets[0].offset;
    final anchor1 = doc.assets[1].offset;
    final bodyLen = doc.body.length;
    const metrics = ArticleCanvasMetrics(
      aspectRatio: 0.72,
      outerPadding: EdgeInsets.zero,
      contentPadding: EdgeInsets.all(12),
      headerReservedHeight: 0,
      footerReservedHeight: 0,
      wrapImageGap: 8,
      wrapImageMaxWidth: 132,
      fullWidthImageAspectRatio: 4 / 3,
      journalImageAspectRatio: 1,
      inlineImageSpacing: 8,
    );
    final pages = ArticleFlowLayoutEngine.buildPageSlicesForViewport(
      document: doc,
      metrics: metrics,
      stageWidth: 420,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      viewportSliceHeight: 400,
    );

    final wrapFragments = pages
        .expand((page) => page.fragments)
        .where(
          (fragment) => fragment.kind == ArticleLayoutFragmentKind.wrapContent,
        )
        .toList(growable: false);
    expect(wrapFragments, hasLength(2));
    expect(wrapFragments[0].binding?.bodyRange?.start, anchor0);
    expect(wrapFragments[0].binding?.bodyRange?.end, anchor1);
    expect(
      wrapFragments[0].text,
      doc.body.substring(anchor0, anchor1).trimRight(),
    );
    expect(wrapFragments[1].binding?.bodyRange?.start, anchor1);
    expect(wrapFragments[1].binding?.bodyRange?.end, bodyLen);
    expect(
      wrapFragments[1].text,
      doc.body.substring(anchor1, bodyLen).trimRight(),
    );
  });
}
