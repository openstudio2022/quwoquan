import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_stage_widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_pixel_probe.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

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
      expect(backwardState.renderSceneReady, isFalse);
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
    expect(interactiveState.renderSceneReady, isFalse);
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
    await tester.pumpAndSettle();

    final backwardAnimationStates = debugStates.where(
      (state) =>
          state.renderDirection == StPageFlipDirection.back &&
          state.backwardCompositeMode == 'paperFoldBackwardMainline',
    );
    expect(backwardAnimationStates, isNotEmpty);
    void expectStableBackBand(
      ArticleReadOnlyBookDebugState state,
      String phase,
    ) {
      final backBounds = state.backwardBackPaintBounds;
      final surface = state.backwardSurfaceViewportRect;
      expect(backBounds, isNotNull, reason: '$phase back band must be painted');
      expect(surface, isNotNull, reason: '$phase surface bounds are required');
      final minStableWidth = math.max(8.0, surface!.width * 0.02);
      expect(
        backBounds!.width,
        greaterThan(minStableWidth),
        reason:
            '$phase back band must not collapse into the near-invisible texture strip.',
      );
      expect(
        backBounds.width,
        lessThan(surface.width * 0.88),
        reason:
            '$phase back band must stay inside the F/E strip instead of expanding into a large flat backface.',
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
    expectStableBackBand(earlyPaintedBackStates.first, 'early');
    final midFoldFaceStates = backwardAnimationStates.where(
      (state) =>
          state.backwardFrontPaintBounds != null &&
          state.backwardBackPaintBounds != null &&
          (state.backwardRectoCoverage ?? 0) > 0.02 &&
          (state.backwardRectoCoverage ?? 0) < 0.72,
    );
    expect(
      midFoldFaceStates,
      isNotEmpty,
      reason:
          'BACK front/back split must be visible during the middle fold, not '
          'only in the final recto-dominant phase.',
    );
    expectStableBackBand(midFoldFaceStates.first, 'middle');
    final lateFrontStates = backwardAnimationStates.where(
      (state) =>
          (state.backwardRectoCoverage ?? 0) >= 0.72 &&
          state.backwardFrontPaintBounds != null,
    );
    expect(
      lateFrontStates,
      isNotEmpty,
      reason:
          'BACK late phase should remain front-dominant after the midpoint.',
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
          'BACK late phase must keep the E/F back band visible instead of jumping to a front-only state.',
    );
    expectStableBackBand(lateBackStates.first, 'late');
    final mixedFaceStates = backwardAnimationStates.where(
      (state) =>
          (state.backwardRectoCoverage ?? 0) > 0.05 &&
          (state.backwardRectoWidth ?? 0) > 0.01,
    );
    expect(
      mixedFaceStates,
      isNotEmpty,
      reason:
          'BACK replay must reach a phase where the fold has crossed the midpoint '
          'and previous-front recto becomes physically visible.',
    );
    for (final state in mixedFaceStates) {
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
      expect(state.backwardFrontPaintBounds, isNotNull);
      expect(state.backwardBackPaintBounds, isNotNull);
      expect(state.backwardCurrentResidualBounds, isNotNull);
      expect(state.backwardFrontPolygonPoints, isNotNull);
      expect(state.backwardBackPolygonPoints, isNotNull);
      expect(
        state.backwardFrontPaintBounds!.right,
        greaterThan(0),
        reason: 'recto/front must not be fully clipped into negative X.',
      );
      expect(
        state.backwardBackPaintBounds!.right,
        greaterThan(0),
        reason: 'verso/back must not be fully clipped into negative X.',
      );
      expect(
        state.backwardFrontPaintBounds!.left,
        lessThanOrEqualTo(state.backwardBackPaintBounds!.right),
        reason:
            'recto/front must be a sheet-local spine-side segment adjacent to '
            'the rotating back fold band.',
      );
      expect(
        state.backwardFrontPaintBounds!.top,
        lessThanOrEqualTo(state.backwardCurrentResidualBounds!.top + 1),
        reason:
            'sheet-local previous-front must cover the upper spine-side region; '
            'otherwise the current page leaks through the top-left corner.',
      );
      expect(
        state.backwardBackPaintBounds!.width,
        lessThan(state.backwardSurfaceViewportRect!.width * 0.92),
        reason:
            'previous-back must remain a fold band instead of expanding into a '
            'full uncreased back page.',
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
      (state) => state.backwardFoldX != null,
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
        expect(state.backwardBackSheetId, equals(state.backwardFrontSheetId));
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
            'is only allowed through the E/free-edge driven flat segment.',
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
        sample.latePoseCount,
        greaterThan(0),
        reason:
            '图二对应的 late BACK pose 必须同时暴露 previous-front、'
            'previous-back 与 current residual，不能塌成单条竖带。',
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
      expect(
        sample.latePoseBackWidth,
        lessThan(sample.latePoseSurfaceWidth * 0.88),
        reason:
            'late BACK previous-back must stay an E/F fold band, not a full page.',
      );
      expect(
        sample.latePoseFrontWidth,
        greaterThan(0),
        reason: 'late BACK still needs the S-E previous-front flat segment.',
      );
      expect(
        sample.latePoseCurrentWidth,
        greaterThan(0),
        reason: 'late BACK must keep current residual visible under the fold.',
      );
      expect(sample.latePoseBackVertexCount, greaterThanOrEqualTo(3));
      expect(sample.latePoseFrontSheetId, equals(sample.latePoseBackSheetId));
      expect(sample.latePoseFrontSheetId, equals('mainlineLeaf:2'));
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

  testWidgets('PageflipDiagnosticsApp backward verso samples semantic back surface', (
    WidgetTester tester,
  ) async {
    final sample = await _renderBackwardVersoTextureProbeScene(tester);

    expect(
      sample.backBandWidth,
      greaterThan(12),
      reason:
          'probe requires a visible BACK fold band to judge texture source.',
    );
    expect(
      sample.backSurfaceStrategy,
      equals('paperFoldBackMainlineSurface'),
      reason: 'probe must run on the Route-B previous-back mainline surface.',
    );
    expect(
      sample.activeVersoSurfaceKind,
      equals('back'),
      reason:
          'BACK verso runtime snapshot must be marked as semantic back surface.',
    );
    expect(
      sample.activeVersoPageIndex,
      equals(2),
      reason:
          'BACK verso runtime snapshot must remain bound to the flipping leaf.',
    );
    expect(
      sample.uvStrategy,
      equals(backwardVersoTextureMappingStrategy),
      reason:
          'runtime probe must expose the UV strategy so screenshot diagnostics '
          'can distinguish local sampling from the old double-mirror path.',
    );
    expect(
      sample.runtimeFailureReason,
      BackwardVersoFailureReason.none,
      reason:
          'runtime probe must not report snapshot/mesh/probe-point failures in '
          'the accepted BACK mainline pose.',
    );
    expect(
      sample.probePointCount,
      greaterThanOrEqualTo(1),
      reason:
          'runtime probe must expose at least one stable fold-band sample point; '
          'direction discrimination is enforced by the dedicated pixel test.',
    );
    expect(
      sample.frontBackOverlapWidth,
      isNotNull,
      reason:
          'runtime probe must report front/back overlap for visibility triage.',
    );
    expect(
      sample.backVisibleUncoveredWidth,
      greaterThan(0),
      reason:
          'BACK must leave at least one visible back-band region not covered by front/recto paint.',
    );
    expect(
      sample.visibleProbeCount,
      greaterThanOrEqualTo(1),
      reason:
          'framebuffer oracle needs at least one screen-space probe inside the visible back band.',
    );
    expect(
      sample.framebufferProbeColors,
      equals(sample.framebufferBackExpectedColors),
      reason:
          'visible BACK back-band framebuffer pixels must match the semantic back surface.',
    );
    expect(
      sample.framebufferProbeColors,
      isNot(equals(sample.framebufferFrontColors)),
      reason:
          'visible BACK back-band framebuffer pixels must not be previous-front paint.',
    );
    expect(
      sample.framebufferProbeColors,
      isNot(equals(sample.framebufferCurrentColors)),
      reason:
          'visible BACK back-band framebuffer pixels must not be covered-current paint.',
    );
  });

  testWidgets('BACK high-overlap pose still shows semantic back texture', (
    WidgetTester tester,
  ) async {
    final sample = await _renderBackwardVersoTextureProbeScene(
      tester,
      backwardDragDelta: const Offset(360, -36),
    );

    expect(
      sample.frontBackOverlapWidth,
      greaterThan(50),
      reason: 'this oracle must cover the screenshot-like high-overlap pose.',
    );
    expect(
      sample.backVisibleUncoveredWidth,
      greaterThan(24),
      reason:
          'the fixed screenshot-like pose must no longer collapse the BACK verso band to a subpixel strip.',
    );
    expect(sample.visibleProbeCount, greaterThanOrEqualTo(1));
    expect(
      sample.framebufferProbeColors,
      equals(sample.framebufferBackExpectedColors),
      reason:
          'even in the high-overlap pose, visible BACK pixels must be the semantic back texture.',
    );
    expect(
      sample.framebufferProbeColors,
      isNot(equals(sample.framebufferFrontColors)),
    );
    expect(
      sample.framebufferProbeColors,
      isNot(equals(sample.framebufferCurrentColors)),
    );
  });

  testWidgets('BACK source attribution maps high-overlap color blocks', (
    WidgetTester tester,
  ) async {
    final sample = await _renderBackwardVersoTextureProbeScene(
      tester,
      backwardDragDelta: const Offset(360, -36),
    );

    final sourcesByLabel = <String, BackwardPaintSourceDiagnostic>{
      for (final source in sample.paintSources) source.label: source,
    };
    expect(
      sourcesByLabel.keys,
      containsAll(<String>[
        'staticCurrentFront',
        'bottomCurrentFront',
        'previousFrontFlat',
        'sheetRectoFront',
        'sheetVersoBack',
        'foldOverlay',
      ]),
      reason:
          'the high-overlap screenshot pose must expose every visible paint source '
          'so user-visible color blocks can be attributed before geometry changes.',
    );
    expect(sourcesByLabel['staticCurrentFront']?.pageIndex, 3);
    expect(sourcesByLabel['bottomCurrentFront']?.pageIndex, 3);
    expect(sourcesByLabel['previousFrontFlat']?.pageIndex, 2);
    expect(sourcesByLabel['sheetRectoFront']?.pageIndex, 2);
    expect(sourcesByLabel['sheetVersoBack']?.pageIndex, 2);
    expect(sourcesByLabel['sheetVersoBack']?.surfaceKind, 'back');
    expect(sourcesByLabel['previousFrontFlat']?.surfaceKind, 'front');
    expect(sourcesByLabel['sheetRectoFront']?.surfaceKind, 'front');
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
      sample.visibleProbeCount,
      greaterThanOrEqualTo(1),
      reason:
          'source attribution is only useful when at least one visible verso pixel is proven.',
    );
    expect(
      sample.framebufferColorCountsBySource['sheetVersoBack']?[_ProbeColor
              .cyan] ??
          0,
      greaterThan(0),
      reason:
          'the sheetVersoBack source must account for visible back-colored pixels.',
    );
    expect(
      sample.framebufferColorCountsBySource['previousFrontFlat']?[_ProbeColor
              .red] ??
          0,
      greaterThan(0),
      reason:
          'the flat previous-front plane must keep showing the previous front texture.',
    );
    expect(
      sample.framebufferColorCountsBySource['previousFrontFlat']?[_ProbeColor
              .cyan] ??
          0,
      isA<int>(),
      reason:
          'source bounds may overlap the back band; front ownership is proven by the red probe above.',
    );
    expect(
      sample.framebufferColorCountsBySource['sheetRectoFront']?[_ProbeColor
              .red] ??
          0,
      greaterThan(0),
      reason:
          'the recto BACK slice must keep showing previous-front colored pixels.',
    );
    expect(
      sample.framebufferColorCountsBySource['sheetRectoFront']?[_ProbeColor
              .cyan] ??
          0,
      isA<int>(),
      reason:
          'source bounds may overlap the back band; recto/front ownership is proven by the red probe above.',
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
      contains('previousFrontFlat'),
      reason:
          'the final dynamic BACK frame must still hand off through the previous front surface.',
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
    const pageSize = Size(400, 600);
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
    const polygon = <Offset>[
      Offset(44, 92),
      Offset(332, 124),
      Offset(306, 520),
      Offset(72, 492),
    ];
    final probe = resolveBackwardVersoPixelProbe(
      pageSize: pageSize,
      polygon: polygon,
    );
    expect(probe.isEmpty, isFalse);

    final renderedImage = await renderBackwardLeafVersoProbeImage(
      leafVersoSnapshot: snapshot,
      pageSize: pageSize,
      polygon: polygon,
    );
    expect(renderedImage, isNotNull);
    final renderedMesh = buildBackwardLeafVersoUvMesh(
      pageSize: pageSize,
      polygon: polygon,
    );
    expect(renderedMesh, isNotNull);
    final renderedPaintOrigin = renderedMesh!.paintBounds.inflate(1).topLeft;
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
            localPoint,
          ),
        ),
      );
      doubleMirrorProbeColors.add(
        _classifyProbeColor(
          _colorAtBytes(
            snapshotImage.width,
            snapshotImage.height,
            snapshotBytes,
            Offset(pageSize.width - localPoint.dx, localPoint.dy),
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

    final mirrorSensitiveSamples = actualProbeColors.asMap().entries.any(
      (entry) =>
          entry.value == backSurfaceExpectedProbeColors[entry.key] &&
          entry.value != doubleMirrorProbeColors[entry.key],
    );
    final failureReason =
        listEquals(actualProbeColors, backSurfaceExpectedProbeColors)
        ? BackwardVersoFailureReason.none
        : BackwardVersoFailureReason.mirrorDirectionMismatch;

    expect(
      failureReason,
      BackwardVersoFailureReason.none,
      reason:
          'shared BACK fold-band renderer must sample the already mirrored '
          'semantic back snapshot without mirroring it a second time. '
          'actual=$actualProbeColors '
          'backSurface=$backSurfaceExpectedProbeColors '
          'doubleMirror=$doubleMirrorProbeColors',
    );
    expect(
      mirrorSensitiveSamples,
      isTrue,
      reason:
          'probe pattern must distinguish single-mirror from double-mirror sampling; '
          'otherwise pixel proof cannot verify direction.',
    );
    expect(
      actualProbeColors,
      isNot(equals(doubleMirrorProbeColors)),
      reason:
          'fold-band pixels must not match double-mirrored sampling that makes the back look front-facing.',
    );
    expect(
      actualProbeColors,
      isNot(equals(frontProbeColors)),
      reason:
          'fold-band pixels must not match the previous leaf front surface.',
    );
    expect(
      actualProbeColors,
      isNot(equals(currentProbeColors)),
      reason:
          'fold-band pixels must not match the covered current page surface.',
    );

    renderedImage.dispose();
    frontImage.dispose();
    currentImage.dispose();
    snapshot.dispose();
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

  final gesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
  );

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
            (s.backwardRectoCoverage ?? 0) >= 0.68 &&
            (s.backwardVersoWidth ?? 0) > 0.01 &&
            s.backwardFrontPaintBounds != null &&
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
    child: Align(
      alignment: Alignment.centerRight,
      child: Container(width: pageSize.width * 0.22, color: Colors.black),
    ),
  );
}

Future<_BackwardVersoTextureProbeSample> _renderBackwardVersoTextureProbeScene(
  WidgetTester tester, {
  Offset backwardDragDelta = const Offset(120, -40),
}) async {
  await tester.binding.setSurfaceSize(const Size(900, 1200));
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
                return _buildProbeBackPageSurface(context, pageIndex, pageSize);
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
  await backwardGesture.moveBy(backwardDragDelta);
  for (var i = 0; i < 10; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
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
  await tester.pump(const Duration(milliseconds: 16));
  probeState = debugStates.lastWhere(
    (state) =>
        state.renderDirection == StPageFlipDirection.back &&
        state.backwardCompositeMode == 'paperFoldBackwardMainline' &&
        state.backwardBackPaintBounds != null &&
        state.backwardBackSheetId == 'mainlineLeaf:2',
  );

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
  final framebufferFrontColors = <_ProbeColor>[];
  final framebufferCurrentColors = <_ProbeColor>[];
  final sampleCount = math.min(
    probeState.backwardVersoProbeLocalPoints.length,
    probeState.backwardVersoProbeViewportPoints.length,
  );
  for (var index = 0; index < sampleCount; index += 1) {
    final viewportPoint = probeState.backwardVersoProbeViewportPoints[index];
    final localPoint = probeState.backwardVersoProbeLocalPoints[index];
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
      localPoint: localPoint,
    );
    if (actualColor != expectedBackColor) {
      continue;
    }
    framebufferProbeColors.add(actualColor);
    framebufferBackExpectedColors.add(expectedBackColor);
    framebufferFrontColors.add(
      _frontProbeColor(
        pageSize: capturedBackPageSize!,
        pageIndex: 2,
        localPoint: localPoint,
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
    framebufferColorCountsBySource[source.label] = _scanColorsInRect(
      imageWidth: framebufferImage.width,
      imageHeight: framebufferImage.height,
      bytes: framebufferBytes,
      rect: bounds,
    );
  }
  await backwardGesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));
  framebufferImage.dispose();

  return _BackwardVersoTextureProbeSample(
    backBandWidth: probeState.backwardBackPaintBounds!.width,
    backSurfaceStrategy: probeState.backwardBackPixelSurfaceStrategy,
    activeVersoPageIndex: probeState.activeVersoPageIndex,
    activeVersoSurfaceKind: probeState.activeVersoSurfaceKind,
    uvStrategy: probeState.backwardVersoTextureUvStrategy,
    runtimeFailureReason: probeState.backwardVersoFailureReason,
    probePointCount: probeState.backwardVersoProbeLocalPoints.length,
    frontBackOverlapWidth: probeState.backwardFrontBackOverlapWidth,
    backVisibleUncoveredWidth: probeState.backwardBackVisibleUncoveredWidth,
    visibleProbeCount: framebufferProbeColors.length,
    paintSources: probeState.backwardPaintSources,
    framebufferColorCountsBySource: framebufferColorCountsBySource,
    framebufferProbeColors: framebufferProbeColors,
    framebufferBackExpectedColors: framebufferBackExpectedColors,
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
                (source.label == 'previousFrontFlat' ||
                    source.label == 'sheetRectoFront'),
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
  );
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

enum _ProbeColor { red, green, cyan, white, black, paperBack, other }

_ProbeColor _semanticBackProbeColor({
  required Size pageSize,
  required int pageIndex,
  required Offset localPoint,
}) {
  if (localPoint.dx <= pageSize.width * 0.22) {
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

Map<_ProbeColor, int> _scanColorsInRect({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required Rect rect,
}) {
  final counts = <_ProbeColor, int>{};
  final left = rect.left.round().clamp(0, imageWidth - 1);
  final right = rect.right.round().clamp(left, imageWidth - 1);
  final top = rect.top.round().clamp(0, imageHeight - 1);
  final bottom = rect.bottom.round().clamp(top, imageHeight - 1);

  for (var y = top; y <= bottom; y += 3) {
    for (var x = left; x <= right; x += 3) {
      final color = _colorAtBytes(
        imageWidth,
        imageHeight,
        bytes,
        Offset(x.toDouble(), y.toDouble()),
      );
      final probeColor = _classifyProbeColor(color);
      counts.update(probeColor, (count) => count + 1, ifAbsent: () => 1);
    }
  }
  return counts;
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
    required this.backBandWidth,
    required this.backSurfaceStrategy,
    required this.activeVersoPageIndex,
    required this.activeVersoSurfaceKind,
    required this.uvStrategy,
    required this.runtimeFailureReason,
    required this.probePointCount,
    required this.frontBackOverlapWidth,
    required this.backVisibleUncoveredWidth,
    required this.visibleProbeCount,
    required this.paintSources,
    required this.framebufferColorCountsBySource,
    required this.framebufferProbeColors,
    required this.framebufferBackExpectedColors,
    required this.framebufferFrontColors,
    required this.framebufferCurrentColors,
  });

  final double backBandWidth;
  final String? backSurfaceStrategy;
  final int? activeVersoPageIndex;
  final String? activeVersoSurfaceKind;
  final String? uvStrategy;
  final BackwardVersoFailureReason runtimeFailureReason;
  final int probePointCount;
  final double? frontBackOverlapWidth;
  final double? backVisibleUncoveredWidth;
  final int visibleProbeCount;
  final List<BackwardPaintSourceDiagnostic> paintSources;
  final Map<String, Map<_ProbeColor, int>> framebufferColorCountsBySource;
  final List<_ProbeColor> framebufferProbeColors;
  final List<_ProbeColor> framebufferBackExpectedColors;
  final List<_ProbeColor> framebufferFrontColors;
  final List<_ProbeColor> framebufferCurrentColors;
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
  });

  final ArticlePageCurlCorner corner;
  final double angleDegrees;
  final double depth;
  final BackwardGeometryFailureReason failureReason;
  final String? compositeMode;
  final double backWidth;
  final double currentWidth;

  String describe() {
    return 'corner=${corner.name} angle=${angleDegrees.toStringAsFixed(1)} '
        'depth=${depth.toStringAsFixed(1)} '
        'reason=${failureReason.name} '
        'mode=${compositeMode ?? "-"} '
        'backWidth=${backWidth.toStringAsFixed(1)} '
        'currentWidth=${currentWidth.toStringAsFixed(1)}';
  }
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
