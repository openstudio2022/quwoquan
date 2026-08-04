import 'package:flutter/painting.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/content/content/post/domain/article_document_models.dart';
import 'package:quwoquan_app/content/content/post/presentation/article_flow_layout_engine.dart';
import 'package:quwoquan_app/content/content/post/domain/article_presentation_models.dart';

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
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'paragraph_0',
          type: ArticleDocumentNodeType.paragraph,
          text: 'intro',
        ),
        ArticleDocumentNode(
          id: 'i1',
          type: ArticleDocumentNodeType.figure,
          assetId: 'i1',
          imageUrl: '/a.jpg',
        ),
        ArticleDocumentNode(
          id: 'i2',
          type: ArticleDocumentNodeType.figure,
          assetId: 'i2',
          imageUrl: '/b.jpg',
        ),
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
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: '统一分页标题',
        ),
        ArticleDocumentNode(
          id: 'paragraph_0',
          type: ArticleDocumentNodeType.paragraph,
          text: '第一页正文',
        ),
        ArticleDocumentNode(
          id: 'asset_1',
          type: ArticleDocumentNodeType.figure,
          assetId: 'asset_1',
          imageUrl: '/demo.jpg',
        ),
        ArticleDocumentNode(
          id: 'paragraph_1',
          type: ArticleDocumentNodeType.paragraph,
          text: '第二页正文\n第三页正文',
        ),
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

  test('first page keeps title with body when there is no cover', () {
    final doc = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: '首屏标题',
        ),
        ArticleDocumentNode(
          id: 'paragraph_0',
          type: ArticleDocumentNodeType.paragraph,
          text: '首段正文必须和标题同页。\n\n第二段正文进入连续分页。',
        ),
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
      stageWidth: 420,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      viewportSliceHeight: 220,
    );

    expect(pages.first.title, '首屏标题');
    expect(pages.first.body, contains('首段正文'));
    expect(
      pages.first.fragments.map((fragment) => fragment.kind),
      containsAll(<ArticleLayoutFragmentKind>[
        ArticleLayoutFragmentKind.title,
        ArticleLayoutFragmentKind.body,
      ]),
    );
  });

  test('first page keeps title cover and first paragraph together', () {
    final doc = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: '有封面标题',
        ),
        ArticleDocumentNode(
          id: 'cover',
          type: ArticleDocumentNodeType.figure,
          assetId: 'cover',
          imageUrl: '/cover.jpg',
        ),
        ArticleDocumentNode(
          id: 'paragraph_0',
          type: ArticleDocumentNodeType.paragraph,
          text: '有封面时首段正文仍应出现在第一页。\n\n后续正文继续分页。',
        ),
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
      stageWidth: 420,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      viewportSliceHeight: 420,
    );

    expect(pages.first.title, '有封面标题');
    expect(pages.first.body, contains('有封面时首段正文'));
    expect(
      pages.first.fragments.map((fragment) => fragment.kind),
      containsAll(<ArticleLayoutFragmentKind>[
        ArticleLayoutFragmentKind.title,
        ArticleLayoutFragmentKind.fullWidthImage,
        ArticleLayoutFragmentKind.body,
      ]),
    );
  });

  test('long paragraph is split into multiple body runs', () {
    final doc = ArticleDocumentData(
      nodes: <ArticleDocumentNode>[
        const ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: '连续分页',
        ),
        ArticleDocumentNode(
          id: 'paragraph_0',
          type: ArticleDocumentNodeType.paragraph,
          text: List<String>.generate(
            80,
            (index) => '第$index句正文用于验证单个超长段落也能继续分页。',
          ).join(),
        ),
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
      stageWidth: 360,
      titleStyle: titleStyle,
      bodyStyle: bodyStyle,
      viewportSliceHeight: 220,
    );

    final bodyPages = pages.where((page) => page.body.trim().isNotEmpty);
    expect(bodyPages.length, greaterThan(1));
    expect(pages.first.title, '连续分页');
    expect(pages.first.body.trim(), isNotEmpty);
  });

  test('wrap fragments keep independent body bindings', () {
    final doc = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'document_title',
          type: ArticleDocumentNodeType.documentTitle,
          text: '标题',
        ),
        ArticleDocumentNode(
          id: 'asset_a',
          type: ArticleDocumentNodeType.figure,
          assetId: 'asset_a',
          imageUrl: '/a.jpg',
          imageLayout: 'wrapLeft',
        ),
        ArticleDocumentNode(
          id: 'paragraph_0',
          type: ArticleDocumentNodeType.paragraph,
          text: '第一',
        ),
        ArticleDocumentNode(
          id: 'asset_b',
          type: ArticleDocumentNodeType.figure,
          assetId: 'asset_b',
          imageUrl: '/b.jpg',
          imageLayout: 'wrapLeft',
        ),
        ArticleDocumentNode(
          id: 'paragraph_1',
          type: ArticleDocumentNodeType.paragraph,
          text: '段第二段',
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
    // 投影 body 在相邻段落节点之间会插入 `\n`，锚点可能落在换行上；wrap 显式
    // leadingText 对应段落纯文本，故 fragment.text 与 substring 相比无段前换行。
    expect(
      wrapFragments[0].text,
      doc.body.substring(anchor0, anchor1).trimRight().trimLeft(),
    );
    expect(wrapFragments[1].binding?.bodyRange?.start, anchor1);
    expect(wrapFragments[1].binding?.bodyRange?.end, bodyLen);
    expect(
      wrapFragments[1].text,
      doc.body.substring(anchor1, bodyLen).trimRight().trimLeft(),
    );
  });
}
