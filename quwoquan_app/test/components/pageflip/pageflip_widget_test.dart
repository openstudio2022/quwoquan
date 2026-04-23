import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/backward_leaf_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

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
      findsOneWidget,
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
    'PageflipDiagnosticsApp keeps ArticleReadOnlyBookDeck size stable after debug overlay appears',
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
        findsOneWidget,
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
      expect(find.byType(ArticlePageBackwardLeafRenderer), findsNothing);
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
    'PageflipDiagnosticsApp backward is frozen on genericDynamic legacy branch',
    (WidgetTester tester) async {
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
      expect(
        interactiveState.renderBranch,
        ArticleReadOnlyBookRenderBranch.genericDynamic,
      );

      await gesture.up();
    },
  );

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
    // toImage/scanline probe 在部分环境会长时间卡住；主修复跟进中，恢复后删除 skip
    skip: true,
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
    // 同 a.，依赖 _renderForwardProbeScene；与 a. 一并恢复
    skip: true,
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

Future<_ForwardProbeSample> _renderForwardProbeScene(
  WidgetTester tester,
) async {
  const probeSurfaceSize = Size(480, 720);
  const probeDragDelta = Offset(-140, -16);

  await tester.binding.setSurfaceSize(probeSurfaceSize);
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final boundaryKey = GlobalKey();
  final engine = PageflipEngine(pageCount: 4, initialPage: 1);
  final pages = <Color>[
    const Color(0xFFE53935),
    const Color(0xFFE53935),
    const Color(0xFF43A047),
    const Color(0xFF1E88E5),
  ];

  await tester.pumpWidget(
    MaterialApp(
      home: RepaintBoundary(
        key: boundaryKey,
        child: SizedBox.expand(
          child: PageflipWidget(
            engine: engine,
            pageBuilder: (context, pageIndex) {
              return ColoredBox(
                color: pages[pageIndex],
                child: const SizedBox.expand(),
              );
            },
          ),
        ),
      ),
    ),
  );

  for (var i = 0; i < 6; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  final sceneBefore = engine.buildScene(probeSurfaceSize);
  expect(sceneBefore, isNotNull);

  final start = Offset(
    sceneBefore!.pageRect.right - 18,
    sceneBefore.pageRect.bottom - 18,
  );
  final gesture = await tester.startGesture(start);
  await gesture.moveBy(probeDragDelta);
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final sceneAfter = engine.buildScene(probeSurfaceSize);
  expect(sceneAfter, isNotNull);
  expect(sceneAfter!.renderFrame, isNotNull);
  expect(sceneAfter.renderFrame!.direction, PageflipDirection.forward);

  final image = await _captureBoundaryImage(boundaryKey);
  final bytes = await _rawRgbaBytes(image);
  final left = sceneAfter.pageRect.left.round();
  final right = sceneAfter.pageRect.right.round();

  var seenRed = false;
  var seenGreen = false;
  var firstRedX = -1;
  var firstGreenX = -1;
  var maxWhiteRun = 0;

  final scanlineOffsets = <double>[-0.18, 0.0, 0.18];
  for (final offsetFactor in scanlineOffsets) {
    final scanline =
        (sceneAfter.pageRect.center.dy +
                sceneAfter.pageRect.height * offsetFactor)
            .round();
    final result = _scanForwardLine(
      imageWidth: image.width,
      imageHeight: image.height,
      bytes: bytes,
      left: left,
      right: right,
      scanlineY: scanline,
    );
    seenRed = seenRed || result.seenRed;
    seenGreen = seenGreen || result.seenGreen;
    maxWhiteRun = result.maxWhiteRun > maxWhiteRun
        ? result.maxWhiteRun
        : maxWhiteRun;
    if (offsetFactor == 0.0) {
      firstRedX = result.firstRedX;
      firstGreenX = result.firstGreenX;
    }
  }

  await gesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));

  return _ForwardProbeSample(
    seenRed: seenRed,
    seenGreen: seenGreen,
    firstRedX: firstRedX,
    firstGreenX: firstGreenX,
    maxWhiteRun: maxWhiteRun,
  );
}

_ScanlineProbeResult _scanForwardLine({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required int left,
  required int right,
  required int scanlineY,
}) {
  var seenRed = false;
  var seenGreen = false;
  var firstRedX = -1;
  var firstGreenX = -1;
  var whiteRun = 0;
  var maxWhiteRun = 0;

  for (var x = left; x <= right; x += 1) {
    final color = _colorAtBytes(
      imageWidth,
      imageHeight,
      bytes,
      Offset(x.toDouble(), scanlineY.toDouble()),
    );
    final classification = _classifyProbeColor(color);
    if (classification == _ProbeColor.red) {
      seenRed = true;
      firstRedX = firstRedX < 0 ? x : firstRedX;
    }
    if (classification == _ProbeColor.green) {
      seenGreen = true;
      firstGreenX = firstGreenX < 0 ? x : firstGreenX;
    }
    if (seenRed && classification == _ProbeColor.white) {
      whiteRun += 1;
      maxWhiteRun = whiteRun > maxWhiteRun ? whiteRun : maxWhiteRun;
    } else {
      whiteRun = 0;
    }
  }

  return _ScanlineProbeResult(
    seenRed: seenRed,
    seenGreen: seenGreen,
    firstRedX: firstRedX,
    firstGreenX: firstGreenX,
    maxWhiteRun: maxWhiteRun,
  );
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

enum _ProbeColor { red, green, white, other }

_ProbeColor _classifyProbeColor(Color color) {
  if (color.red > 235 && color.green > 235 && color.blue > 235) {
    return _ProbeColor.white;
  }
  if (color.red > color.green + 40 && color.red > color.blue + 40) {
    return _ProbeColor.red;
  }
  if (color.green > color.red + 30 && color.green > color.blue + 20) {
    return _ProbeColor.green;
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

class _ScanlineProbeResult {
  const _ScanlineProbeResult({
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
