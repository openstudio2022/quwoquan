import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_document_models.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/widgets/article_content_block_renderer.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

void main() {
  testWidgets('titleStyle 为 none 时分页结果不会再注入标题片段', (tester) async {
    late BuildContext context;
    await tester.pumpWidget(
      MaterialApp(
        home: Builder(
          builder: (ctx) {
            context = ctx;
            return const SizedBox(width: 430, height: 900);
          },
        ),
      ),
    );

    final pages = resolvePaginatedArticlePages(
      context: context,
      constraints: const BoxConstraints.tightFor(width: 430, height: 900),
      document: ArticleDocumentData(
        titleStyle: ArticleDocumentTitleStyle.none,
        nodes: const <ArticleDocumentNode>[
          ArticleDocumentNode(
            id: 'title',
            type: ArticleDocumentNodeType.documentTitle,
            text: '这段标题应当被隐藏',
          ),
          ArticleDocumentNode(
            id: 'p1',
            type: ArticleDocumentNodeType.paragraph,
            text: '正文仍应正常参与分页。',
          ),
        ],
      ),
      template: ArticleTemplatePreset.journal,
      fontPreset: ArticleFontPreset.clean,
    );

    expect(pages, isNotEmpty);
    expect(pages.every((page) => page.title.trim().isEmpty), isTrue);
    expect(pages.any((page) => page.body.contains('正文仍应正常参与分页')), isTrue);
  });

  testWidgets('标题到首图用章节间距，图到图用自然段间距', (tester) async {
    await tester.binding.setSurfaceSize(const Size(320, 1400));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    const page = ArticlePageData(
      id: 'spacing_page',
      fragments: <ArticleLayoutFragment>[
        ArticleLayoutFragment(
          id: 'title_fragment',
          kind: ArticleLayoutFragmentKind.title,
          text: '主标题',
        ),
        ArticleLayoutFragment(
          id: 'figure_a',
          kind: ArticleLayoutFragmentKind.fullWidthImage,
          asset: ArticleDocumentAsset(
            id: 'asset_a',
            offset: 0,
            imageUrl: 'https://example.com/a.jpg',
          ),
        ),
        ArticleLayoutFragment(
          id: 'figure_b',
          kind: ArticleLayoutFragmentKind.fullWidthImage,
          asset: ArticleDocumentAsset(
            id: 'asset_b',
            offset: 1,
            imageUrl: 'https://example.com/b.jpg',
          ),
        ),
      ],
    );

    await tester.pumpWidget(
      const MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 900,
              child: ArticlePageReadOnlyView(
                page: page,
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final titleRect = tester.getRect(find.text('主标题'));
    final imageFinder = find.byType(ArticleAdaptiveImage);
    final imageRects =
        imageFinder
            .evaluate()
            .map((element) {
              final renderObject = element.renderObject! as RenderBox;
              return renderObject.localToGlobal(Offset.zero) &
                  renderObject.size;
            })
            .toList(growable: false)
          ..sort((left, right) => left.top.compareTo(right.top));

    expect(imageRects.length, 2);
    expect(
      imageRects.first.top - titleRect.bottom,
      greaterThan(articleParagraphSpacing()),
    );
    expect(
      imageRects[1].top - imageRects.first.bottom,
      greaterThanOrEqualTo(articleParagraphSpacing() - 0.5),
    );
  });

  testWidgets(
    'legacy page without fragments will normalize to unified read-only fragments',
    (tester) async {
      const page = ArticlePageData(
        id: 'legacy_page',
        title: '旧分页标题',
        body: '这是一段旧分页正文，用于验证只读页会在渲染前规范化为统一 fragments。',
        imageUrl: 'https://example.com/legacy.jpg',
        imageLayout: 'wrapLeft',
        caption: '旧说明',
        contentBlocks: <ArticleDocumentBlock>[
          ArticleDocumentBlock(
            id: 'h2_1',
            type: ArticleDocumentBlockType.heading2,
            text: '小节标题',
          ),
        ],
      );

      await tester.pumpWidget(
        const MaterialApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: SizedBox(
                width: 320,
                height: 1200,
                child: ArticlePageReadOnlyView(
                  page: page,
                  template: ArticleTemplatePreset.gentle,
                  fontPreset: ArticleFontPreset.clean,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('旧分页标题'), findsOneWidget);
      expect(find.text('小节标题'), findsOneWidget);
      expect(find.text('旧说明'), findsOneWidget);
      final caption = tester.widget<Text>(find.text('旧说明'));
      expect(caption.textAlign, TextAlign.center);
      expect(find.textContaining('这是一段旧分页正文'), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'book deck uses stage curl navigation instead of plain PageView',
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

      expect(find.byType(PageView), findsNothing);

      await tester.dragFrom(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
        const Offset(-260, -40),
      );
      await tester.pumpAndSettle();
      expect(find.text('第二页正文'), findsOneWidget);

      await tester.dragFrom(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
        const Offset(260, -40),
      );
      await tester.pumpAndSettle();
      expect(find.text('第一页正文'), findsOneWidget);
    },
  );

  testWidgets('book deck uses landscape spread on wide stage', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1400, 900));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
    ];

    await tester.pumpWidget(
      const MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 1400,
              height: 900,
              child: ArticleReadOnlyBookDeck(
                pages: pages,
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

    expect(find.text('第一页正文'), findsOneWidget);
    expect(find.text('第二页正文'), findsOneWidget);
    expect(find.text('第三页正文'), findsNothing);

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-420, -20),
    );
    await tester.pumpAndSettle();

    expect(find.text('第三页正文'), findsOneWidget);
  });

  testWidgets('book deck aborts curl and snaps back before midpoint', (
    tester,
  ) async {
    ArticleReaderPageCurlAbort? aborted;
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 900,
              child: ArticleReadOnlyBookDeck(
                pages: pages,
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                metrics: const ArticleCanvasMetrics(
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
                onPageCurlAborted: (event) => aborted = event,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final hotzone = find.byKey(TestKeys.articlePageCurlHotzoneBottomRight);
    final gesture = await tester.startGesture(
      tester.getBottomRight(hotzone) + const Offset(-6, -6),
    );
    await tester.pump(const Duration(milliseconds: 320));
    await gesture.moveBy(const Offset(-80, -10));
    await gesture.up();
    await tester.pumpAndSettle();

    expect(find.text('第二页正文'), findsNothing);
    expect(aborted, isNotNull);
    expect(aborted!.corner, equals('bottom_right'));
    expect(aborted!.progress, greaterThan(0));
    expect(aborted!.direction, equals('forward'));
  });

  testWidgets(
    'book deck keeps the current page stable during an in-flight curl',
    (tester) async {
      final commits = <ArticleReaderPageFlipCommit>[];
      const pages = <ArticlePageData>[
        ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
        ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: SizedBox(
                width: 430,
                height: 900,
                child: ArticleReadOnlyBookDeck(
                  pages: pages,
                  template: ArticleTemplatePreset.journal,
                  fontPreset: ArticleFontPreset.clean,
                  metrics: const ArticleCanvasMetrics(
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
                  onPageFlipCommitted: commits.add,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final gesture = await tester.startGesture(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
      );
      await tester.pump(const Duration(milliseconds: 120));
      await gesture.moveBy(const Offset(-130, -12));
      await tester.pump(const Duration(milliseconds: 80));

      expect(commits, isEmpty);

      await gesture.up();
      await tester.pumpAndSettle();
    },
  );

  testWidgets('book deck commits a deliberate short corner lift', (
    tester,
  ) async {
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
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
    );
    await tester.pump(const Duration(milliseconds: 120));
    await gesture.moveBy(const Offset(-170, -16));
    await tester.pump(const Duration(milliseconds: 80));
    await gesture.up();
    await tester.pumpAndSettle();

    expect(find.text('第二页正文'), findsOneWidget);
  });

  testWidgets('book deck 前翻仍保持 shared forward 可用', (
    tester,
  ) async {
    final commits = <ArticleReaderPageFlipCommit>[];
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 900,
              child: ArticleReadOnlyBookDeck(
                pages: pages,
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                metrics: const ArticleCanvasMetrics(
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
                onPageFlipCommitted: commits.add,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();

    expect(find.text('第二页正文'), findsOneWidget);
    expect(commits, isNotEmpty);
    expect(commits.last.direction, equals('forward'));
    expect(commits.last.fromPage, equals(0));
    expect(commits.last.toPage, equals(1));
  });

  testWidgets('book deck 回翻仍保持 staged curl layer', (tester) async {
      const pages = <ArticlePageData>[
        ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
        ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
        ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
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

      await tester.dragFrom(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
        const Offset(-260, -40),
      );
      await tester.pumpAndSettle();

      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await tester.pump(const Duration(milliseconds: 32));
      await gesture.moveBy(const Offset(88, -18));
      await tester.pump(const Duration(milliseconds: 64));

      expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
      expect(find.byType(PageView), findsNothing);
      expect(find.text('第一页正文'), findsWidgets);
      expect(find.text('第二页正文'), findsWidgets);

      await gesture.up();
      await tester.pumpAndSettle();
    },
  );

  testWidgets(
    'book deck records backward commit after returning to previous page',
    (tester) async {
      final commits = <ArticleReaderPageFlipCommit>[];
      const pages = <ArticlePageData>[
        ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
        ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ];

      await tester.pumpWidget(
        MaterialApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: SizedBox(
                width: 430,
                height: 900,
                child: ArticleReadOnlyBookDeck(
                  pages: pages,
                  template: ArticleTemplatePreset.journal,
                  fontPreset: ArticleFontPreset.clean,
                  metrics: const ArticleCanvasMetrics(
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
                  onPageFlipCommitted: commits.add,
                ),
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      await tester.dragFrom(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
        const Offset(-260, -40),
      );
      await tester.pumpAndSettle();
      expect(find.text('第二页正文'), findsOneWidget);

      await tester.dragFrom(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
        const Offset(260, -40),
      );
      await tester.pumpAndSettle();

      expect(find.text('第一页正文'), findsOneWidget);
      expect(commits, isNotEmpty);
      expect(commits.last.direction, equals('backward'));
      expect(commits.last.fromPage, equals(1));
      expect(commits.last.toPage, equals(0));
    },
  );

  testWidgets(
    'book deck backward drag keeps curl layer active without rigid pageview fallback',
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

      await tester.dragFrom(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
        const Offset(-260, -40),
      );
      await tester.pumpAndSettle();

      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await tester.pump(const Duration(milliseconds: 32));
      await gesture.moveBy(const Offset(88, -18));
      await tester.pump(const Duration(milliseconds: 32));

      expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
      expect(find.byType(PageView), findsNothing);

      await gesture.up();
      await tester.pumpAndSettle();
    },
  );

  testWidgets('book deck 在 maxPageCurlPages 边界仍使用 curl', (tester) async {
    final pages = List<ArticlePageData>.generate(
      ArticleReadOnlyBookDeck.maxPageCurlPages,
      (i) => ArticlePageData(id: 'page_$i', title: '标题$i', body: '正文$i'),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 900,
              child: ArticleReadOnlyBookDeck(
                pages: pages,
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                metrics: const ArticleCanvasMetrics(
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

    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
    expect(find.byKey(TestKeys.articleBookStylePager), findsNothing);
  });

  testWidgets('book deck 超过 maxPageCurlPages 降级为 pager', (tester) async {
    final pages = List<ArticlePageData>.generate(
      ArticleReadOnlyBookDeck.maxPageCurlPages + 1,
      (i) => ArticlePageData(id: 'page_$i', title: '标题$i', body: '正文$i'),
    );

    await tester.pumpWidget(
      MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 900,
              child: ArticleReadOnlyBookDeck(
                pages: pages,
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                metrics: const ArticleCanvasMetrics(
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

    expect(find.byKey(TestKeys.articleBookStylePager), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);
  });

  testWidgets('book deck 在 forceDegradedPager 时使用 PageView', (tester) async {
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
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                forceDegradedPager: true,
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

    expect(find.byKey(TestKeys.articleBookStylePager), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);
  });

  testWidgets('book deck 在 enablePageCurl=false 时使用 PageView', (tester) async {
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
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                enablePageCurl: false,
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

    expect(find.byKey(TestKeys.articleBookStylePager), findsOneWidget);
    expect(find.byKey(TestKeys.articlePageCurlLayer), findsNothing);
  });

  testWidgets('book deck 回翻 abort 记录 backward direction', (tester) async {
    ArticleReaderPageCurlAbort? aborted;
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox(
              width: 430,
              height: 900,
              child: ArticleReadOnlyBookDeck(
                pages: pages,
                template: ArticleTemplatePreset.journal,
                fontPreset: ArticleFontPreset.clean,
                metrics: const ArticleCanvasMetrics(
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
                onPageCurlAborted: (event) => aborted = event,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // 先前翻到第 2 页
    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    expect(find.text('第二页正文'), findsOneWidget);

    // 从左下角热区向右做极小拖拽（回翻方向），不足以 commit
    final hotzone = find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft);
    final gesture2 = await tester.startGesture(
      tester.getBottomLeft(hotzone) + const Offset(6, -6),
    );
    await tester.pump(const Duration(milliseconds: 320));
    await gesture2.moveBy(const Offset(20, -4));
    await gesture2.up();
    await tester.pumpAndSettle();

    // 仍在第 2 页（abort 回弹）
    expect(find.text('第二页正文'), findsOneWidget);
    expect(aborted, isNotNull);
    expect(aborted!.direction, equals('backward'));
    expect(aborted!.corner, contains('left'));
  });

  testWidgets('book deck typography 回翻短拖拽沿 shared path 提交上一页', (tester) async {
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
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

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    expect(find.text('第二页正文'), findsOneWidget);

    final hotzone = find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft);
    final gesture = await tester.startGesture(
      tester.getBottomLeft(hotzone) + const Offset(6, -6),
    );
    await tester.pump(const Duration(milliseconds: 32));
    await gesture.moveBy(const Offset(88, -18));
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
    expect(find.text('第一页正文'), findsWidgets);
    expect(find.text('第二页正文'), findsWidgets);

    await gesture.up();
    await tester.pumpAndSettle();

    expect(find.text('第一页正文'), findsOneWidget);
    expect(find.text('第二页正文'), findsNothing);
  });

  testWidgets('book deck typography 回翻中途保持连续 curl layer 可见', (tester) async {
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
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

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    expect(find.text('第二页正文'), findsOneWidget);

    final hotzone = find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft);
    final gesture = await tester.startGesture(
      tester.getBottomLeft(hotzone) + const Offset(6, -6),
    );
    await tester.pump(const Duration(milliseconds: 32));
    await gesture.moveBy(const Offset(136, -24));
    await tester.pump(const Duration(milliseconds: 32));

    expect(find.byKey(TestKeys.articlePageCurlLayer), findsOneWidget);
    expect(find.text('第一页正文'), findsWidgets);
    expect(find.text('第二页正文'), findsWidgets);

    await gesture.up();
    await tester.pumpAndSettle();
  });

  testWidgets('book deck typography 左侧点击通过 shared backward path 返回上一页', (
    tester,
  ) async {
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
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

    await tester.dragFrom(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
      const Offset(-260, -40),
    );
    await tester.pumpAndSettle();
    expect(find.text('第二页正文'), findsOneWidget);

    final hotzone = find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft);
    await tester.tapAt(tester.getBottomLeft(hotzone) + const Offset(40, -16));
    await tester.pumpAndSettle();

    expect(find.text('第一页正文'), findsOneWidget);
    expect(find.text('第二页正文'), findsNothing);
  });

  testWidgets('book deck 在窄横屏下保持 single，不提前切到 spread', (tester) async {
    await tester.binding.setSurfaceSize(const Size(844, 390));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
    ];

    await tester.pumpWidget(
      const MaterialApp(
        home: CupertinoPageScaffold(
          child: SafeArea(
            child: SizedBox.expand(
              child: ArticleReadOnlyBookDeck(
                pages: pages,
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

    expect(find.text('第一页正文'), findsOneWidget);
    expect(find.text('第二页正文'), findsNothing);
  });

  testWidgets('book deck resize 时保持当前逻辑页可见并在 single/spread 间稳定切换', (
    tester,
  ) async {
    const pages = <ArticlePageData>[
      ArticlePageData(id: 'page_1', title: '第一页标题', body: '第一页正文'),
      ArticlePageData(id: 'page_2', title: '第二页标题', body: '第二页正文'),
      ArticlePageData(id: 'page_3', title: '第三页标题', body: '第三页正文'),
      ArticlePageData(id: 'page_4', title: '第四页标题', body: '第四页正文'),
    ];

    Future<void> pumpDeck(Size size) async {
      await tester.binding.setSurfaceSize(size);
      await tester.pumpWidget(
        const MaterialApp(
          home: CupertinoPageScaffold(
            child: SafeArea(
              child: SizedBox.expand(
                child: ArticleReadOnlyBookDeck(
                  pages: pages,
                  initialPage: 2,
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
    }

    addTearDown(() => tester.binding.setSurfaceSize(null));

    await pumpDeck(const Size(430, 900));
    expect(find.text('第三页正文'), findsOneWidget);
    expect(find.text('第四页正文'), findsNothing);

    await pumpDeck(const Size(1400, 900));
    expect(find.text('第三页正文'), findsOneWidget);
    expect(find.text('第四页正文'), findsOneWidget);

    await pumpDeck(const Size(430, 900));
    expect(find.text('第三页正文'), findsOneWidget);
    expect(find.text('第四页正文'), findsNothing);
  });
}
