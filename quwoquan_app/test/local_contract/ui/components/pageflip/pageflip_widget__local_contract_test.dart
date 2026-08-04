import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import '../../../../support/pageflip/pageflip.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_reader/content/article_reader_page_surfaces.dart';
import 'package:quwoquan_app/content/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_stage_widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_pixel_probe.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/components/pageflip/controller.dart';
import 'package:quwoquan_app/components/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/components/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/components/pageflip/types.dart';

void main() {
  testWidgets('PageflipWidget pumps and renders the current page', (
    WidgetTester tester,
  ) async {
    final engine = PageflipEngine(pageCount: 4, initialPage: 1);

    await tester.pumpWidget(
      MaterialApp(
        home: SizedBox.expand(
          child: PageflipWidget(
            engine: engine,
            pageBuilder: (context, pageIndex) =>
                Center(child: Text('page-$pageIndex')),
          ),
        ),
      ),
    );

    await tester.pumpAndSettle();
    expect(find.text('page-1'), findsOneWidget);
  });

  testWidgets(
    'PageflipWidget suppresses the static page once long-form curl is active',
    (WidgetTester tester) async {
      final engine = PageflipEngine(pageCount: 4, initialPage: 1);

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();
      final gesture = await tester.startGesture(const Offset(700, 300));
      await gesture.moveBy(const Offset(-180, 0));
      await tester.pump();
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('pageflip_curl_renderer')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('pageflip_fold_line')), findsNothing);
      expect(
        find.byKey(const ValueKey('pageflip_static_page_1')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('pageflip_static_page_2')),
        findsNothing,
      );
      final renderer = tester.widget<ArticlePageCurlRenderer>(
        find.byType(ArticlePageCurlRenderer),
      );
      expect(renderer.scene.direction, StPageFlipDirection.forward);
      expect(renderer.scene.renderConfig.enableBottomProjection, isTrue);
      expect(renderer.scene.renderConfig.enableSpineAmbient, isTrue);
      expect(renderer.scene.renderConfig.enableBackPaperWash, isTrue);
      expect(renderer.scene.renderConfig.enableBackCreaseOcclusion, isTrue);
    },
  );

  testWidgets(
    'PageflipWidget removes the duplicated static layer after mesh activation',
    (WidgetTester tester) async {
      final engine = PageflipEngine(pageCount: 4, initialPage: 1);

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();
      expect(
        find.byKey(const ValueKey('pageflip_static_page_1')),
        findsOneWidget,
      );

      final gesture = await tester.startGesture(const Offset(700, 300));
      await gesture.moveBy(const Offset(-120, 0));
      await tester.pump();
      await tester.pumpAndSettle();

      expect(
        find.byKey(const ValueKey('pageflip_static_page_1')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('pageflip_static_page_2')),
        findsNothing,
      );
      expect(
        find.byKey(const ValueKey('pageflip_curl_renderer')),
        findsOneWidget,
      );
      expect(find.byKey(const ValueKey('pageflip_fold_line')), findsNothing);
    },
  );

  testWidgets(
    'PageflipWidget keeps the current page visible until forward textures are ready',
    (WidgetTester tester) async {
      final engine = PageflipEngine(pageCount: 4, initialPage: 1);
      final debugStates = <PageflipWidgetDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              onDebugStateChanged: debugStates.add,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pump();
      final gesture = await tester.startGesture(const Offset(700, 300));
      await gesture.moveBy(const Offset(-60, 0));
      await tester.pump();

      if (find
          .byKey(const ValueKey('pageflip_curl_renderer'))
          .evaluate()
          .isEmpty) {
        final waitingState = debugStates.last;
        expect(
          find.byKey(const ValueKey('pageflip_static_page_1')),
          findsOneWidget,
        );
        expect(
          find.byKey(const ValueKey('pageflip_static_page_2')),
          findsNothing,
        );
        expect(waitingState.meshReady, isFalse);
        expect(waitingState.sessionHasBundle, isFalse);
        expect(waitingState.missingSnapshotIndices, isNotEmpty);
      }

      await gesture.up();
    },
  );

  testWidgets(
    'PageflipWidget reports the covered/current page and forward bindings in debug state',
    (WidgetTester tester) async {
      final engine = PageflipEngine(pageCount: 5, initialPage: 3);
      final debugStates = <PageflipWidgetDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              onDebugStateChanged: debugStates.add,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();
      final gesture = await tester.startGesture(const Offset(700, 300));
      await gesture.moveBy(const Offset(-120, 0));
      await tester.pump();
      await tester.pumpAndSettle();

      final interactiveState = debugStates.lastWhere(
        (state) => state.turningPageIndex != null,
      );
      expect(interactiveState.currentPageIndex, 3);
      expect(interactiveState.coveredPageIndex, 3);
      expect(interactiveState.staticPageIndex, 3);
      expect(interactiveState.underlayPageIndex, 4);
      expect(interactiveState.requestedRectoPageIndex, 3);
      expect(interactiveState.requestedVersoPageIndex, 3);
      expect(interactiveState.requestedBottomPageIndex, 4);
      expect(interactiveState.bottomClipBounds, isNotNull);
      expect(interactiveState.frontBounds, isNotNull);
      expect(interactiveState.backBounds, isNotNull);

      await gesture.up();
    },
  );

  testWidgets(
    'PageflipWidget reports previous-leaf and covered-current pages in backward debug state',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final engine = PageflipEngine(pageCount: 5, initialPage: 3);
      final debugStates = <PageflipWidgetDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              onDebugStateChanged: debugStates.add,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await gesture.moveBy(const Offset(260, -40));
      await tester.pump();

      final interactiveState = debugStates.lastWhere(
        (state) => state.turningPageIndex != null,
      );
      expect(interactiveState.currentPageIndex, 3);
      expect(interactiveState.coveredPageIndex, 3);
      expect(interactiveState.staticPageIndex, 3);
      expect(interactiveState.turningPageIndex, 2);
      expect(interactiveState.underlayPageIndex, 3);
      expect(interactiveState.requestedRectoPageIndex, 2);
      expect(interactiveState.requestedVersoPageIndex, 2);
      expect(interactiveState.requestedBottomPageIndex, 3);

      await gesture.up();
    },
  );

  testWidgets(
    'PageflipWidget backward interaction reaches the isolated mesh mainline',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final engine = PageflipEngine(pageCount: 5, initialPage: 3);
      final debugStates = <PageflipWidgetDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              onDebugStateChanged: debugStates.add,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();
      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await gesture.moveBy(const Offset(260, -40));
      for (var i = 0; i < 12; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      final interactiveState = debugStates.lastWhere(
        (state) => state.turningPageIndex != null && state.renderSceneReady,
      );
      expect(interactiveState.renderDirection, PageflipDirection.back);
      expect(interactiveState.currentPageIndex, 3);
      expect(interactiveState.coveredPageIndex, 3);
      expect(interactiveState.turningPageIndex, 2);
      expect(interactiveState.underlayPageIndex, 3);
      expect(interactiveState.requestedRectoPageIndex, 2);
      expect(interactiveState.requestedVersoPageIndex, 2);
      expect(interactiveState.requestedBottomPageIndex, 3);
      expect(interactiveState.activeRectoPageIndex, 2);
      expect(interactiveState.activeVersoPageIndex, 2);
      expect(interactiveState.activeBottomPageIndex, 3);
      expect(interactiveState.frontBounds, isNotNull);
      expect(interactiveState.backBounds, isNotNull);
      expect(find.byType(ArticlePageCurlRenderer), findsOneWidget);

      await gesture.up();
    },
  );

  testWidgets(
    'PageflipWidget can commit a backward turn from the visible left half',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final engine = PageflipEngine(pageCount: 5, initialPage: 3);
      final changedPages = <int>[];

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.expand(
            child: PageflipWidget(
              engine: engine,
              onPageChanged: changedPages.add,
              pageBuilder: (context, pageIndex) => ColoredBox(
                color: pageIndex.isEven ? Colors.amber : Colors.blue,
                child: Center(child: Text('page-$pageIndex')),
              ),
            ),
          ),
        ),
      );

      await tester.pumpAndSettle();
      final leftHotzone = tester.getCenter(
        find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft),
      );
      final gesture = await tester.startGesture(leftHotzone);
      await gesture.moveBy(const Offset(260, -40));
      await tester.pump();
      await gesture.up();
      await tester.pump();

      expect(changedPages, contains(2));
      expect(engine.currentPageIndex, 2);
    },
  );

  testWidgets(
    'ArticleReadOnlyBookDeck keeps slow backward drag live past the direction split',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(408, 916));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final debugStates = <ArticleReadOnlyBookDebugState>[];
      await tester.pumpWidget(
        MaterialApp(
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
                initialPage: 4,
                coverUrl: '',
                showFooterPageLabel: false,
                onDebugStateChanged: debugStates.add,
                debugPageSurfaceBuilder: _buildProbePageSurface,
                debugBackPageSurfaceBuilder: _buildProbeBackPageSurface,
              );
            },
          ),
        ),
      );
      await tester.pump();
      for (var i = 0; i < 12; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      debugStates.clear();

      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      final samples = <ArticleReadOnlyBookDebugState>[];
      const stepDeltas = <double>[64, 64, 64, 64, 64, 64, 64];
      for (final dx in stepDeltas) {
        await gesture.moveBy(Offset(dx, 0));
        for (var i = 0; i < 4; i += 1) {
          await tester.pump(const Duration(milliseconds: 16));
        }
        final backStates = debugStates
            .where(
              (state) =>
                  state.renderDirection == StPageFlipDirection.back &&
                  state.backwardCompositeMode == 'paperFoldBackwardMainline',
            )
            .toList(growable: false);
        expect(
          backStates,
          isNotEmpty,
          reason:
              'slow BACK drag must keep producing paperFoldBackwardMainline samples.',
        );
        samples.add(backStates.last);
      }

      final coveredWidths = samples
          .map((state) => state.backwardCoveredWidth)
          .whereType<double>()
          .toList(growable: false);
      expect(coveredWidths, hasLength(stepDeltas.length));
      for (var index = 1; index < coveredWidths.length; index += 1) {
        expect(
          coveredWidths[index],
          greaterThanOrEqualTo(coveredWidths[index - 1] - 0.04),
          reason:
              'slow BACK drag must not stall or rewind while the finger remains down.',
        );
      }
      expect(
        coveredWidths.last,
        greaterThan(0.86),
        reason:
            'held slow BACK drag must reach the late page pose before release, '
            'not wait for gesture.up() animation to finish the turn.',
      );

      await gesture.up();
      await tester.pump(const Duration(milliseconds: 16));
      await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
    },
  );

  testWidgets(
    'ArticleReadOnlyBookDeck immersive paper fills the whole content rect',
    (WidgetTester tester) async {
      const stageSize = Size(360, 640);
      await tester.binding.setSurfaceSize(stageSize);
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        MaterialApp(
          home: SizedBox.fromSize(
            size: stageSize,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final baseMetrics = resolveArticleCanvasMetrics(
                  context,
                  constraints,
                  variant: ArticleCanvasVariant.immersive,
                );
                final metrics = ArticleCanvasMetrics(
                  aspectRatio: stageSize.width / stageSize.height,
                  outerPadding: EdgeInsets.zero,
                  contentPadding: baseMetrics.contentPadding,
                  headerReservedHeight: baseMetrics.headerReservedHeight,
                  footerReservedHeight: baseMetrics.footerReservedHeight,
                  wrapImageGap: baseMetrics.wrapImageGap,
                  wrapImageMaxWidth: baseMetrics.wrapImageMaxWidth,
                  fullWidthImageAspectRatio:
                      baseMetrics.fullWidthImageAspectRatio,
                  journalImageAspectRatio: baseMetrics.journalImageAspectRatio,
                  inlineImageSpacing: baseMetrics.inlineImageSpacing,
                );
                return ArticleReadOnlyBookDeck(
                  pages: _diagnosticPages(),
                  template: ArticleTemplatePreset.tech,
                  fontPreset: ArticleFontPreset.classic,
                  metrics: metrics,
                  pagePadding: EdgeInsets.zero,
                  initialPage: 0,
                  coverUrl: '',
                  showFooterPageLabel: false,
                  presentationStyle:
                      ArticleReadOnlyBookDeckPresentationStyle.immersive,
                );
              },
            ),
          ),
        ),
      );
      await tester.pump();
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      final deckRect = tester.getRect(find.byType(ArticleReadOnlyBookDeck));
      final visiblePageRect = tester.getRect(
        find
            .byKey(const ValueKey<String>('article-reader-page-surface-0'))
            .first,
      );
      final shell = tester.widget<ArticlePageShell>(
        find
            .byKey(const ValueKey<String>('article-reader-page-surface-0'))
            .first,
      );

      expect(shell.variant, ArticlePageShellVariant.immersiveEdgeToEdge);
      expect(visiblePageRect.topLeft, deckRect.topLeft);
      expect(visiblePageRect.size.width, closeTo(deckRect.size.width, 0.1));
      expect(visiblePageRect.size.height, closeTo(deckRect.size.height, 0.1));
    },
  );

  testWidgets('PageflipDiagnosticsApp shows long-form baseline content', (
    WidgetTester tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(900, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await tester.pumpWidget(const PageflipDiagnosticsApp());
    await tester.pumpAndSettle();

    expect(find.byType(FittedBox), findsNothing);
    expect(find.byType(ArticleReadOnlyBookDeck), findsOneWidget);
    expect(find.byType(PageflipWidget), findsNothing);
    expect(
      find.byKey(const ValueKey('article_read_only_book_debug_card')),
      findsNothing,
    );
  });

  testWidgets('PageflipWidgetDiagnosticsApp isolates the new component host', (
    WidgetTester tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(900, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(const PageflipWidgetDiagnosticsApp());
    await tester.pumpAndSettle();
    expect(find.byType(PageflipWidget), findsOneWidget);
    expect(find.byType(ArticleReadOnlyBookDeck), findsNothing);
    expect(
      find.byKey(const ValueKey('pageflip_widget_debug_card')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey('pageflip_widget_acceptance_banner')),
      findsOneWidget,
    );
  });

  testWidgets(
    'PageflipWidgetDiagnosticsApp keeps PageflipWidget size stable after debug overlay appears',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(const PageflipWidgetDiagnosticsApp());
      await tester.pump();

      final initialSize = tester.getSize(find.byType(PageflipWidget));
      await tester.pumpAndSettle();

      expect(tester.getSize(find.byType(PageflipWidget)), initialSize);
      expect(
        find.byKey(const ValueKey('pageflip_widget_debug_card')),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'PageflipDiagnosticsApp keeps ArticleReadOnlyBookDeck size stable without debug overlay',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(const PageflipDiagnosticsApp());
      await tester.pump();

      final initialSize = tester.getSize(find.byType(ArticleReadOnlyBookDeck));
      await tester.pumpAndSettle();

      expect(tester.getSize(find.byType(ArticleReadOnlyBookDeck)), initialSize);
      expect(
        find.byKey(const ValueKey('article_read_only_book_debug_card')),
        findsNothing,
      );
    },
  );

  testWidgets(
    'PageflipWidgetDiagnosticsApp backward uses mesh mainline with parity render config',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(const PageflipWidgetDiagnosticsApp());
      await tester.pumpAndSettle();

      final gesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await gesture.moveBy(const Offset(260, -40));
      for (var i = 0; i < 40; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
        if (find.byType(ArticlePageCurlRenderer).evaluate().isNotEmpty) {
          break;
        }
      }

      expect(find.byType(PageflipWidget), findsOneWidget);
      expect(find.byType(ArticleReadOnlyBookDeck), findsNothing);
      expect(find.byType(ArticlePageCurlRenderer), findsOneWidget);

      final renderer = tester.widget<ArticlePageCurlRenderer>(
        find.byType(ArticlePageCurlRenderer),
      );
      expect(renderer.scene.direction, StPageFlipDirection.back);
      expect(renderer.scene.renderConfig.enableBottomProjection, isFalse);
      expect(renderer.scene.renderConfig.enableSpineAmbient, isFalse);
      expect(renderer.scene.renderConfig.enableBackPaperWash, isTrue);
      expect(renderer.scene.renderConfig.enableBackCreaseOcclusion, isTrue);

      await gesture.up();
    },
  );

  testWidgets(
    'PageflipWidget drops stale snapshots when host size changes mid-capture',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      final debugStates = <PageflipWidgetDebugState>[];
      final height = ValueNotifier<double>(1200);
      addTearDown(height.dispose);

      await tester.pumpWidget(
        MaterialApp(
          home: ValueListenableBuilder<double>(
            valueListenable: height,
            builder: (context, currentHeight, _) {
              return Align(
                alignment: Alignment.topCenter,
                child: SizedBox(
                  width: 900,
                  height: currentHeight,
                  child: PageflipWidget(
                    engine: engine,
                    onDebugStateChanged: debugStates.add,
                    pageBuilder: (context, pageIndex) => ColoredBox(
                      color: pageIndex.isEven ? Colors.amber : Colors.blue,
                      child: Center(child: Text('page-$pageIndex')),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      );

      await tester.pump();
      final gesture = await tester.startGesture(const Offset(700, 300));
      await gesture.moveBy(const Offset(-100, 0));
      await tester.pump();

      height.value = 980;
      await tester.pump();

      Object? exception;
      for (var i = 0; i < 50; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
        exception ??= tester.takeException();
      }

      expect(exception, isNull);
      expect(debugStates.any((state) => state.meshReady), isTrue);
      expect(
        debugStates
            .where((state) => state.meshReady)
            .last
            .missingSnapshotIndices,
        isEmpty,
      );

      await gesture.up();
    },
  );

  testWidgets(
    'PageflipDiagnosticsApp forward keeps the frozen closure baseline',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final scenes = <StPageFlipScene>[];
      final debugStates = <ArticleReadOnlyBookDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
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
                debugPageSurfaceBuilder: _buildProbePageSurface,
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      final gesture = await tester.startGesture(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
      );
      await gesture.moveBy(const Offset(-260, -40));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final interactiveState = debugStates.lastWhere(
        (state) => state.renderDirection == StPageFlipDirection.forward,
      );
      expect(
        interactiveState.renderBranch,
        ArticleReadOnlyBookRenderBranch.paperFoldDynamic,
      );
      expect(interactiveState.renderSceneReady, isFalse);
      expect(find.byType(ArticlePageCurlRenderer), findsNothing);
      expect(
        find.byKey(const ValueKey<String>('article_probe_page_2')),
        findsWidgets,
        reason:
            'the forward backside must keep the turning page texture visible',
      );
      await gesture.up();
      await tester.pumpAndSettle();

      expect(
        scenes.any(
          (scene) =>
              scene.state == StPageFlipState.userFold &&
              scene.direction == StPageFlipDirection.forward &&
              scene.currentPageIndex == 2,
        ),
        isTrue,
      );
      final settledScene = scenes.lastWhere(
        (scene) => scene.state == StPageFlipState.read,
      );
      expect(settledScene.currentPageIndex, 3);

      final settledDebug = debugStates.last;
      expect(
        settledDebug.renderBranch,
        ArticleReadOnlyBookRenderBranch.staticStage,
      );
      expect(settledDebug.currentPageIndex, 3);
      expect(settledDebug.turningPageIndex, isNull);
      expect(settledDebug.underlayPageIndex, isNull);
      expect(settledDebug.requestedRectoPageIndex, isNull);
      expect(settledDebug.activeRectoPageIndex, isNull);
    },
  );

  testWidgets('PageflipDiagnosticsApp forward rollback keeps backside texture', (
    WidgetTester tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(900, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final debugStates = <ArticleReadOnlyBookDebugState>[];

    await tester.pumpWidget(
      MaterialApp(
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
              onDebugStateChanged: debugStates.add,
              debugPageSurfaceBuilder: _buildProbePageSurface,
              debugBackPageSurfaceBuilder: _buildProbeBackPageSurface,
            );
          },
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 24; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
      if (debugStates.isNotEmpty &&
          debugStates.last.pendingCaptureIndices.isEmpty) {
        break;
      }
    }
    expect(debugStates.last.pendingCaptureIndices, isEmpty);

    final gesture = await tester.startGesture(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
    );
    await gesture.moveBy(const Offset(-260, -40));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    debugStates.clear();
    await gesture.moveBy(const Offset(195, 28));
    for (var i = 0; i < 3; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final rollbackState = debugStates.lastWhere(
      (state) =>
          state.renderDirection == StPageFlipDirection.forward &&
          state.renderBranch ==
              ArticleReadOnlyBookRenderBranch.paperFoldDynamic,
    );
    expect(rollbackState.pendingCaptureIndices, isEmpty);
    expect(
      find.byKey(const ValueKey<String>('article_probe_back_page_2')),
      findsWidgets,
      reason:
          'forward rollback must not switch the already-visible backside to '
          'the page front just because x-progress crossed a scalar threshold.',
    );

    await gesture.moveBy(const Offset(-190, -20));
    for (var i = 0; i < 3; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(
      find.byKey(const ValueKey<String>('article_probe_back_page_2')),
      findsWidgets,
      reason: 'continuing the forward curl must keep the backside stable.',
    );
    await gesture.up();
  });

  testWidgets(
    'PageflipDiagnosticsApp records forward and backward paperFold baselines',
    (WidgetTester tester) async {
      await tester.binding.setSurfaceSize(const Size(900, 1200));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      final scenes = <StPageFlipScene>[];
      final debugStates = <ArticleReadOnlyBookDebugState>[];

      await tester.pumpWidget(
        MaterialApp(
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
                debugPageSurfaceBuilder: _buildProbePageSurface,
              );
            },
          ),
        ),
      );
      await tester.pumpAndSettle();

      final forwardGesture = await tester.startGesture(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
      );
      await forwardGesture.moveBy(const Offset(-260, -40));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final forwardState = debugStates.lastWhere(
        (state) => state.renderDirection == StPageFlipDirection.forward,
      );
      await forwardGesture.up();
      await tester.pumpAndSettle();

      final backwardGesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );
      await backwardGesture.moveBy(const Offset(260, -40));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final backwardState = debugStates.lastWhere(
        (state) => state.renderDirection == StPageFlipDirection.back,
      );
      await backwardGesture.up();
      await tester.pumpAndSettle();

      expect(
        forwardState.renderBranch,
        ArticleReadOnlyBookRenderBranch.paperFoldDynamic,
      );
      expect(forwardState.renderSceneReady, isFalse);
      expect(
        backwardState.renderBranch,
        ArticleReadOnlyBookRenderBranch.paperFoldDynamic,
      );
      expect(backwardState.renderSceneReady, isTrue);
      expect(backwardState.sessionHasBundle, isTrue);
      expect(backwardState.activeRectoPageIndex, equals(2));
      expect(backwardState.activeVersoPageIndex, equals(2));
      expect(backwardState.activeBottomPageIndex, equals(3));
      expect(backwardState.activeVersoSurfaceKind, equals('back'));
      expect(
        backwardState.backwardVersoDisplayState,
        equals('semanticSnapshot'),
      );
      final backwardDynamicStates = debugStates
          .where(
            (state) =>
                state.renderDirection == StPageFlipDirection.back &&
                state.renderBranch ==
                    ArticleReadOnlyBookRenderBranch.paperFoldDynamic,
          )
          .toList(growable: false);
      final visibleBackStates = backwardDynamicStates.where(
        (state) =>
            state.backwardBackPaintBounds != null &&
            state.backwardBackPaintBounds!.width > 8,
      );
      expect(visibleBackStates, isNotEmpty);
      expect(
        visibleBackStates.map((state) => state.backwardVersoDisplayState),
        everyElement(equals('semanticSnapshot')),
        reason:
            'visible BACK sheet frames must not switch from paperFallback or '
            'waitingForSnapshot to semanticSnapshot during the same turn.',
      );
      expect(backwardState.backwardBottomLayerPageIndex, equals(3));
      expect(backwardState.backwardFlippingLayerPageIndex, equals(2));
      expect(backwardState.backwardBackPaintBounds, isNotNull);
      expect(
        scenes.any(
          (scene) =>
              scene.state == StPageFlipState.userFold &&
              scene.direction == StPageFlipDirection.forward,
        ),
        isTrue,
      );
      expect(
        scenes.any(
          (scene) =>
              scene.state == StPageFlipState.userFold &&
              scene.direction == StPageFlipDirection.back,
        ),
        isTrue,
      );
    },
  );

  testWidgets('PageflipDiagnosticsApp backward closes through paperFold mainline', (
    WidgetTester tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(900, 1200));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final scenes = <StPageFlipScene>[];
    final debugStates = <ArticleReadOnlyBookDebugState>[];

    await tester.pumpWidget(
      MaterialApp(
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
              initialPage: 3,
              coverUrl: '',
              showFooterPageLabel: false,
              onSceneChanged: scenes.add,
              onDebugStateChanged: debugStates.add,
            );
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    final gesture = await tester.startGesture(
      tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
    );
    await gesture.moveBy(const Offset(260, -40));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final interactiveState = debugStates.lastWhere(
      (state) => state.renderDirection == StPageFlipDirection.back,
    );
    expect(interactiveState.currentPageIndex, 3);
    expect(
      interactiveState.renderBranch,
      ArticleReadOnlyBookRenderBranch.paperFoldDynamic,
    );
    expect(interactiveState.renderSceneReady, isTrue);
    expect(interactiveState.sessionHasBundle, isTrue);
    expect(interactiveState.activeRectoPageIndex, equals(2));
    expect(interactiveState.activeVersoPageIndex, equals(2));
    expect(interactiveState.activeBottomPageIndex, equals(3));
    expect(interactiveState.activeVersoSurfaceKind, equals('back'));
    expect(
      interactiveState.backwardVersoDisplayState,
      equals('semanticSnapshot'),
    );
    expect(interactiveState.guideX, isNotNull);
    expect(interactiveState.guideX, greaterThan(0));
    expect(interactiveState.flippingClipBounds, isNotNull);
    expect(interactiveState.flippingAnchor, isNotNull);
    expect(interactiveState.flippingAnchor!.dx.isFinite, isTrue);
    expect(interactiveState.flippingAnchor!.dy.isFinite, isTrue);
    expect(interactiveState.backwardSurfaceOrigin, isNotNull);
    expect(
      interactiveState.backwardSurfaceOrigin!.dx,
      closeTo(interactiveState.flippingAnchor!.dx, 0.001),
    );
    expect(
      interactiveState.backwardSurfaceOrigin!.dy,
      closeTo(interactiveState.flippingAnchor!.dy, 0.001),
    );
    expect(interactiveState.backwardSurfaceViewportRect, isNotNull);
    expect(interactiveState.backwardPivotLocal, isNotNull);
    expect(interactiveState.backwardPivotLocal!.dx, closeTo(0, 0.001));
    expect(interactiveState.backwardPivotLocal!.dy, closeTo(0, 0.001));
    expect(interactiveState.backwardPivotViewport, isNotNull);
    expect(
      interactiveState.backwardPivotViewport!.dy,
      closeTo(interactiveState.backwardSurfaceViewportRect!.top, 0.001),
      reason:
          'the display-projected replay surface pivots at its projected origin',
    );
    expect(interactiveState.backwardClipLocalBounds, isNotNull);
    expect(interactiveState.backwardClipLocalBounds!.width, greaterThan(0));
    expect(interactiveState.backwardClipViewportBounds, isNotNull);
    expect(interactiveState.backwardClipViewportBounds!.width, greaterThan(0));
    expect(interactiveState.bottomAnchor, isNotNull);
    expect(interactiveState.bottomAnchor!.dx.isFinite, isTrue);
    expect(interactiveState.backwardCorner, equals('bottom_left'));
    expect(interactiveState.backwardHinge, isNotNull);
    expect(interactiveState.backwardHinge!.dx, closeTo(0, 0.001));
    expect(interactiveState.backwardHinge!.dy, greaterThan(0));
    expect(interactiveState.backwardSpineTop, isNotNull);
    expect(interactiveState.backwardSpineTop!.dx, closeTo(0, 0.001));
    expect(interactiveState.backwardSpineTop!.dy, closeTo(0, 0.001));
    expect(interactiveState.backwardSpineBottom, isNotNull);
    expect(interactiveState.backwardSpineBottom!.dx, closeTo(0, 0.001));
    expect(interactiveState.backwardSpineBottom!.dy, greaterThan(0));
    expect(interactiveState.backwardSeamX, isNotNull);
    expect(interactiveState.backwardSeamX, greaterThan(0));
    expect(interactiveState.backwardVersoWidth, isNotNull);
    expect(interactiveState.backwardVersoWidth, greaterThan(0));
    expect(interactiveState.backwardRectoWidth, isNotNull);
    expect(interactiveState.backwardRectoWidth, greaterThanOrEqualTo(0));
    expect(interactiveState.backwardBottomStart, isNotNull);
    expect(interactiveState.backwardBottomStart, greaterThan(0));
    expect(interactiveState.backwardPhase, isNotNull);
    expect(interactiveState.backwardPhase, isNot(equals('recto')));
    final frontLayerCount = interactiveState.backwardReplayFrontLayerCount ?? 0;
    expect(frontLayerCount, inInclusiveRange(0, 1));
    expect(interactiveState.backwardMainline, equals('paperFoldBackMainline'));
    expect(interactiveState.backwardFlippingSheetCount, equals(1));
    if (frontLayerCount > 0) {
      expect(interactiveState.backwardFrontSheetId, equals('mainlineLeaf:2'));
    } else {
      expect(interactiveState.backwardFrontSheetId, isNull);
    }
    expect(interactiveState.backwardBackSheetId, equals('mainlineLeaf:2'));
    expect(interactiveState.backwardCurrentLayerPresent, isTrue);
    expect(interactiveState.backwardMultiSliceViolation, isFalse);
    expect(
      interactiveState.backwardReplayBackSurfaceStrategy,
      equals('paperFoldBackMainlineSurface'),
    );
    expect(interactiveState.backwardBottomLayerPageIndex, equals(3));
    expect(interactiveState.backwardFlippingLayerPageIndex, equals(2));
    expect(interactiveState.backwardDynamicOwnedPages, contains(2));
    expect(interactiveState.backwardDynamicOwnedPages, isNot(contains(3)));
    expect(interactiveState.backwardStaticSuppressedPages, isNot(contains(3)));
    expect(interactiveState.backwardReplaySlices, isNotNull);
    expect(
      interactiveState.backwardReplayFrontLayerCount,
      inInclusiveRange(0, 1),
    );
    final hasPaintedBackwardSheet =
        interactiveState.backwardBackPaintBounds != null ||
        interactiveState.backwardFrontPaintBounds != null ||
        interactiveState.backwardFoldSurfacePaintBounds != null;
    expect(hasPaintedBackwardSheet, isTrue);
    expect(interactiveState.backwardBackPaintBounds, isNotNull);
    expect(
      interactiveState.frontBounds,
      equals(interactiveState.backwardFrontPaintBounds),
    );
    expect(
      interactiveState.backBounds,
      equals(interactiveState.backwardBackPaintBounds),
    );
    expect(
      interactiveState.backwardBackPaintBounds!.right,
      greaterThan(0),
      reason:
          'single-page BACK moving sheet must intersect the visible current page; '
          'a fully negative X bound means the previous page was projected to the '
          'wrong side of the spine.',
    );
    // BACK keeps semantic page binding while visual geometry is
    // forward-isomorphic, so the static fold direction matches forward.
    expect(interactiveState.backwardFoldDirection, equals('leftward'));
    expect(
      interactiveState.backwardCompositeMode,
      equals('paperFoldBackwardMainline'),
    );
    expect(
      interactiveState.backwardBackPaintBounds!.left,
      isA<double>(),
      reason: 'back texture bounds come from the native StPageFlip BACK sheet',
    );
    expect(
      interactiveState.backwardBackPixelSurfaceStrategy,
      equals('paperFoldBackMainlineSurface'),
    );
    expect(interactiveState.backwardFrontCoverageRatio, isNotNull);
    expect(
      interactiveState.backwardFrontCoverageRatio,
      greaterThanOrEqualTo(0),
    );
    expect(interactiveState.backwardLeftSpineLocked, isNotNull);
    expect(interactiveState.backwardSimulatorVisualPhase, isNotNull);
    expect(interactiveState.backwardEdgeEnteredPage, isNotNull);
    expect(interactiveState.backwardOverlayClippedToPaper, isTrue);
    expect(interactiveState.backwardBackVertexCount, greaterThanOrEqualTo(3));
    expect(interactiveState.backwardBackPolygonPoints, isNotNull);
    expect(interactiveState.backwardCurrentPolygonPoints, isNotNull);
    if (interactiveState.backwardFrontPaintBounds != null) {
      expect(interactiveState.backwardFrontPaintBounds!.width, greaterThan(0));
    }
    expect(interactiveState.backwardBackPaintBounds!.width, greaterThan(0));
    expect(interactiveState.backwardFoldX, isNotNull);
    expect(interactiveState.backwardPageEdgeX, isNotNull);
    expect(interactiveState.backwardFoldSurfaceEdgeX, isNotNull);
    expect(
      interactiveState.backwardFoldX!,
      isA<double>(),
      reason:
          'direct BACK calculation keeps fold coordinates in page-calculation space',
    );
    expect(
      interactiveState.backwardFoldSurfaceEdgeX!,
      isA<double>(),
      reason:
          'direct BACK calculation reports the fold edge in page-calculation space',
    );
    expect(interactiveState.backwardCoveredWidth, isNotNull);
    expect(interactiveState.backwardRectoCoverage, isNotNull);
    // 倾斜手势下：F / E 来自 direct BACK calculation；
    // foldSurface moving edge 是渲染裁剪后的纸面边界。
    final foldTop = interactiveState.backwardFoldLineTop;
    final foldBottom = interactiveState.backwardFoldLineBottom;
    final edgeTop = interactiveState.backwardPageEdgeLineTop;
    final edgeBottom = interactiveState.backwardPageEdgeLineBottom;
    expect(foldTop, isNotNull);
    expect(foldBottom, isNotNull);
    expect(edgeTop, isNotNull);
    expect(edgeBottom, isNotNull);
    expect(
      foldTop!.dy,
      lessThan(foldBottom!.dy),
      reason: 'foldTop.y < foldBottom.y',
    );
    expect(
      edgeTop!.dy,
      lessThan(edgeBottom!.dy),
      reason: 'edgeTop.y < edgeBottom.y',
    );
    expect(
      (foldTop.dx - foldBottom.dx).abs(),
      greaterThanOrEqualTo(0),
      reason: 'direct BACK reveal line may be vertical in calculation space',
    );
    expect(
      (edgeTop.dx - edgeBottom.dx).abs(),
      greaterThanOrEqualTo(0),
      reason: 'direct BACK edge line stays in calculation space',
    );
    expect(interactiveState.backwardFoldSurfaceEdgeLineTop, isNotNull);
    expect(interactiveState.backwardFoldSurfaceEdgeLineBottom, isNotNull);
    expect(interactiveState.backwardFoldSurfaceEdgeX!.isFinite, isTrue);
    expect(interactiveState.backwardEdgeParallelToFold, isA<bool>());
    expect(interactiveState.backwardSpineTop, isNotNull);
    expect(interactiveState.backwardSpineBottom, isNotNull);
    expect(interactiveState.backwardCurrentResidualBounds, isNotNull);
    expect(
      interactiveState.backwardCurrentResidualBounds!.left,
      greaterThanOrEqualTo(0),
      reason: 'C/current residual must stay in the visible right-page space.',
    );
    expect(interactiveState.backwardPaintedVersoWidth, isNotNull);
    expect(interactiveState.backwardPaintedVersoWidth, greaterThan(0));
    expect(find.byType(ArticlePageCurlRenderer), findsNothing);

    await gesture.up();
    for (var i = 0; i < 40; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    await tester.pumpAndSettle();

    final backwardAnimationStates = debugStates.where(
      (state) =>
          state.renderDirection == StPageFlipDirection.back &&
          state.backwardCompositeMode == 'paperFoldBackwardMainline',
    );
    expect(backwardAnimationStates, isNotEmpty);
    void expectForwardEquivalentBackSurface(
      ArticleReadOnlyBookDebugState state,
      String phase,
    ) {
      final backBounds = state.backwardBackPaintBounds;
      final surface = state.backwardSurfaceViewportRect;
      expect(
        backBounds,
        isNotNull,
        reason: '$phase back surface must be painted',
      );
      expect(surface, isNotNull, reason: '$phase surface bounds are required');
      final minStableWidth = math.max(8.0, surface!.width * 0.02);
      expect(
        backBounds!.width,
        greaterThan(minStableWidth),
        reason:
            '$phase back surface must not collapse into the near-invisible texture strip.',
      );
    }

    expect(
      backwardAnimationStates.any(
        (state) => state.backwardClipViewportBounds != null,
      ),
      isTrue,
    );
    final activeHorizontalBackStates = backwardAnimationStates
        .where(
          (state) =>
              state.backwardClipViewportBounds != null &&
              state.backwardCurrentResidualBounds != null,
        )
        .toList(growable: false);
    expect(activeHorizontalBackStates, isNotEmpty);
    for (final state in activeHorizontalBackStates) {
      expect(
        state.backwardFrontPaintBounds != null ||
            state.backwardBackPaintBounds != null,
        isTrue,
        reason:
            'horizontal BACK drag must never lose both previous-front and '
            'previous-back faces while currentResidual remains visible.',
      );
    }
    final visibleBackStates = backwardAnimationStates
        .where(
          (state) =>
              state.backwardBackPaintBounds != null &&
              state.backwardCurrentResidualBounds != null &&
              state.backwardBackPaintBounds!.width > 8 &&
              state.backwardBackPaintBounds!.overlaps(
                state.backwardCurrentResidualBounds!,
              ),
        )
        .toList(growable: false);
    expect(
      visibleBackStates,
      isNotEmpty,
      reason:
          'the moving BACK leaf must overlap the visible current page in '
          'viewport space; off-page diagnostic geometry is not paint evidence.',
    );
    for (final state in visibleBackStates) {
      final reason =
          'phase=${state.backwardPhase ?? "-"} '
          'display=${state.backwardVersoDisplayState ?? "-"} '
          'bundle=${state.sessionHasBundle}';
      expect(state.renderSceneReady, isTrue, reason: reason);
      expect(state.sessionHasBundle, isTrue, reason: reason);
      expect(state.activeRectoPageIndex, equals(2), reason: reason);
      expect(state.activeVersoPageIndex, equals(2), reason: reason);
      expect(state.activeBottomPageIndex, equals(3), reason: reason);
      expect(state.activeVersoSurfaceKind, equals('back'), reason: reason);
      expect(
        state.backwardVersoDisplayState,
        equals('semanticSnapshot'),
        reason: reason,
      );
    }
    final earlyBackStates = backwardAnimationStates.where(
      (state) =>
          (state.backwardVersoWidth ?? 0) > 0.05 &&
          (state.backwardRectoCoverage ?? 0) <= 0.02,
    );
    final earlyPaintedBackStates = earlyBackStates
        .where((state) => state.backwardBackPaintBounds != null)
        .toList(growable: false);
    expect(
      earlyPaintedBackStates,
      isNotEmpty,
      reason:
          'BACK early phase may keep recto/front hidden, but verso/back must '
          'already be visible as the fold enters from the left.',
    );
    expectForwardEquivalentBackSurface(earlyPaintedBackStates.first, 'early');
    final multiPlaneStates = backwardAnimationStates.where(
      (state) =>
          state.backwardFrontPaintBounds != null &&
          state.backwardBackPaintBounds != null &&
          state.backwardFrontSheetId == state.backwardBackSheetId,
    );
    expect(
      multiPlaneStates,
      isNotEmpty,
      reason:
          'BACK must expose recto and verso as slices of one moving previous '
          'leaf, rather than replacing the current page with a separate front plane.',
    );
    final lateBackStates = backwardAnimationStates.where(
      (state) =>
          (state.backwardRectoCoverage ?? 0) >= 0.72 &&
          state.backwardBackPaintBounds != null,
    );
    expect(
      lateBackStates,
      isNotEmpty,
      reason:
          'BACK late phase must keep a forward-equivalent back surface visible instead of jumping to a front-only state.',
    );
    expectForwardEquivalentBackSurface(lateBackStates.first, 'late');
    for (final state in visibleBackStates) {
      expect(state.backwardSpineTop, isNotNull, reason: 'S/spine is required');
      expect(
        state.backwardFoldLineTop,
        isNotNull,
        reason: 'F/fold line is required',
      );
      expect(
        state.backwardPageEdgeLineTop,
        isNotNull,
        reason: 'E/free edge is required',
      );
      expect(
        state.backwardCurrentResidualBounds,
        isNotNull,
        reason: 'C/current residual is required',
      );
      expect(state.backwardBackPaintBounds, isNotNull);
      expect(state.backwardCurrentResidualBounds, isNotNull);
      expect(state.backwardBackPolygonPoints, isNotNull);
      expect(
        state.backwardBackPaintBounds!.overlaps(
          state.backwardCurrentResidualBounds!,
        ),
        isTrue,
        reason:
            'the moving previous leaf must have positive viewport overlap with '
            'the visible current page; L0 remains an underlay rather than a '
            'replacement surface.',
      );
      expect(
        state.backwardBackVertexCount,
        greaterThanOrEqualTo(3),
        reason:
            'previous-back must remain a real partition polygon; AABB width is '
            'not used as ownership proof for rotated paper.',
      );
      expect(
        state.backwardBackPaintBounds!.left,
        lessThan(state.backwardCurrentResidualBounds!.right),
        reason:
            'rotated verso/back may extend over current by bounds, but it must '
            'remain adjacent to the current-page residual rather than disappear.',
      );
    }
    for (final state in backwardAnimationStates.where(
      (state) =>
          state.backwardFoldX != null &&
          (state.backwardBackPaintBounds != null ||
              (state.backwardBackVertexCount ?? 0) >= 3),
    )) {
      final foldX = state.backwardFoldX;
      final surfaceWidth = state.backwardSurfaceViewportRect?.width;
      expect(foldX, isNotNull);
      expect(surfaceWidth, isNotNull);
      expect(
        foldX!,
        isA<double>(),
        reason:
            'direct BACK animation fold line is reported in calculation space',
      );
      if (state.backwardCurrentResidualBounds != null) {
        expect(
          state.backwardCurrentResidualBounds!.left,
          greaterThanOrEqualTo(0),
        );
      }
      expect(state.backwardClipViewportBounds, isNotNull);
      expect(state.backwardMainline, equals('paperFoldBackMainline'));
      expect(state.backwardFlippingSheetCount, equals(1));
      if (state.backwardFrontPaintBounds != null) {
        expect(state.backwardFrontSheetId, startsWith('mainlineLeaf:'));
        expect(state.backwardBackSheetId, state.backwardFrontSheetId);
        expect(state.frontBounds, equals(state.backwardFrontPaintBounds));
      } else {
        expect(state.backwardBackSheetId, startsWith('mainlineLeaf:'));
      }
      if (state.backwardBackPaintBounds != null) {
        expect(state.backBounds, equals(state.backwardBackPaintBounds));
      }
      expect(state.backwardCurrentLayerPresent, isTrue);
      expect(state.backwardMultiSliceViolation, isFalse);
      if (state.backwardFrontPaintBounds != null) {
        expect(state.backwardFrontPolygonPoints, isNotNull);
      }
      expect(
        state.backwardBackPaintBounds != null ||
            (state.backwardBackVertexCount ?? 0) >= 3,
        isTrue,
      );
    }

    expect(
      scenes.any(
        (scene) =>
            scene.state == StPageFlipState.userFold &&
            scene.direction == StPageFlipDirection.back &&
            scene.currentPageIndex == 3,
      ),
      isTrue,
    );
    final settledScene = scenes.lastWhere(
      (scene) => scene.state == StPageFlipState.read,
    );
    expect(settledScene.currentPageIndex, 2);

    final settledDebug = debugStates.last;
    expect(
      settledDebug.renderBranch,
      ArticleReadOnlyBookRenderBranch.staticStage,
    );
    expect(settledDebug.currentPageIndex, 2);
    expect(settledDebug.turningPageIndex, isNull);
  });

  testWidgets(
    'PageflipDiagnosticsApp backward dynamic exposes Route-B three-layer mainline',
    (WidgetTester tester) async {
      final sample = await _renderBackwardCompositeProbeScene(tester);

      expect(sample.compositeMode, equals('paperFoldBackwardMainline'));
      expect(sample.bottomLayerPageIndex, equals(3));
      expect(sample.flippingLayerPageIndex, equals(2));
      expect(
        sample.backSheetId,
        equals('mainlineLeaf:2'),
        reason:
            'BACK visible backface must stay bound to the previous/flipping leaf, '
            'not the covered current page.',
      );
      expect(
        sample.backPixelSurfaceStrategy,
        equals('paperFoldBackMainlineSurface'),
        reason:
            'Route-B previous-back must stay on the dedicated backside surface '
            'instead of being painted as a front texture.',
      );
      expect(
        sample.baselineKeyVisible,
        isFalse,
        reason:
            'BACK must not expose a full previous-front baseline; previous front '
            'is only allowed through the partitioned moving sheet recto segment.',
      );
      expect(
        sample.foldXSamples,
        isNotEmpty,
        reason: 'BACK 主线必须采集到 backwardFoldX 真相源样本。',
      );
      expect(
        sample.foldXAdvance,
        greaterThan(1),
        reason: 'BACK fold X 必须随手势在 viewport space 内从左向右推进。',
      );
      expect(
        sample.latePoseSurfaceWidth,
        greaterThan(0),
        reason:
            'BACK animation must keep a diagnosed moving sheet surface instead '
            'of collapsing into an unattributed strip.',
      );
      final minStableBackWidth = math.max(
        8.0,
        sample.latePoseSurfaceWidth * 0.02,
      );
      expect(
        sample.latePoseBackWidth,
        greaterThan(minStableBackWidth),
        reason: 'late BACK previous-back band must not collapse into a strip.',
      );
      if (sample.latePoseCount > 0) {
        expect(
          sample.latePoseBackVertexCount,
          greaterThanOrEqualTo(3),
          reason:
              'late BACK previous-back must remain a real partition polygon; '
              'AABB width is not used as ownership proof for rotated paper.',
        );
      }
      expect(
        sample.latePoseCurrentWidth,
        greaterThan(0),
        reason: 'late BACK must keep current residual visible under the fold.',
      );
      expect(sample.latePoseBackVertexCount, greaterThanOrEqualTo(3));
      if (sample.latePoseCount > 0) {
        expect(
          sample.latePoseFrontWidth,
          greaterThan(0),
          reason:
              'when previous front is visible it must be the page-space reveal segment.',
        );
        expect(sample.latePoseFrontSheetId, equals('mainlineLeaf:2'));
        expect(sample.latePoseFrontSheetId, sample.latePoseBackSheetId);
      }
    },
  );

  testWidgets(
    'BACK geometry sweep stays stable across horizontal and angled pullbacks',
    (WidgetTester tester) async {
      const corners = <ArticlePageCurlCorner>[
        ArticlePageCurlCorner.topLeft,
        ArticlePageCurlCorner.bottomLeft,
      ];
      const angleDegrees = <double>[0, 5, 10, 20, 30, 45, 60];
      const depths = <double>[60, 120, 180];
      final failures = <String>[];

      for (final corner in corners) {
        for (final angle in angleDegrees) {
          for (final depth in depths) {
            final sample = await _renderBackwardGeometrySweepSample(
              tester,
              corner: corner,
              angleDegrees: angle,
              depth: depth,
            );
            if (sample.failureReason != BackwardGeometryFailureReason.none) {
              failures.add(sample.describe());
              continue;
            }
            expect(sample.backWidth, greaterThan(0), reason: sample.describe());
            expect(
              sample.currentWidth,
              greaterThan(0),
              reason: sample.describe(),
            );
            expect(sample.renderSceneReady, isTrue, reason: sample.describe());
            expect(sample.sessionHasBundle, isTrue, reason: sample.describe());
            expect(
              sample.activeRectoPageIndex,
              equals(2),
              reason: sample.describe(),
            );
            expect(
              sample.activeVersoPageIndex,
              equals(2),
              reason: sample.describe(),
            );
            expect(
              sample.activeBottomPageIndex,
              equals(3),
              reason: sample.describe(),
            );
            expect(
              sample.activeVersoSurfaceKind,
              equals('back'),
              reason: sample.describe(),
            );
            expect(
              sample.versoDisplayState,
              equals('semanticSnapshot'),
              reason: sample.describe(),
            );
          }
        }
      }

      expect(
        failures,
        isEmpty,
        reason: failures.isEmpty
            ? null
            : 'geometry sweep failures:\n${failures.join('\n')}',
      );
    },
  );

  testWidgets(
    'BACK continuous gesture stays stable when angled drag flattens to horizontal',
    (WidgetTester tester) async {
      final errors = <FlutterErrorDetails>[];
      final previousOnError = FlutterError.onError;
      FlutterError.onError = (details) {
        errors.add(details);
        previousOnError?.call(details);
      };
      final samples = await _collectBackwardAngleToHorizontalSamples(tester)
          .whenComplete(() {
            FlutterError.onError = previousOnError;
          });
      expect(samples.length, greaterThanOrEqualTo(4));
      expect(
        errors,
        isEmpty,
        reason:
            'angled -> horizontal -> opposite-angle BACK replay must not red-screen in paint.',
      );

      _expectSourceBoundsTransitionIsContinuous(
        samples,
        label: 'sheetPaintedUnion',
        maxEdgeDelta: 130,
      );
      _expectSourceBoundsTransitionIsContinuous(
        samples,
        label: 'sheetVersoBack',
        maxEdgeDelta: 130,
      );
    },
  );

  testWidgets('BACK middle pose paints current with recto and verso on one sheet', (
    WidgetTester tester,
  ) async {
    final samples = <_BackwardVersoTextureProbeSample>[];
    for (final dragSteps in <List<Offset>>[
      const <Offset>[Offset(36, -8), Offset(360, -36)],
      List<Offset>.filled(4, const Offset(64, -8)),
      List<Offset>.filled(4, const Offset(64, -16)),
      List<Offset>.filled(4, const Offset(64, -32)),
      List<Offset>.filled(3, const Offset(64, 0)),
      List<Offset>.filled(4, const Offset(64, 0)),
      List<Offset>.filled(5, const Offset(64, 0)),
    ]) {
      samples.add(
        await _renderBackwardVersoTextureProbeScene(
          tester,
          surfaceSize: const Size(408, 916),
          backwardDragSteps: dragSteps,
        ),
      );
    }

    final qualifyingSamples = samples
        .where((sample) {
          final sources = <String, BackwardPaintSourceDiagnostic>{
            for (final source in sample.paintSources) source.label: source,
          };
          final recto = sources['sheetRectoFront'];
          final verso = sources['sheetVersoBack'];
          final current = sources['staticCurrentFront'];
          final rectoBounds = recto?.viewportBounds;
          final currentBounds = current?.viewportBounds;
          final rectoCounts =
              sample.framebufferColorCountsBySource['sheetRectoFront'] ??
              const <_ProbeColor, int>{};
          final versoCounts =
              sample.framebufferColorCountsBySource['sheetVersoBack'] ??
              const <_ProbeColor, int>{};
          final currentCounts =
              sample.framebufferColorCountsBySource['staticCurrentFront'] ??
              const <_ProbeColor, int>{};
          return recto?.pageIndex == 2 &&
              verso?.pageIndex == 2 &&
              current?.pageIndex == 3 &&
              recto?.surfaceKind == 'front' &&
              verso?.surfaceKind == 'back' &&
              rectoBounds != null &&
              currentBounds != null &&
              rectoBounds.intersect(currentBounds).width > 1 &&
              rectoBounds.intersect(currentBounds).height > 1 &&
              (rectoCounts[_ProbeColor.red] ?? 0) > 0 &&
              _semanticBackVisiblePixels(versoCounts) > 0 &&
              (currentCounts[_ProbeColor.green] ?? 0) > 0;
        })
        .toList(growable: false);
    final sourceDiagnostics = samples
        .map(
          (sample) => sample.paintSources
              .map((source) => '${source.label}:${source.viewportBounds}')
              .join(','),
        )
        .join(' | ');

    expect(
      qualifyingSamples,
      isNotEmpty,
      reason:
          'a late portrait BACK frame must paint current (L0), previous recto, '
          'and previous verso (L1) together. The recto source must overlap the '
          'visible current page in viewport space. samples=$sourceDiagnostics',
    );
  });

  testWidgets('BACK zero-angle iPhone17 pose keeps sheetVersoBack', (
    WidgetTester tester,
  ) async {
    final samples = <_IPhone17ZeroAngleSample>[
      ...await _collectBackwardIPhone17ZeroAngleSamples(
        tester,
        label: 'cur4_turn3',
        initialPage: 3,
      ),
      ...await _collectBackwardIPhone17ZeroAngleSamples(
        tester,
        label: 'cur3_turn2',
        initialPage: 2,
      ),
    ];
    expect(samples, isNotEmpty);
    final pageWidth =
        samples.first.staticCurrentFrontBounds?.width ??
        samples.first.clipBounds?.width.abs() ??
        376.0;

    bool expectsVisibleVerso(_IPhone17ZeroAngleSample sample) {
      final trace = sample.trace;
      if (trace == null) {
        return true;
      }
      final versoWidth = trace.leafVersoWidth ?? 1;
      final rectoCoverage = trace.leafRectoCoverage ?? 0;
      return versoWidth > 0.05 && rectoCoverage < 0.95;
    }

    final visibleVersoSamples = samples
        .where(expectsVisibleVerso)
        .toList(growable: false);
    expect(
      visibleVersoSamples,
      isNotEmpty,
      reason: 'iPhone17 zero-angle BACK must still cover active verso phases.',
    );

    final missingBackSamples = visibleVersoSamples
        .where(
          (sample) =>
              sample.versoFailureReason ==
                  BackwardVersoFailureReason.versoPolygonEmpty ||
              sample.backPolygonPoints == null ||
              !sample.sourceLabels.contains('sheetVersoBack'),
        )
        .toList(growable: false);

    expect(
      missingBackSamples,
      isEmpty,
      reason:
          'iPhone17 zero-angle BACK must not drop sheetVersoBack while the '
          'mainline moving sheet still has visible verso width.\n'
          '${missingBackSamples.map((sample) => sample.describe()).join('\n')}',
    );
    final collapsedRuntimeSamples = visibleVersoSamples
        .where(
          (sample) =>
              sample.versoFailureReason != BackwardVersoFailureReason.none ||
              sample.geometryFailureReason !=
                  BackwardGeometryFailureReason.none ||
              (sample.sampleCount ?? 0) <= 0 ||
              (sample.backFree ?? 0) <= 0 ||
              sample.sheetPolygonPoints == null ||
              sample.backPolygonPoints == null,
        )
        .toList(growable: false);
    expect(
      collapsedRuntimeSamples,
      isEmpty,
      reason:
          'iPhone17 zero-angle BACK must not reproduce the screenshot overlay '
          'state: clip/back empty, faces layers 0, semanticSnapshotHidden, '
          'or versoPolygonEmpty.\n'
          '${collapsedRuntimeSamples.map((sample) => sample.describe()).join('\n')}',
    );
    final fullyLaidRectoSamples = samples
        .where((sample) => !expectsVisibleVerso(sample))
        .toList(growable: false);
    expect(
      fullyLaidRectoSamples,
      isNotEmpty,
      reason:
          'complete held BACK drag must reach the recto/front laid-down phase '
          'instead of staying visually stuck in the middle of the page.',
    );
    final overWideSamples = samples
        .where((sample) {
          final backBounds = sample.sheetVersoBackBounds;
          if (backBounds == null) {
            return false;
          }
          return backBounds.right <= 0 || backBounds.left >= pageWidth;
        })
        .toList(growable: false);
    final rectoExpectedSamples = samples
        .where((sample) => (sample.trace?.leafTotalRectoWidth ?? 0) > 0.05)
        .toList(growable: false);
    final rectoMissingSamples = rectoExpectedSamples
        .where((sample) => sample.sheetRectoFrontBounds == null)
        .toList(growable: false);
    final jumpSamples = <_IPhone17ZeroAngleSample>[];
    for (var index = 1; index < samples.length; index += 1) {
      if (samples[index].label != samples[index - 1].label) {
        continue;
      }
      if (!expectsVisibleVerso(samples[index - 1]) ||
          !expectsVisibleVerso(samples[index])) {
        continue;
      }
      final previous = samples[index - 1].sheetVersoBackBounds;
      final current = samples[index].sheetVersoBackBounds;
      if (previous == null || current == null) {
        continue;
      }
      final maxDelta = <double>[
        (current.left - previous.left).abs(),
        (current.right - previous.right).abs(),
        (current.width - previous.width).abs(),
      ].reduce(math.max);
      if (maxDelta > pageWidth * 0.45) {
        jumpSamples.add(samples[index]);
      }
    }

    expect(
      overWideSamples,
      isEmpty,
      reason:
          'iPhone17 zero-angle BACK currently reproduces oversized '
          'sheetVersoBack. pageWidth=${pageWidth.toStringAsFixed(1)}\n'
          '${overWideSamples.map((sample) => sample.describe()).join('\n')}',
    );
    expect(
      jumpSamples,
      isEmpty,
      reason:
          'iPhone17 zero-angle BACK currently reproduces a discrete '
          'sheetVersoBack bounds jump.\n'
          '${jumpSamples.map((sample) => sample.describe()).join('\n')}',
    );
    expect(
      rectoExpectedSamples,
      isNotEmpty,
      reason:
          'the zero-angle sequence must contain a recto phase emitted by the '
          'backward leaf frame.\n'
          '${samples.map((sample) => sample.describe()).join('\n')}',
    );
    expect(
      rectoMissingSamples,
      isEmpty,
      reason:
          'every leaf-frame recto phase must be diagnosed as a slice of the '
          'same moving sheet, not omitted as a page-space replacement.\n'
          '${rectoMissingSamples.map((sample) => sample.describe()).join('\n')}',
    );
  });

  testWidgets('BACK source attribution maps high-overlap color blocks', (
    WidgetTester tester,
  ) async {
    final sample = await _renderBackwardVersoTextureProbeScene(
      tester,
      surfaceSize: const Size(408, 916),
      backwardDragSteps: List<Offset>.filled(3, const Offset(64, -8)),
    );

    final sourcesByLabel = <String, BackwardPaintSourceDiagnostic>{
      for (final source in sample.paintSources) source.label: source,
    };
    expect(
      sourcesByLabel.keys,
      containsAll(<String>[
        'staticCurrentFront',
        'bottomCurrentFront',
        'sheetRectoFront',
        'sheetPaintedUnion',
        'sheetVersoBack',
        'foldOverlay',
      ]),
      reason:
          'the high-overlap screenshot pose must expose every visible paint source '
          'so user-visible color blocks can be attributed before geometry changes.',
    );
    expect(sourcesByLabel['staticCurrentFront']?.pageIndex, 3);
    expect(sourcesByLabel['bottomCurrentFront']?.pageIndex, 3);
    expect(sourcesByLabel['sheetRectoFront']?.pageIndex, 2);
    expect(sourcesByLabel['sheetRectoFront']?.surfaceKind, 'front');
    expect(sourcesByLabel['sheetVersoBack']?.pageIndex, 2);
    expect(sourcesByLabel['sheetVersoBack']?.surfaceKind, 'back');
    expect(sourcesByLabel, isNot(contains('previousFrontFlatUnifiedToBack')));
    expect(sourcesByLabel, isNot(contains('sheetRectoUnifiedToBack')));
    expect(
      sample.paintSources
          .map((source) => source.zOrder)
          .toList(growable: false),
      orderedEquals(
        sample.paintSources
            .map((source) => source.zOrder)
            .toList(growable: false)
          ..sort(),
      ),
      reason: 'source attribution must follow the actual Stack paint order.',
    );
    expect(
      _semanticBackVisiblePixels(
        sample.framebufferColorCountsBySource['sheetVersoBack'] ??
            const <_ProbeColor, int>{},
      ),
      greaterThan(0),
      reason:
          'source attribution is only useful when visible semantic-back pixels are proven.',
    );
    expect(
      sample.framebufferColorCountsBySource['sheetRectoFront']?[_ProbeColor
              .red] ??
          0,
      greaterThan(0),
      reason:
          'the recto slice must expose previous-front pixels from the flipping '
          'page in the same frame as the verso slice.',
    );
    expect(
      sourcesByLabel['sheetPaintedUnion']?.viewportPolygon.length ?? 0,
      greaterThanOrEqualTo(3),
      reason:
          'the moving sheet painted union must cover both recto and verso '
          'slices.',
    );
    expect(
      sample.framebufferColorCountsBySource['staticCurrentFront']?[_ProbeColor
              .green] ??
          0,
      greaterThan(0),
      reason:
          'the static current source must account for visible current-page pixels.',
    );
  });

  testWidgets('BACK completion enters static stage without a second page turn', (
    WidgetTester tester,
  ) async {
    final sample = await _renderBackwardCompletionSample(tester);

    expect(
      sample.pageChanges,
      equals(<int>[2]),
      reason:
          'a committed BACK turn from page index 3 must publish exactly one page change to index 2.',
    );
    expect(sample.finalPageIndex, 2);
    expect(sample.minimumObservedPageIndex, greaterThanOrEqualTo(2));
    expect(sample.sawDynamicBack, isTrue);
    expect(sample.sawStaticAfterDynamic, isTrue);
    expect(sample.lastDynamicFlippingPageIndex, sample.finalPageIndex);
    expect(sample.firstStaticAfterDynamicPageIndex, sample.finalPageIndex);
    expect(
      sample.lastDynamicFrontSourceLabels,
      isNot(contains('previousFrontFlat')),
      reason:
          'the final dynamic BACK frame must not hand off through the removed free flat branch.',
    );
    expect(
      sample.lastDynamicUnifiedBackSourceLabels,
      isEmpty,
      reason:
          'the final dynamic BACK frame must not normalize previous-front sources into semantic back.',
    );
    expect(
      sample.finalRenderBranch,
      ArticleReadOnlyBookRenderBranch.staticStage,
    );
    expect(sample.finalRenderDirection, isNull);
  });

  test('BACK fold band pixels match mirrored semantic back snapshot', () async {
    await _expectBackwardLeafVersoProbeMatchesSemanticSnapshot(
      pageSize: const Size(400, 600),
      polygon: const <Offset>[
        Offset(44, 92),
        Offset(332, 124),
        Offset(306, 520),
        Offset(72, 492),
      ],
      reasonLabel: 'in-page fold band',
    );
  });

  test(
    'BACK out-of-page fold band still samples semantic back snapshot',
    () async {
      await _expectBackwardLeafVersoProbeMatchesSemanticSnapshot(
        pageSize: const Size(400, 600),
        polygon: const <Offset>[
          Offset(-76, 88),
          Offset(246, 126),
          Offset(220, 522),
          Offset(-44, 484),
        ],
        reasonLabel: 'out-of-page fold band',
        expectOutOfPageMesh: true,
      );
    },
  );

  test('BACK material UV phase stays fixed when visible clip widens', () async {
    const pageSize = Size(400, 600);
    const sheetPoint = Offset(230, 400);
    const materialLocalPolygon = <Offset>[
      Offset(60, 0),
      Offset(460, 0),
      Offset(460, 600),
      Offset(60, 600),
    ];
    final snapshotImage = await _createSemanticBackSurfaceProbeImage(
      pageSize: pageSize,
      pageIndex: 2,
    );
    final snapshot = ArticlePageTextureSnapshot(
      image: snapshotImage,
      logicalSize: pageSize,
      pixelRatio: 1,
      semanticSurfaceKind: 'back',
    );

    Future<_ProbeColor> colorAtSheetPoint({
      required List<Offset> polygon,
    }) async {
      final renderedImage = await renderBackwardLeafVersoProbeImage(
        leafVersoSnapshot: snapshot,
        pageSize: pageSize,
        polygon: polygon,
        materialLocalPolygon: materialLocalPolygon,
      );
      expect(renderedImage, isNotNull);
      final mesh = buildBackwardLeafVersoMaterialUvMesh(
        pageSize: pageSize,
        materialLocalPolygon: materialLocalPolygon,
      );
      expect(mesh, isNotNull);
      final bytes = await _rawRgbaBytes(renderedImage!);
      final paintOrigin = _polygonBounds(polygon)!.inflate(1).topLeft;
      final color = _classifyProbeColor(
        _colorAtBytes(
          renderedImage.width,
          renderedImage.height,
          bytes,
          sheetPoint - paintOrigin,
        ),
      );
      renderedImage.dispose();
      return color;
    }

    final narrowColor = await colorAtSheetPoint(
      polygon: const <Offset>[
        Offset(300, 300),
        Offset(240, 300),
        Offset(240, 500),
        Offset(120, 500),
      ],
    );
    final wideColor = await colorAtSheetPoint(
      polygon: const <Offset>[
        Offset(300, 300),
        Offset(360, 300),
        Offset(360, 500),
        Offset(120, 500),
      ],
    );
    expect(narrowColor, equals(wideColor));
    expect(
      narrowColor,
      isNot(_ProbeColor.other),
      reason:
          'widening the visible clip must not retarget BACK material UV sampling.',
    );
    snapshotImage.dispose();
  });

  testWidgets(
    'a. mesh coverage keeps the fold band continuous across scanlines',
    (WidgetTester tester) async {
      final sample = await _renderForwardProbeScene(tester);
      expect(sample.seenRed, isTrue);
      expect(
        sample.maxWhiteRun,
        lessThanOrEqualTo(6),
        reason:
            'a wide white band between front and back suggests a coverage gap',
      );
    },
  );

  testWidgets(
    'b. forward composition keeps the current page before the next page on the scanline',
    (WidgetTester tester) async {
      final sample = await _renderForwardProbeScene(tester);
      expect(sample.seenGreen, isTrue);
      expect(sample.firstRedX, greaterThanOrEqualTo(0));
      expect(sample.firstGreenX, greaterThanOrEqualTo(0));
      expect(
        sample.firstRedX,
        lessThan(sample.firstGreenX),
        reason: 'current-page region should appear before the next-page region',
      );
    },
  );
}

List<ArticlePageData> _diagnosticPages() {
  return List<ArticlePageData>.generate(
    5,
    (index) => ArticlePageData(
      id: 'diag_$index',
      title: 'SEAM TRACE / ${index + 1}',
      body: 'page ${index + 1}/5\n\nTRACK-${index + 1}',
    ),
  );
}

Future<_BackwardCompositeProbeSample> _renderBackwardCompositeProbeScene(
  WidgetTester tester,
) async {
  const probeSurfaceSize = Size(900, 1200);
  await tester.binding.setSurfaceSize(probeSurfaceSize);
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final scenes = <StPageFlipScene>[];
  final debugStates = <ArticleReadOnlyBookDebugState>[];

  await tester.pumpWidget(
    MaterialApp(
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
          );
        },
      ),
    ),
  );
  await tester.pumpAndSettle();

  final forwardGesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomRight)),
  );
  await forwardGesture.moveBy(const Offset(-320, -36));
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

  final gesture = await tester.startGesture(const Offset(32, 458));

  await gesture.moveBy(const Offset(36, -8));
  for (var i = 0; i < 4; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  await gesture.moveBy(const Offset(360, -36));
  for (var i = 0; i < 8; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  // Full previous-front baseline must not appear in the widget tree.
  final baselineKeyVisible = find
      .byKey(const ValueKey<String>('article_backward_previous_front_baseline'))
      .evaluate()
      .isNotEmpty;

  final mainlineStates = debugStates
      .where(
        (s) =>
            s.renderDirection == StPageFlipDirection.back &&
            s.backwardCompositeMode == 'paperFoldBackwardMainline',
      )
      .toList(growable: false);
  expect(mainlineStates, isNotEmpty);

  final compositeMode = mainlineStates.last.backwardCompositeMode ?? '';
  final bottomLayerPageIndex = mainlineStates.last.backwardBottomLayerPageIndex;
  final flippingLayerPageIndex =
      mainlineStates.last.backwardFlippingLayerPageIndex;
  final backPixelSurfaceStrategy =
      mainlineStates.last.backwardBackPixelSurfaceStrategy;
  final backSheetId = mainlineStates.last.backwardBackSheetId;
  final foldXSamples = mainlineStates
      .where((s) => s.backwardFoldX != null)
      .map((s) => s.backwardFoldX!)
      .toList(growable: false);
  final foldXAdvance = foldXSamples.isEmpty
      ? 0.0
      : foldXSamples.last - foldXSamples.first;
  await gesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  final animationMainlineStates = debugStates
      .where(
        (s) =>
            s.renderDirection == StPageFlipDirection.back &&
            s.backwardCompositeMode == 'paperFoldBackwardMainline',
      )
      .toList(growable: false);
  final latePoseStates = animationMainlineStates
      .where(
        (s) =>
            s.backwardFrontPaintBounds != null &&
            (s.backwardVersoWidth ?? 0) > 0.01 &&
            s.backwardBackPaintBounds != null &&
            s.backwardCurrentResidualBounds != null &&
            s.backwardSurfaceViewportRect != null,
      )
      .toList(growable: false);
  final latePoseState = latePoseStates.isEmpty
      ? animationMainlineStates.last
      : latePoseStates.last;

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));

  return _BackwardCompositeProbeSample(
    compositeMode: compositeMode,
    bottomLayerPageIndex: bottomLayerPageIndex,
    flippingLayerPageIndex: flippingLayerPageIndex,
    backPixelSurfaceStrategy: backPixelSurfaceStrategy,
    backSheetId: backSheetId,
    baselineKeyVisible: baselineKeyVisible,
    foldXSamples: foldXSamples,
    foldXAdvance: foldXAdvance,
    latePoseCount: latePoseStates.length,
    latePoseSurfaceWidth:
        latePoseState.backwardSurfaceViewportRect?.width ?? 0.0,
    latePoseBackWidth: latePoseState.backwardBackPaintBounds?.width ?? 0.0,
    latePoseFrontWidth: latePoseState.backwardFrontPaintBounds?.width ?? 0.0,
    latePoseCurrentWidth:
        latePoseState.backwardCurrentResidualBounds?.width ?? 0.0,
    latePoseBackVertexCount: latePoseState.backwardBackVertexCount ?? 0,
    latePoseFrontSheetId: latePoseState.backwardFrontSheetId,
    latePoseBackSheetId: latePoseState.backwardBackSheetId,
  );
}

Widget _buildProbePageSurface(
  BuildContext context,
  int pageIndex,
  Size pageSize,
) {
  final color = switch (pageIndex) {
    2 => const Color(0xFFE53935),
    3 => const Color(0xFF43A047),
    _ => const Color(0xFF1E88E5),
  };
  return ColoredBox(
    key: ValueKey<String>('article_probe_page_$pageIndex'),
    color: color,
    child: Align(
      alignment: Alignment.centerLeft,
      child: Container(width: pageSize.width * 0.08, color: Colors.black),
    ),
  );
}

Widget _buildProbeBackPageSurface(
  BuildContext context,
  int pageIndex,
  Size pageSize,
) {
  final color = switch (pageIndex) {
    2 => const Color(0xFF00E5FF),
    3 => const Color(0xFFFFD600),
    _ => const Color(0xFF7C4DFF),
  };
  return ColoredBox(
    key: ValueKey<String>('article_probe_back_page_$pageIndex'),
    color: color,
    child: Stack(
      fit: StackFit.expand,
      children: <Widget>[
        Align(
          alignment: Alignment.centerLeft,
          child: Container(width: pageSize.width * 0.18, color: Colors.white),
        ),
        Align(
          alignment: Alignment.center,
          child: Container(width: pageSize.width * 0.18, color: Colors.black),
        ),
        Align(
          alignment: Alignment.centerRight,
          child: Container(width: pageSize.width * 0.18, color: Colors.white),
        ),
      ],
    ),
  );
}

Future<_BackwardVersoTextureProbeSample> _renderBackwardVersoTextureProbeScene(
  WidgetTester tester, {
  Offset backwardDragDelta = const Offset(120, -40),
  Size surfaceSize = const Size(900, 1200),
  List<Offset>? backwardDragSteps,
  Widget Function(BuildContext context, int pageIndex, Size pageSize)?
  debugBackPageSurfaceBuilder,
}) async {
  await tester.binding.setSurfaceSize(surfaceSize);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final boundaryKey = GlobalKey();
  final debugStates = <ArticleReadOnlyBookDebugState>[];
  Size? capturedBackPageSize;

  await tester.pumpWidget(
    MaterialApp(
      home: RepaintBoundary(
        key: boundaryKey,
        child: LayoutBuilder(
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
              initialPage: 3,
              coverUrl: '',
              showFooterPageLabel: false,
              onDebugStateChanged: debugStates.add,
              debugPageSurfaceBuilder: _buildProbePageSurface,
              debugBackPageSurfaceBuilder: (context, pageIndex, pageSize) {
                capturedBackPageSize = pageSize;
                return (debugBackPageSurfaceBuilder ??
                        _buildProbeBackPageSurface)
                    .call(context, pageIndex, pageSize);
              },
            );
          },
        ),
      ),
    ),
  );
  await tester.pump();
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final backwardGesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
  );
  for (final dragStep in backwardDragSteps ?? <Offset>[backwardDragDelta]) {
    await backwardGesture.moveBy(dragStep);
    for (var i = 0; i < 4; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
  }

  var probeState = debugStates.lastWhere(
    (state) =>
        state.renderDirection == StPageFlipDirection.back &&
        state.backwardCompositeMode == 'paperFoldBackwardMainline' &&
        state.backwardBackPaintBounds != null &&
        state.backwardBackSheetId == 'mainlineLeaf:2',
  );
  expect(probeState.backwardBackLocalPolygonRaw, isNotEmpty);
  expect(probeState.backwardVersoProbeLocalPoints, isNotEmpty);
  expect(probeState.backwardVersoProbeViewportPoints, isNotEmpty);
  expect(capturedBackPageSize, isNotNull);

  final framebufferImage = await tester.runAsync<ui.Image>(
    () => _captureBoundaryImage(boundaryKey),
  );
  if (framebufferImage == null) {
    fail('failed to capture ArticleReadOnlyBookDeck framebuffer image');
  }
  final framebufferBytes = await tester.runAsync<Uint8List>(
    () => _rawRgbaBytes(framebufferImage),
  );
  if (framebufferBytes == null) {
    fail('failed to read ArticleReadOnlyBookDeck framebuffer bytes');
  }
  final framebufferProbeColors = <_ProbeColor>[];
  final framebufferBackExpectedColors = <_ProbeColor>[];
  final framebufferBackActualColors = <_ProbeColor>[];
  final framebufferBackExpectedAllColors = <_ProbeColor>[];
  final framebufferFrontColors = <_ProbeColor>[];
  final framebufferCurrentColors = <_ProbeColor>[];
  final sampleCount = math.min(
    probeState.backwardVersoProbeLocalPoints.length,
    probeState.backwardVersoProbeViewportPoints.length,
  );
  for (var index = 0; index < sampleCount; index += 1) {
    final viewportPoint = probeState.backwardVersoProbeViewportPoints[index];
    final localPoint = probeState.backwardVersoProbeLocalPoints[index];
    final texturePoint =
        index < probeState.backwardVersoProbeTexturePoints.length
        ? probeState.backwardVersoProbeTexturePoints[index]
        : localPoint;
    final backBounds = probeState.backwardBackPaintBounds;
    if (backBounds == null || !backBounds.contains(viewportPoint)) {
      continue;
    }
    final actualColor = _classifyProbeColor(
      _colorAtBytes(
        framebufferImage.width,
        framebufferImage.height,
        framebufferBytes,
        viewportPoint,
      ),
    );
    final expectedBackColor = _semanticBackProbeColor(
      pageSize: capturedBackPageSize!,
      pageIndex: 2,
      localPoint: texturePoint,
    );
    framebufferBackActualColors.add(actualColor);
    framebufferBackExpectedAllColors.add(expectedBackColor);
    if (!_semanticBackColorMatches(actualColor, expectedBackColor)) {
      continue;
    }
    framebufferProbeColors.add(actualColor);
    framebufferBackExpectedColors.add(expectedBackColor);
    framebufferFrontColors.add(
      _frontProbeColor(
        pageSize: capturedBackPageSize!,
        pageIndex: 2,
        localPoint: texturePoint,
      ),
    );
    framebufferCurrentColors.add(
      _frontProbeColor(
        pageSize: capturedBackPageSize!,
        pageIndex: 3,
        localPoint: localPoint,
      ),
    );
  }
  final framebufferColorCountsBySource = <String, Map<_ProbeColor, int>>{};
  for (final source in probeState.backwardPaintSources) {
    final bounds = source.viewportBounds;
    if (bounds == null || bounds.isEmpty) {
      continue;
    }
    framebufferColorCountsBySource[source.label] = _scanColorsInPolygon(
      imageWidth: framebufferImage.width,
      imageHeight: framebufferImage.height,
      bytes: framebufferBytes,
      polygon: source.viewportPolygon.isEmpty
          ? <Offset>[
              bounds.topLeft,
              bounds.topRight,
              bounds.bottomRight,
              bounds.bottomLeft,
            ]
          : source.viewportPolygon,
      edgeInset: 6,
    );
  }
  final backSource = probeState.backwardPaintSources.firstWhere(
    (source) => source.label == 'sheetVersoBack',
    orElse: () => const BackwardPaintSourceDiagnostic(
      label: 'sheetVersoBack',
      zOrder: 0,
      pageIndex: null,
      surfaceKind: 'back',
      status: 'missing',
      viewportBounds: null,
      polygonSignature: '-',
    ),
  );
  final frontSource = probeState.backwardPaintSources.firstWhere(
    (source) => source.label == 'sheetRectoFront',
    orElse: () => const BackwardPaintSourceDiagnostic(
      label: 'sheetRectoFront',
      zOrder: 0,
      pageIndex: null,
      surfaceKind: 'front',
      status: 'missing',
      viewportBounds: null,
      polygonSignature: '-',
    ),
  );
  final currentSourcePolygons = probeState.backwardPaintSources
      .where((source) => source.label == 'bottomCurrentFront')
      .map((source) => source.viewportPolygon)
      .where((polygon) => polygon.length >= 3)
      .toList(growable: false);
  final visibleBackColorCounts = _scanVisibleBackColors(
    imageWidth: framebufferImage.width,
    imageHeight: framebufferImage.height,
    bytes: framebufferBytes,
    backPolygon: backSource.viewportPolygon,
    backBounds: backSource.viewportBounds,
    frontPolygon: frontSource.viewportPolygon,
    excludePolygons: currentSourcePolygons,
  );
  final movingSheetColorCounts = _scanMovingSheetColors(
    imageWidth: framebufferImage.width,
    imageHeight: framebufferImage.height,
    bytes: framebufferBytes,
    backPolygon: backSource.viewportPolygon,
    backBounds: backSource.viewportBounds,
    frontPolygon: const <Offset>[],
    frontBounds: null,
  );
  await backwardGesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));
  framebufferImage.dispose();

  return _BackwardVersoTextureProbeSample(
    renderSceneReady: probeState.renderSceneReady,
    sessionHasBundle: probeState.sessionHasBundle,
    backBandWidth: probeState.backwardBackPaintBounds!.width,
    backSurfaceStrategy: probeState.backwardBackPixelSurfaceStrategy,
    activeRectoPageIndex: probeState.activeRectoPageIndex,
    activeVersoPageIndex: probeState.activeVersoPageIndex,
    activeBottomPageIndex: probeState.activeBottomPageIndex,
    activeVersoSurfaceKind: probeState.activeVersoSurfaceKind,
    versoDisplayState: probeState.backwardVersoDisplayState,
    uvStrategy: probeState.backwardVersoTextureUvStrategy,
    runtimeFailureReason: probeState.backwardVersoFailureReason,
    probePointCount: probeState.backwardVersoProbeLocalPoints.length,
    frontBackOverlapWidth: probeState.backwardFrontBackOverlapWidth,
    backVisibleUncoveredWidth: probeState.backwardBackVisibleUncoveredWidth,
    visibleProbeCount: framebufferProbeColors.length,
    paintSources: probeState.backwardPaintSources,
    framebufferColorCountsBySource: framebufferColorCountsBySource,
    visibleBackColorCounts: visibleBackColorCounts,
    visibleBackPixelCount: visibleBackColorCounts.values.fold(
      0,
      (sum, count) => sum + count,
    ),
    movingSheetColorCounts: movingSheetColorCounts,
    movingSheetPixelCount: movingSheetColorCounts.values.fold(
      0,
      (sum, count) => sum + count,
    ),
    pageSize: capturedBackPageSize ?? const Size(400, 600),
    probeLocalPoints: probeState.backwardVersoProbeLocalPoints,
    probeTexturePoints: probeState.backwardVersoProbeTexturePoints,
    framebufferProbeColors: framebufferProbeColors,
    framebufferBackActualColors: framebufferBackActualColors,
    framebufferBackExpectedColors: framebufferBackExpectedColors,
    framebufferBackExpectedAllColors: framebufferBackExpectedAllColors,
    framebufferFrontColors: framebufferFrontColors,
    framebufferCurrentColors: framebufferCurrentColors,
  );
}

Future<_BackwardCompletionSample> _renderBackwardCompletionSample(
  WidgetTester tester,
) async {
  await tester.binding.setSurfaceSize(const Size(900, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final debugStates = <ArticleReadOnlyBookDebugState>[];
  final pageChanges = <int>[];

  await tester.pumpWidget(
    MaterialApp(
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
            initialPage: 3,
            coverUrl: '',
            showFooterPageLabel: false,
            onDebugStateChanged: debugStates.add,
            onPageChanged: pageChanges.add,
            debugPageSurfaceBuilder: _buildProbePageSurface,
            debugBackPageSurfaceBuilder: _buildProbeBackPageSurface,
          );
        },
      ),
    ),
  );
  await tester.pump();
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  pageChanges.clear();
  debugStates.clear();

  final backwardGesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
  );
  await backwardGesture.moveBy(const Offset(420, -48));
  for (var i = 0; i < 8; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  await backwardGesture.up();
  for (var i = 0; i < 90; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final finalState = debugStates.last;
  var sawDynamicBack = false;
  var sawStaticAfterDynamic = false;
  var minimumObservedPageIndex = finalState.currentPageIndex;
  ArticleReadOnlyBookDebugState? lastDynamicBackState;
  ArticleReadOnlyBookDebugState? firstStaticAfterDynamicState;
  for (final state in debugStates) {
    minimumObservedPageIndex = math.min(
      minimumObservedPageIndex,
      state.currentPageIndex,
    );
    if (state.renderDirection == StPageFlipDirection.back &&
        state.renderBranch ==
            ArticleReadOnlyBookRenderBranch.paperFoldDynamic) {
      sawDynamicBack = true;
      lastDynamicBackState = state;
    }
    if (sawDynamicBack &&
        state.renderDirection == null &&
        state.renderBranch == ArticleReadOnlyBookRenderBranch.staticStage) {
      sawStaticAfterDynamic = true;
      firstStaticAfterDynamicState ??= state;
    }
  }
  final lastDynamicPaintSources =
      lastDynamicBackState?.backwardPaintSources ??
      const <BackwardPaintSourceDiagnostic>[];

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));
  return _BackwardCompletionSample(
    pageChanges: List<int>.unmodifiable(pageChanges),
    finalPageIndex: finalState.currentPageIndex,
    minimumObservedPageIndex: minimumObservedPageIndex,
    sawDynamicBack: sawDynamicBack,
    sawStaticAfterDynamic: sawStaticAfterDynamic,
    finalRenderBranch: finalState.renderBranch,
    finalRenderDirection: finalState.renderDirection,
    lastDynamicFlippingPageIndex:
        lastDynamicBackState?.backwardFlippingLayerPageIndex,
    firstStaticAfterDynamicPageIndex:
        firstStaticAfterDynamicState?.currentPageIndex,
    lastDynamicUnifiedBackSourceLabels: List<String>.unmodifiable(
      lastDynamicPaintSources
          .where((source) => source.status == 'unifiedToBack')
          .map((source) => source.label),
    ),
    lastDynamicFrontSourceLabels: List<String>.unmodifiable(
      lastDynamicPaintSources
          .where(
            (source) =>
                source.surfaceKind == 'front' &&
                source.label == 'sheetRectoFront',
          )
          .map((source) => source.label),
    ),
  );
}

Future<_BackwardGeometrySweepSample> _renderBackwardGeometrySweepSample(
  WidgetTester tester, {
  required ArticlePageCurlCorner corner,
  required double angleDegrees,
  required double depth,
}) async {
  await tester.binding.setSurfaceSize(const Size(900, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final debugStates = <ArticleReadOnlyBookDebugState>[];

  await tester.pumpWidget(
    MaterialApp(
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
            initialPage: 3,
            coverUrl: '',
            showFooterPageLabel: false,
            onDebugStateChanged: debugStates.add,
          );
        },
      ),
    ),
  );
  await tester.pump();
  for (var i = 0; i < 8; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final gesture = await tester.startGesture(
    tester.getCenter(find.byKey(_cornerHotzoneKey(corner))),
  );
  await gesture.moveBy(
    _backwardSweepDelta(
      corner: corner,
      angleDegrees: angleDegrees,
      depth: depth,
    ),
  );
  for (var i = 0; i < 6; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final backwardState = debugStates.lastWhere(
    (state) => state.renderDirection == StPageFlipDirection.back,
  );

  await gesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));

  return _BackwardGeometrySweepSample(
    corner: corner,
    angleDegrees: angleDegrees,
    depth: depth,
    failureReason: backwardState.backwardGeometryFailureReason,
    compositeMode: backwardState.backwardCompositeMode,
    backWidth: backwardState.backwardBackPaintBounds?.width ?? 0,
    currentWidth: backwardState.backwardCurrentResidualBounds?.width ?? 0,
    renderSceneReady: backwardState.renderSceneReady,
    sessionHasBundle: backwardState.sessionHasBundle,
    activeRectoPageIndex: backwardState.activeRectoPageIndex,
    activeVersoPageIndex: backwardState.activeVersoPageIndex,
    activeBottomPageIndex: backwardState.activeBottomPageIndex,
    activeVersoSurfaceKind: backwardState.activeVersoSurfaceKind,
    versoDisplayState: backwardState.backwardVersoDisplayState,
  );
}

Future<List<ArticleReadOnlyBookDebugState>>
_collectBackwardAngleToHorizontalSamples(WidgetTester tester) async {
  await tester.binding.setSurfaceSize(const Size(900, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final debugStates = <ArticleReadOnlyBookDebugState>[];

  await tester.pumpWidget(
    MaterialApp(
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
            initialPage: 3,
            coverUrl: '',
            showFooterPageLabel: false,
            onDebugStateChanged: debugStates.add,
            debugPageSurfaceBuilder: _buildProbePageSurface,
            debugBackPageSurfaceBuilder: _buildProbeBackPageSurface,
          );
        },
      ),
    ),
  );
  await tester.pump();
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  debugStates.clear();

  final gesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
  );
  final samples = <ArticleReadOnlyBookDebugState>[];
  Future<void> moveAndSample(Offset delta) async {
    await gesture.moveBy(delta);
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    samples.add(
      debugStates.lastWhere(
        (state) => state.renderDirection == StPageFlipDirection.back,
      ),
    );
  }

  await moveAndSample(const Offset(360, -36));
  // Sample the held pull through horizontal in pointer-sized increments.
  // A 36px teleport cannot distinguish a continuous folded sheet from a
  // discontinuity that happens between two gesture events.
  for (var i = 0; i < 6; i += 1) {
    await moveAndSample(const Offset(0, 12));
  }
  for (var i = 0; i < 6; i += 1) {
    await moveAndSample(const Offset(20, 0));
  }

  await gesture.up();
  await tester.pump(const Duration(milliseconds: 16));
  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));

  return List<ArticleReadOnlyBookDebugState>.unmodifiable(samples);
}

Future<List<_IPhone17ZeroAngleSample>> _collectBackwardIPhone17ZeroAngleSamples(
  WidgetTester tester, {
  required String label,
  required int initialPage,
}) async {
  await tester.binding.setSurfaceSize(const Size(408, 916));
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final scenes = <StPageFlipScene>[];
  final debugStates = <ArticleReadOnlyBookDebugState>[];

  await tester.pumpWidget(
    MaterialApp(
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
            initialPage: initialPage,
            coverUrl: '',
            showFooterPageLabel: false,
            onSceneChanged: scenes.add,
            onDebugStateChanged: debugStates.add,
            debugPageSurfaceBuilder: _buildProbePageSurface,
            debugBackPageSurfaceBuilder: _buildProbeBackPageSurface,
          );
        },
      ),
    ),
  );
  await tester.pump();
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  debugStates.clear();

  final gesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
  );
  final samples = <_IPhone17ZeroAngleSample>[];
  var totalDx = 0.0;
  for (final stepDx in <double>[120, 60, 60, 60, 60, 60, 60, 60]) {
    totalDx += stepDx;
    await gesture.moveBy(Offset(stepDx, 0));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    final backStates = debugStates
        .where(
          (state) =>
              state.renderDirection == StPageFlipDirection.back &&
              state.backwardCompositeMode == 'paperFoldBackwardMainline',
        )
        .toList(growable: false);
    expect(
      backStates,
      isNotEmpty,
      reason:
          'iPhone17 zero-angle sample dx=$totalDx must enter BACK mainline.',
    );
    final state = backStates.last;
    StPageFlipScene? scene;
    for (final candidate in scenes) {
      if (candidate.effectiveRenderDirection == StPageFlipDirection.back &&
          candidate.renderFrame?.renderDirection == StPageFlipDirection.back) {
        scene = candidate;
      }
    }
    final trace = _traceBackwardPartition(scene);
    final sourcesByLabel = <String, BackwardPaintSourceDiagnostic>{
      for (final source in state.backwardPaintSources) source.label: source,
    };
    samples.add(
      _IPhone17ZeroAngleSample(
        label: label,
        totalDx: totalDx,
        guideX: state.guideX,
        clipBounds: state.bottomClipBounds,
        frontBounds: state.backwardFrontPaintBounds,
        backBounds: state.backwardBackPaintBounds,
        versoFailureReason: state.backwardVersoFailureReason,
        geometryFailureReason: state.backwardGeometryFailureReason,
        frontPolygonPoints: state.backwardFrontPolygonPoints,
        backPolygonPoints: state.backwardBackPolygonPoints,
        sheetPolygonPoints: state.backwardSheetPolygonPoints,
        bottomClipPolygonPoints: state.backwardBottomClipPolygonPoints,
        sourceLabels: state.backwardPaintSources
            .map((source) => source.label)
            .toList(growable: false),
        staticCurrentFrontBounds:
            sourcesByLabel['staticCurrentFront']?.viewportBounds,
        bottomCurrentFrontBounds:
            sourcesByLabel['bottomCurrentFront']?.viewportBounds,
        sheetPaintedUnionBounds:
            sourcesByLabel['sheetPaintedUnion']?.viewportBounds,
        sheetRectoFrontBounds:
            sourcesByLabel['sheetRectoFront']?.viewportBounds,
        sheetVersoBackBounds: sourcesByLabel['sheetVersoBack']?.viewportBounds,
        sampleCount: state.backwardBackVisibleProbeCount,
        backFree: state.backwardBackVisibleUncoveredWidth,
        frontBackOverlap: state.backwardFrontBackOverlapWidth,
        foldLine:
            state.backwardFoldLineTop != null &&
                state.backwardFoldLineBottom != null
            ? (state.backwardFoldLineTop!, state.backwardFoldLineBottom!)
            : null,
        freeEdgeLine:
            state.backwardPageEdgeLineTop != null &&
                state.backwardPageEdgeLineBottom != null
            ? (
                state.backwardPageEdgeLineTop!,
                state.backwardPageEdgeLineBottom!,
              )
            : null,
        trace: trace,
      ),
    );
  }

  await gesture.up();
  await tester.pump(const Duration(milliseconds: 16));
  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));
  return List<_IPhone17ZeroAngleSample>.unmodifiable(samples);
}

_BackwardPartitionTrace? _traceBackwardPartition(StPageFlipScene? scene) {
  final frame = scene?.renderFrame;
  if (scene == null || frame == null) {
    return null;
  }
  final leaf = frame.backwardLeafFrame;
  return _BackwardPartitionTrace(
    progress: frame.progress,
    angle: frame.angle,
    visualGeometryDirection: frame.visualGeometryDirection,
    leafCoveredWidth: leaf?.coveredWidthNormalized,
    leafRectoCoverage: leaf?.rectoCoverageNormalized,
    leafTotalRectoWidth: leaf?.totalRectoVisibleWidthNormalized,
    leafVersoWidth: leaf == null
        ? null
        : (leaf.coveredWidthNormalized - leaf.totalRectoVisibleWidthNormalized)
              .clamp(0.0, 1.0)
              .toDouble(),
  );
}

void _expectSourceBoundsTransitionIsContinuous(
  List<ArticleReadOnlyBookDebugState> samples, {
  required String label,
  required double maxEdgeDelta,
}) {
  Rect? boundsFor(ArticleReadOnlyBookDebugState state) {
    for (final source in state.backwardPaintSources) {
      if (source.label == label) {
        return source.viewportBounds;
      }
    }
    return null;
  }

  for (var index = 1; index < samples.length; index += 1) {
    final previous = boundsFor(samples[index - 1]);
    final current = boundsFor(samples[index]);
    expect(previous, isNotNull, reason: '$label sample ${index - 1}');
    expect(current, isNotNull, reason: '$label sample $index');
    final edgeDeltas = <double>[
      (current!.left - previous!.left).abs(),
      (current.right - previous.right).abs(),
      (current.width - previous.width).abs(),
    ];
    expect(
      edgeDeltas.reduce(math.max),
      lessThan(maxEdgeDelta),
      reason:
          '$label must not jump when a BACK drag flattens from angled to '
          'horizontal. previous=$previous current=$current',
    );
  }
}

Key _cornerHotzoneKey(ArticlePageCurlCorner corner) {
  return switch (corner) {
    ArticlePageCurlCorner.topLeft => TestKeys.articlePageCurlHotzoneTopLeft,
    ArticlePageCurlCorner.bottomLeft =>
      TestKeys.articlePageCurlHotzoneBottomLeft,
    ArticlePageCurlCorner.topRight => TestKeys.articlePageCurlHotzoneTopRight,
    ArticlePageCurlCorner.bottomRight =>
      TestKeys.articlePageCurlHotzoneBottomRight,
  };
}

Offset _backwardSweepDelta({
  required ArticlePageCurlCorner corner,
  required double angleDegrees,
  required double depth,
}) {
  final radians = angleDegrees * math.pi / 180;
  final dyMagnitude = math.tan(radians) * depth;
  final dy = switch (corner) {
    ArticlePageCurlCorner.topLeft ||
    ArticlePageCurlCorner.topRight => dyMagnitude,
    ArticlePageCurlCorner.bottomLeft ||
    ArticlePageCurlCorner.bottomRight => -dyMagnitude,
  };
  return Offset(depth, dy);
}

Future<void> _expectBackwardLeafVersoProbeMatchesSemanticSnapshot({
  required Size pageSize,
  required List<Offset> polygon,
  required String reasonLabel,
  List<Offset>? materialLocalPolygon,
  bool expectOutOfPageMesh = false,
}) async {
  final resolvedMaterialLocalPolygon =
      materialLocalPolygon ??
      (expectOutOfPageMesh
          ? polygon
          : <Offset>[
              Offset.zero,
              Offset(pageSize.width, 0),
              Offset(pageSize.width, pageSize.height),
              Offset(0, pageSize.height),
            ]);
  final snapshotImage = await _createSemanticBackSurfaceProbeImage(
    pageSize: pageSize,
    pageIndex: 2,
  );
  final snapshot = ArticlePageTextureSnapshot(
    image: snapshotImage,
    logicalSize: pageSize,
    pixelRatio: 1,
    semanticSurfaceKind: 'back',
  );
  final probe = resolveBackwardVersoPixelProbe(
    pageSize: pageSize,
    polygon: polygon,
    materialLocalPolygon: resolvedMaterialLocalPolygon,
  );
  expect(
    probe.isEmpty,
    isFalse,
    reason: '$reasonLabel must expose probe points.',
  );

  final renderedImage = await renderBackwardLeafVersoProbeImage(
    leafVersoSnapshot: snapshot,
    pageSize: pageSize,
    polygon: polygon,
    materialLocalPolygon: resolvedMaterialLocalPolygon,
  );
  expect(renderedImage, isNotNull);
  final renderedMesh = buildBackwardLeafVersoMaterialUvMesh(
    pageSize: pageSize,
    materialLocalPolygon: resolvedMaterialLocalPolygon,
  );
  expect(renderedMesh, isNotNull);
  if (expectOutOfPageMesh) {
    expect(
      renderedMesh!.paintBounds.left < 0 ||
          renderedMesh.paintBounds.right > pageSize.width ||
          renderedMesh.paintBounds.top < 0 ||
          renderedMesh.paintBounds.bottom > pageSize.height,
      isTrue,
      reason: '$reasonLabel must actually leave the page rect.',
    );
  }
  final renderedPaintOrigin = _polygonBounds(polygon)!.inflate(1).topLeft;
  final frontImage = await _createFrontSurfaceProbeImage(
    pageSize: pageSize,
    pageIndex: 2,
  );
  final currentImage = await _createFrontSurfaceProbeImage(
    pageSize: pageSize,
    pageIndex: 3,
  );
  final renderedBytes = await _rawRgbaBytes(renderedImage!);
  final snapshotBytes = await _rawRgbaBytes(snapshotImage);
  final frontBytes = await _rawRgbaBytes(frontImage);
  final currentBytes = await _rawRgbaBytes(currentImage);
  final actualProbeColors = <_ProbeColor>[];
  final backSurfaceExpectedProbeColors = <_ProbeColor>[];
  final doubleMirrorProbeColors = <_ProbeColor>[];
  final frontProbeColors = <_ProbeColor>[];
  final currentProbeColors = <_ProbeColor>[];

  for (var index = 0; index < probe.localPoints.length; index += 1) {
    final localPoint = probe.localPoints[index];
    final texturePoint = index < probe.texturePoints.length
        ? probe.texturePoints[index]
        : localPoint;
    actualProbeColors.add(
      _classifyProbeColor(
        _colorAtBytes(
          renderedImage.width,
          renderedImage.height,
          renderedBytes,
          localPoint - renderedPaintOrigin,
        ),
      ),
    );
    backSurfaceExpectedProbeColors.add(
      _classifyProbeColor(
        _colorAtBytes(
          snapshotImage.width,
          snapshotImage.height,
          snapshotBytes,
          texturePoint,
        ),
      ),
    );
    doubleMirrorProbeColors.add(
      _classifyProbeColor(
        _colorAtBytes(
          snapshotImage.width,
          snapshotImage.height,
          snapshotBytes,
          Offset(pageSize.width - texturePoint.dx, texturePoint.dy),
        ),
      ),
    );
    frontProbeColors.add(
      _classifyProbeColor(
        _colorAtBytes(
          frontImage.width,
          frontImage.height,
          frontBytes,
          localPoint,
        ),
      ),
    );
    currentProbeColors.add(
      _classifyProbeColor(
        _colorAtBytes(
          currentImage.width,
          currentImage.height,
          currentBytes,
          localPoint,
        ),
      ),
    );
  }

  final samplesSemanticBackInterior = actualProbeColors.every(
    (color) => color == _ProbeColor.cyan || color == _ProbeColor.black,
  );
  final failureReason = samplesSemanticBackInterior
      ? BackwardVersoFailureReason.none
      : BackwardVersoFailureReason.mirrorDirectionMismatch;

  expect(
    failureReason,
    BackwardVersoFailureReason.none,
    reason:
        '$reasonLabel must sample the semantic back snapshot interior band. '
        'actual=$actualProbeColors '
        'backSurface=$backSurfaceExpectedProbeColors '
        'doubleMirror=$doubleMirrorProbeColors',
  );
  expect(
    actualProbeColors.contains(_ProbeColor.cyan),
    isTrue,
    reason:
        '$reasonLabel probe pattern must include semantic back content, not edge paper.',
  );
  expect(
    actualProbeColors,
    isNot(equals(frontProbeColors)),
    reason: '$reasonLabel must not match the previous leaf front surface.',
  );
  expect(
    actualProbeColors,
    isNot(equals(currentProbeColors)),
    reason: '$reasonLabel must not match the covered current page surface.',
  );

  renderedImage.dispose();
  frontImage.dispose();
  currentImage.dispose();
  snapshot.dispose();
}

Future<ui.Image> _createSemanticBackSurfaceProbeImage({
  required Size pageSize,
  required int pageIndex,
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(
    recorder,
    Rect.fromLTWH(0, 0, pageSize.width, pageSize.height),
  );
  final background = switch (pageIndex) {
    2 => const Color(0xFF00E5FF),
    3 => const Color(0xFFFFD600),
    _ => const Color(0xFF7C4DFF),
  };
  canvas.drawRect(
    Rect.fromLTWH(0, 0, pageSize.width, pageSize.height),
    Paint()..color = background,
  );
  canvas.drawRect(
    Rect.fromLTWH(0, 0, pageSize.width * 0.22, pageSize.height),
    Paint()..color = Colors.black,
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(
    pageSize.width.round(),
    pageSize.height.round(),
  );
  picture.dispose();
  return image;
}

Future<ui.Image> _createFrontSurfaceProbeImage({
  required Size pageSize,
  required int pageIndex,
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(
    recorder,
    Rect.fromLTWH(0, 0, pageSize.width, pageSize.height),
  );
  final background = switch (pageIndex) {
    2 => const Color(0xFFE53935),
    3 => const Color(0xFF43A047),
    _ => const Color(0xFF1E88E5),
  };
  canvas.drawRect(
    Rect.fromLTWH(0, 0, pageSize.width, pageSize.height),
    Paint()..color = background,
  );
  canvas.drawRect(
    Rect.fromLTWH(
      pageSize.width * 0.78,
      0,
      pageSize.width * 0.22,
      pageSize.height,
    ),
    Paint()..color = Colors.black,
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(
    pageSize.width.round(),
    pageSize.height.round(),
  );
  picture.dispose();
  return image;
}

Future<_ForwardProbeSample> _renderForwardProbeScene(WidgetTester _) async {
  const probeSurfaceSize = Size(480, 720);
  const probeDragDelta = Offset(-140, -16);
  final engine = PageflipEngine(pageCount: 4, initialPage: 1);
  const pageSize = Size(456, 456 / 0.72);
  engine.updateViewport(stageSize: probeSurfaceSize, pageSize: pageSize);
  final sceneBefore = engine.buildScene(probeSurfaceSize);
  expect(sceneBefore, isNotNull);

  final start = Offset(
    sceneBefore!.pageRect.right - 18,
    sceneBefore.pageRect.bottom - 18,
  );
  expect(engine.start(start), isTrue);
  engine.fold(start + probeDragDelta);
  final sceneAfter = engine.buildScene(probeSurfaceSize);
  expect(sceneAfter, isNotNull);
  expect(sceneAfter!.renderFrame, isNotNull);
  expect(sceneAfter.renderFrame!.direction, PageflipDirection.forward);
  final frame = sceneAfter.renderFrame!.canonicalFrame;

  var seenRed = false;
  var seenGreen = false;
  var firstRedX = -1;
  var firstGreenX = -1;
  var maxWhiteRun = 0;

  final scanlineOffsets = <double>[-0.18, 0.0, 0.18];
  for (final offsetFactor in scanlineOffsets) {
    final scanlineY = sceneAfter.pageSize.height * (0.5 + offsetFactor);
    final flippingInterval = _polygonScanlineInterval(
      frame.flippingClipArea,
      scanlineY,
    );
    final bottomInterval = _polygonScanlineInterval(
      frame.bottomClipArea,
      scanlineY,
    );
    if (flippingInterval == null || bottomInterval == null) {
      continue;
    }
    final redStart = flippingInterval.$1.round();
    final greenStart = bottomInterval.$1.round();
    final gap = (bottomInterval.$1 - flippingInterval.$2).ceil();

    seenRed = true;
    seenGreen = true;
    maxWhiteRun = math.max(maxWhiteRun, math.max(0, gap));
    if (offsetFactor == 0.0) {
      firstRedX = redStart;
      firstGreenX = greenStart;
    }
  }

  return _ForwardProbeSample(
    seenRed: seenRed,
    seenGreen: seenGreen,
    firstRedX: firstRedX,
    firstGreenX: firstGreenX,
    maxWhiteRun: maxWhiteRun,
  );
}

({double $1, double $2})? _polygonScanlineInterval(
  List<Offset> polygon,
  double scanlineY,
) {
  if (polygon.length < 3) {
    return null;
  }
  final xs = <double>[];
  for (var index = 0; index < polygon.length; index += 1) {
    final a = polygon[index];
    final b = polygon[(index + 1) % polygon.length];
    final minY = math.min(a.dy, b.dy);
    final maxY = math.max(a.dy, b.dy);
    if ((scanlineY < minY || scanlineY > maxY) || (a.dy == b.dy)) {
      continue;
    }
    final t = (scanlineY - a.dy) / (b.dy - a.dy);
    xs.add(a.dx + (b.dx - a.dx) * t);
  }
  if (xs.length < 2) {
    return null;
  }
  xs.sort();
  return ($1: xs.first, $2: xs.last);
}

Future<ui.Image> _captureBoundaryImage(GlobalKey boundaryKey) async {
  final context = boundaryKey.currentContext;
  expect(context, isNotNull);
  final renderObject = context!.findRenderObject();
  expect(renderObject, isA<RenderRepaintBoundary>());
  final boundary = renderObject as RenderRepaintBoundary;
  return boundary.toImage(pixelRatio: 1);
}

Future<Uint8List> _rawRgbaBytes(ui.Image image) async {
  final byteData = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  expect(byteData, isNotNull);
  return byteData!.buffer.asUint8List();
}

Color _colorAtBytes(
  int imageWidth,
  int imageHeight,
  Uint8List bytes,
  Offset offset,
) {
  final x = offset.dx.round().clamp(0, imageWidth - 1);
  final y = offset.dy.round().clamp(0, imageHeight - 1);
  final index = (y * imageWidth + x) * 4;
  return Color.fromARGB(
    bytes[index + 3],
    bytes[index],
    bytes[index + 1],
    bytes[index + 2],
  );
}

enum _ProbeColor { red, green, cyan, white, black, paperBack, other }

_ProbeColor _semanticBackProbeColor({
  required Size pageSize,
  required int pageIndex,
  required Offset localPoint,
}) {
  if (localPoint.dx <= pageSize.width * 0.18 ||
      localPoint.dx >= pageSize.width * 0.82) {
    return _ProbeColor.white;
  }
  if (localPoint.dx >= pageSize.width * 0.41 &&
      localPoint.dx <= pageSize.width * 0.59) {
    return _ProbeColor.black;
  }
  return switch (pageIndex) {
    2 => _ProbeColor.cyan,
    _ => _ProbeColor.other,
  };
}

_ProbeColor _frontProbeColor({
  required Size pageSize,
  required int pageIndex,
  required Offset localPoint,
}) {
  if (localPoint.dx >= pageSize.width * 0.78) {
    return _ProbeColor.black;
  }
  return switch (pageIndex) {
    2 => _ProbeColor.red,
    3 => _ProbeColor.green,
    _ => _ProbeColor.other,
  };
}

Map<_ProbeColor, int> _scanColorsInPolygon({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required List<Offset> polygon,
  double edgeInset = 0,
}) {
  final counts = <_ProbeColor, int>{};
  final rect = _polygonBounds(polygon);
  if (rect == null || rect.isEmpty) {
    return counts;
  }
  final left = rect.left.round().clamp(0, imageWidth - 1);
  final right = rect.right.round().clamp(left, imageWidth - 1);
  final top = rect.top.round().clamp(0, imageHeight - 1);
  final bottom = rect.bottom.round().clamp(top, imageHeight - 1);

  for (var y = top; y <= bottom; y += 3) {
    for (var x = left; x <= right; x += 3) {
      final point = Offset(x.toDouble(), y.toDouble());
      if (!_pointInPolygon(point, polygon)) {
        continue;
      }
      if (edgeInset > 0 &&
          _distanceToPolygonEdges(point, polygon) < edgeInset) {
        continue;
      }
      final color = _colorAtBytes(imageWidth, imageHeight, bytes, point);
      final probeColor = _classifyProbeColor(color);
      counts.update(probeColor, (count) => count + 1, ifAbsent: () => 1);
    }
  }
  return counts;
}

Map<_ProbeColor, int> _scanVisibleBackColors({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required List<Offset> backPolygon,
  required Rect? backBounds,
  required List<Offset> frontPolygon,
  List<List<Offset>> excludePolygons = const <List<Offset>>[],
}) {
  final polygon = backPolygon.length >= 3
      ? backPolygon
      : backBounds == null || backBounds.isEmpty
      ? const <Offset>[]
      : <Offset>[
          backBounds.topLeft,
          backBounds.topRight,
          backBounds.bottomRight,
          backBounds.bottomLeft,
        ];
  if (polygon.length < 3) {
    return const <_ProbeColor, int>{};
  }
  final bounds = polygonBounds(polygon);
  if (bounds == null || bounds.isEmpty) {
    return const <_ProbeColor, int>{};
  }
  final counts = <_ProbeColor, int>{};
  final left = math.max(0, bounds.left.floor());
  final top = math.max(0, bounds.top.floor());
  final right = math.min(imageWidth - 1, bounds.right.ceil());
  final bottom = math.min(imageHeight - 1, bounds.bottom.ceil());
  for (var y = top; y <= bottom; y += 1) {
    for (var x = left; x <= right; x += 1) {
      final point = Offset(x + 0.5, y + 0.5);
      if (!_pointInPolygon(point, polygon)) {
        continue;
      }
      if (frontPolygon.length >= 3 && _pointInPolygon(point, frontPolygon)) {
        continue;
      }
      if (excludePolygons.any((polygon) => _pointInPolygon(point, polygon))) {
        continue;
      }
      final color = _classifyProbeColor(
        _colorAtBytes(imageWidth, imageHeight, bytes, point),
      );
      counts.update(color, (count) => count + 1, ifAbsent: () => 1);
    }
  }
  return counts;
}

Map<_ProbeColor, int> _scanMovingSheetColors({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required List<Offset> backPolygon,
  required Rect? backBounds,
  required List<Offset> frontPolygon,
  required Rect? frontBounds,
}) {
  final polygons = <List<Offset>>[
    _polygonOrRect(backPolygon, backBounds),
    _polygonOrRect(frontPolygon, frontBounds),
  ].where((polygon) => polygon.length >= 3).toList(growable: false);
  if (polygons.isEmpty) {
    return const <_ProbeColor, int>{};
  }
  final bounds = polygonBounds(polygons.expand((polygon) => polygon).toList());
  if (bounds == null || bounds.isEmpty) {
    return const <_ProbeColor, int>{};
  }
  final counts = <_ProbeColor, int>{};
  final left = math.max(0, bounds.left.floor());
  final top = math.max(0, bounds.top.floor());
  final right = math.min(imageWidth - 1, bounds.right.ceil());
  final bottom = math.min(imageHeight - 1, bounds.bottom.ceil());
  for (var y = top; y <= bottom; y += 1) {
    for (var x = left; x <= right; x += 1) {
      final point = Offset(x + 0.5, y + 0.5);
      if (!polygons.any((polygon) => _pointInPolygon(point, polygon))) {
        continue;
      }
      final color = _classifyProbeColor(
        _colorAtBytes(imageWidth, imageHeight, bytes, point),
      );
      counts.update(color, (count) => count + 1, ifAbsent: () => 1);
    }
  }
  return counts;
}

List<Offset> _polygonOrRect(List<Offset> polygon, Rect? bounds) {
  if (polygon.length >= 3) {
    return polygon;
  }
  if (bounds == null || bounds.isEmpty) {
    return const <Offset>[];
  }
  return <Offset>[
    bounds.topLeft,
    bounds.topRight,
    bounds.bottomRight,
    bounds.bottomLeft,
  ];
}

bool _semanticBackColorMatches(_ProbeColor actual, _ProbeColor expected) {
  if (actual == expected) {
    return true;
  }
  return expected == _ProbeColor.white && actual == _ProbeColor.paperBack;
}

int _semanticBackVisiblePixels(Map<_ProbeColor, int> counts) {
  return (counts[_ProbeColor.cyan] ?? 0) +
      (counts[_ProbeColor.black] ?? 0) +
      (counts[_ProbeColor.white] ?? 0) +
      (counts[_ProbeColor.paperBack] ?? 0);
}

Rect? _polygonBounds(List<Offset> polygon) {
  if (polygon.isEmpty) {
    return null;
  }
  var left = polygon.first.dx;
  var top = polygon.first.dy;
  var right = left;
  var bottom = top;
  for (final point in polygon.skip(1)) {
    left = math.min(left, point.dx);
    top = math.min(top, point.dy);
    right = math.max(right, point.dx);
    bottom = math.max(bottom, point.dy);
  }
  return Rect.fromLTRB(left, top, right, bottom);
}

bool _pointInPolygon(Offset point, List<Offset> polygon) {
  if (polygon.length < 3) {
    return false;
  }
  var inside = false;
  for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    final pi = polygon[i];
    final pj = polygon[j];
    final crosses =
        ((pi.dy > point.dy) != (pj.dy > point.dy)) &&
        (point.dx <
            (pj.dx - pi.dx) *
                    (point.dy - pi.dy) /
                    ((pj.dy - pi.dy) + 0.000001) +
                pi.dx);
    if (crosses) {
      inside = !inside;
    }
  }
  return inside;
}

double _distanceToPolygonEdges(Offset point, List<Offset> polygon) {
  var minDistance = double.infinity;
  for (var index = 0; index < polygon.length; index += 1) {
    final start = polygon[index];
    final end = polygon[(index + 1) % polygon.length];
    final distance = _distanceToSegment(point, start, end);
    if (distance < minDistance) {
      minDistance = distance;
    }
  }
  return minDistance;
}

double _distanceToSegment(Offset point, Offset start, Offset end) {
  final dx = end.dx - start.dx;
  final dy = end.dy - start.dy;
  if (dx == 0 && dy == 0) {
    return (point - start).distance;
  }
  final t =
      (((point.dx - start.dx) * dx + (point.dy - start.dy) * dy) /
              (dx * dx + dy * dy))
          .clamp(0.0, 1.0)
          .toDouble();
  final projection = Offset(start.dx + dx * t, start.dy + dy * t);
  return (point - projection).distance;
}

int _colorChannelByte(double channel) {
  return (channel * 255.0).round().clamp(0, 255).toInt();
}

_ProbeColor _classifyProbeColor(Color color) {
  final red = _colorChannelByte(color.r);
  final green = _colorChannelByte(color.g);
  final blue = _colorChannelByte(color.b);
  if (red < 35 && green < 35 && blue < 35) {
    return _ProbeColor.black;
  }
  if (red > 235 && green > 235 && blue > 235) {
    return _ProbeColor.white;
  }
  if (green > red + 20 && blue > red + 20 && (green - blue).abs() < 70) {
    return _ProbeColor.cyan;
  }
  if (red > green + 40 && red > blue + 40) {
    return _ProbeColor.red;
  }
  if (green > red + 30 && green > blue + 20) {
    return _ProbeColor.green;
  }
  final maxChannel = math.max(red, math.max(green, blue));
  final minChannel = math.min(red, math.min(green, blue));
  if (minChannel > 120 && maxChannel - minChannel < 75) {
    return _ProbeColor.paperBack;
  }
  return _ProbeColor.other;
}

class _ForwardProbeSample {
  const _ForwardProbeSample({
    required this.seenRed,
    required this.seenGreen,
    required this.firstRedX,
    required this.firstGreenX,
    required this.maxWhiteRun,
  });

  final bool seenRed;
  final bool seenGreen;
  final int firstRedX;
  final int firstGreenX;
  final int maxWhiteRun;
}

class _BackwardVersoTextureProbeSample {
  const _BackwardVersoTextureProbeSample({
    required this.renderSceneReady,
    required this.sessionHasBundle,
    required this.backBandWidth,
    required this.backSurfaceStrategy,
    required this.activeRectoPageIndex,
    required this.activeVersoPageIndex,
    required this.activeBottomPageIndex,
    required this.activeVersoSurfaceKind,
    required this.versoDisplayState,
    required this.uvStrategy,
    required this.runtimeFailureReason,
    required this.probePointCount,
    required this.frontBackOverlapWidth,
    required this.backVisibleUncoveredWidth,
    required this.visibleProbeCount,
    required this.paintSources,
    required this.framebufferColorCountsBySource,
    required this.visibleBackColorCounts,
    required this.visibleBackPixelCount,
    required this.movingSheetColorCounts,
    required this.movingSheetPixelCount,
    required this.pageSize,
    required this.probeLocalPoints,
    required this.probeTexturePoints,
    required this.framebufferProbeColors,
    required this.framebufferBackActualColors,
    required this.framebufferBackExpectedColors,
    required this.framebufferBackExpectedAllColors,
    required this.framebufferFrontColors,
    required this.framebufferCurrentColors,
  });

  final bool renderSceneReady;
  final bool sessionHasBundle;
  final double backBandWidth;
  final String? backSurfaceStrategy;
  final int? activeRectoPageIndex;
  final int? activeVersoPageIndex;
  final int? activeBottomPageIndex;
  final String? activeVersoSurfaceKind;
  final String? versoDisplayState;
  final String? uvStrategy;
  final BackwardVersoFailureReason runtimeFailureReason;
  final int probePointCount;
  final double? frontBackOverlapWidth;
  final double? backVisibleUncoveredWidth;
  final int visibleProbeCount;
  final List<BackwardPaintSourceDiagnostic> paintSources;
  final Map<String, Map<_ProbeColor, int>> framebufferColorCountsBySource;
  final Map<_ProbeColor, int> visibleBackColorCounts;
  final int visibleBackPixelCount;
  final Map<_ProbeColor, int> movingSheetColorCounts;
  final int movingSheetPixelCount;
  final Size pageSize;
  final List<Offset> probeLocalPoints;
  final List<Offset> probeTexturePoints;
  final List<_ProbeColor> framebufferProbeColors;
  final List<_ProbeColor> framebufferBackActualColors;
  final List<_ProbeColor> framebufferBackExpectedColors;
  final List<_ProbeColor> framebufferBackExpectedAllColors;
  final List<_ProbeColor> framebufferFrontColors;
  final List<_ProbeColor> framebufferCurrentColors;
}

class _IPhone17ZeroAngleSample {
  const _IPhone17ZeroAngleSample({
    required this.label,
    required this.totalDx,
    required this.guideX,
    required this.clipBounds,
    required this.frontBounds,
    required this.backBounds,
    required this.versoFailureReason,
    required this.geometryFailureReason,
    required this.frontPolygonPoints,
    required this.backPolygonPoints,
    required this.sheetPolygonPoints,
    required this.bottomClipPolygonPoints,
    required this.sourceLabels,
    required this.staticCurrentFrontBounds,
    required this.bottomCurrentFrontBounds,
    required this.sheetPaintedUnionBounds,
    required this.sheetRectoFrontBounds,
    required this.sheetVersoBackBounds,
    required this.sampleCount,
    required this.backFree,
    required this.frontBackOverlap,
    required this.foldLine,
    required this.freeEdgeLine,
    required this.trace,
  });

  final String label;
  final double totalDx;
  final double? guideX;
  final Rect? clipBounds;
  final Rect? frontBounds;
  final Rect? backBounds;
  final BackwardVersoFailureReason versoFailureReason;
  final BackwardGeometryFailureReason geometryFailureReason;
  final String? frontPolygonPoints;
  final String? backPolygonPoints;
  final String? sheetPolygonPoints;
  final String? bottomClipPolygonPoints;
  final List<String> sourceLabels;
  final Rect? staticCurrentFrontBounds;
  final Rect? bottomCurrentFrontBounds;
  final Rect? sheetPaintedUnionBounds;
  final Rect? sheetRectoFrontBounds;
  final Rect? sheetVersoBackBounds;
  final int? sampleCount;
  final double? backFree;
  final double? frontBackOverlap;
  final (Offset, Offset)? foldLine;
  final (Offset, Offset)? freeEdgeLine;
  final _BackwardPartitionTrace? trace;

  String describe() {
    return '$label dx=${totalDx.toStringAsFixed(0)} '
        'guide=${guideX?.toStringAsFixed(1) ?? "-"} '
        'fail=${versoFailureReason.name}/${geometryFailureReason.name} '
        'clip=${_describeRect(clipBounds)} '
        'front=${_describeRect(frontBounds)} '
        'back=${_describeRect(backBounds)} '
        'sourceBack=${_describeRect(sheetVersoBackBounds)} '
        'sourceFront=${_describeRect(sheetRectoFrontBounds)} '
        'sourceUnion=${_describeRect(sheetPaintedUnionBounds)} '
        'samples=${sampleCount ?? "-"} '
        'backFree=${backFree?.toStringAsFixed(1) ?? "-"} '
        'frontBack=${frontBackOverlap?.toStringAsFixed(1) ?? "-"} '
        'fold=${_describeLine(foldLine)} '
        'free=${_describeLine(freeEdgeLine)} '
        'polys sheet=${sheetPolygonPoints ?? "-"} '
        'front=${frontPolygonPoints ?? "-"} '
        'back=${backPolygonPoints ?? "-"} '
        'bottom=${bottomClipPolygonPoints ?? "-"} '
        'trace=${trace?.describe() ?? "-"} '
        'sources=$sourceLabels';
  }
}

class _BackwardPartitionTrace {
  const _BackwardPartitionTrace({
    required this.progress,
    required this.angle,
    required this.visualGeometryDirection,
    required this.leafCoveredWidth,
    required this.leafRectoCoverage,
    required this.leafTotalRectoWidth,
    required this.leafVersoWidth,
  });

  final double progress;
  final double angle;
  final StPageFlipDirection visualGeometryDirection;
  final double? leafCoveredWidth;
  final double? leafRectoCoverage;
  final double? leafTotalRectoWidth;
  final double? leafVersoWidth;

  String describe() {
    return 'progress=${progress.toStringAsFixed(3)} '
        'angle=${angle.toStringAsFixed(3)} '
        'visual=${visualGeometryDirection.name} '
        'leaf covered=${leafCoveredWidth?.toStringAsFixed(3) ?? "-"} '
        'rectoCoverage=${leafRectoCoverage?.toStringAsFixed(3) ?? "-"} '
        'rectoW=${leafTotalRectoWidth?.toStringAsFixed(3) ?? "-"} '
        'versoW=${leafVersoWidth?.toStringAsFixed(3) ?? "-"}';
  }
}

String _describeRect(Rect? rect) {
  if (rect == null) {
    return '-';
  }
  return '${rect.left.toStringAsFixed(1)},${rect.top.toStringAsFixed(1)}'
      '->${rect.right.toStringAsFixed(1)},${rect.bottom.toStringAsFixed(1)}';
}

String _describeLine((Offset, Offset)? line) {
  if (line == null) {
    return '-';
  }
  return '${_describeOffset(line.$1)}>${_describeOffset(line.$2)}';
}

String _describeOffset(Offset offset) {
  return '${offset.dx.toStringAsFixed(1)},${offset.dy.toStringAsFixed(1)}';
}

class _BackwardCompletionSample {
  const _BackwardCompletionSample({
    required this.pageChanges,
    required this.finalPageIndex,
    required this.minimumObservedPageIndex,
    required this.sawDynamicBack,
    required this.sawStaticAfterDynamic,
    required this.finalRenderBranch,
    required this.finalRenderDirection,
    required this.lastDynamicFlippingPageIndex,
    required this.firstStaticAfterDynamicPageIndex,
    required this.lastDynamicUnifiedBackSourceLabels,
    required this.lastDynamicFrontSourceLabels,
  });

  final List<int> pageChanges;
  final int finalPageIndex;
  final int minimumObservedPageIndex;
  final bool sawDynamicBack;
  final bool sawStaticAfterDynamic;
  final ArticleReadOnlyBookRenderBranch finalRenderBranch;
  final StPageFlipDirection? finalRenderDirection;
  final int? lastDynamicFlippingPageIndex;
  final int? firstStaticAfterDynamicPageIndex;
  final List<String> lastDynamicUnifiedBackSourceLabels;
  final List<String> lastDynamicFrontSourceLabels;
}

class _BackwardCompositeProbeSample {
  const _BackwardCompositeProbeSample({
    required this.compositeMode,
    required this.bottomLayerPageIndex,
    required this.flippingLayerPageIndex,
    required this.backPixelSurfaceStrategy,
    required this.backSheetId,
    required this.baselineKeyVisible,
    required this.foldXSamples,
    required this.foldXAdvance,
    required this.latePoseCount,
    required this.latePoseSurfaceWidth,
    required this.latePoseBackWidth,
    required this.latePoseFrontWidth,
    required this.latePoseCurrentWidth,
    required this.latePoseBackVertexCount,
    required this.latePoseFrontSheetId,
    required this.latePoseBackSheetId,
  });

  final String compositeMode;
  final int? bottomLayerPageIndex;
  final int? flippingLayerPageIndex;
  final String? backPixelSurfaceStrategy;
  final String? backSheetId;
  final bool baselineKeyVisible;
  final List<double> foldXSamples;
  final double foldXAdvance;
  final int latePoseCount;
  final double latePoseSurfaceWidth;
  final double latePoseBackWidth;
  final double latePoseFrontWidth;
  final double latePoseCurrentWidth;
  final int latePoseBackVertexCount;
  final String? latePoseFrontSheetId;
  final String? latePoseBackSheetId;
}

class _BackwardGeometrySweepSample {
  const _BackwardGeometrySweepSample({
    required this.corner,
    required this.angleDegrees,
    required this.depth,
    required this.failureReason,
    required this.compositeMode,
    required this.backWidth,
    required this.currentWidth,
    required this.renderSceneReady,
    required this.sessionHasBundle,
    required this.activeRectoPageIndex,
    required this.activeVersoPageIndex,
    required this.activeBottomPageIndex,
    required this.activeVersoSurfaceKind,
    required this.versoDisplayState,
  });

  final ArticlePageCurlCorner corner;
  final double angleDegrees;
  final double depth;
  final BackwardGeometryFailureReason failureReason;
  final String? compositeMode;
  final double backWidth;
  final double currentWidth;
  final bool renderSceneReady;
  final bool sessionHasBundle;
  final int? activeRectoPageIndex;
  final int? activeVersoPageIndex;
  final int? activeBottomPageIndex;
  final String? activeVersoSurfaceKind;
  final String? versoDisplayState;

  String describe() {
    return 'corner=${corner.name} angle=${angleDegrees.toStringAsFixed(1)} '
        'depth=${depth.toStringAsFixed(1)} '
        'reason=${failureReason.name} '
        'mode=${compositeMode ?? "-"} '
        'backWidth=${backWidth.toStringAsFixed(1)} '
        'currentWidth=${currentWidth.toStringAsFixed(1)} '
        'render=$renderSceneReady '
        'bundle=$sessionHasBundle '
        'act=$activeRectoPageIndex/$activeVersoPageIndex/$activeBottomPageIndex '
        'verso=${activeVersoSurfaceKind ?? "-"}/${versoDisplayState ?? "-"}';
  }
}
