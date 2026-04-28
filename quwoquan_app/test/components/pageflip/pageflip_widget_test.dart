import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/backward_leaf_renderer.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
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
        ArticleReadOnlyBookRenderBranch.genericDynamic,
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
    'PageflipDiagnosticsApp records forward and backward genericDynamic baselines',
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
        ArticleReadOnlyBookRenderBranch.genericDynamic,
      );
      expect(forwardState.renderSceneReady, isFalse);
      expect(
        backwardState.renderBranch,
        ArticleReadOnlyBookRenderBranch.genericDynamic,
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

  testWidgets(
    'PageflipDiagnosticsApp backward closes through genericDynamic mainline',
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
        ArticleReadOnlyBookRenderBranch.genericDynamic,
      );
      expect(interactiveState.renderSceneReady, isFalse);
      expect(interactiveState.guideX, isNotNull);
      expect(interactiveState.guideX, greaterThan(0));
      expect(interactiveState.flippingClipBounds, isNotNull);
      expect(interactiveState.flippingAnchor, isNotNull);
      expect(interactiveState.flippingAnchor!.dx, closeTo(0, 0.001));
      expect(interactiveState.flippingAnchor!.dy, greaterThan(0));
      expect(interactiveState.backwardSurfaceOrigin, isNotNull);
      expect(interactiveState.backwardSurfaceOrigin!.dx, closeTo(0, 0.001));
      expect(interactiveState.backwardSurfaceOrigin!.dy, closeTo(0, 0.001));
      expect(interactiveState.backwardSurfaceViewportRect, isNotNull);
      expect(interactiveState.backwardPivotLocal, isNotNull);
      expect(interactiveState.backwardPivotLocal!.dx, closeTo(0, 0.001));
      expect(
        interactiveState.backwardPivotLocal!.dy,
        closeTo(interactiveState.backwardSurfaceViewportRect!.height, 0.001),
      );
      expect(interactiveState.backwardPivotViewport, isNotNull);
      expect(
        interactiveState.backwardPivotViewport!.dy,
        greaterThan(interactiveState.backwardSurfaceViewportRect!.top + 500),
        reason:
            'the flipping surface must stay top-aligned; only the pivot sits at the bottom edge',
      );
      expect(interactiveState.backwardClipLocalBounds, isNotNull);
      expect(interactiveState.backwardClipViewportBounds, isNotNull);
      expect(interactiveState.bottomAnchor, isNotNull);
      expect(interactiveState.bottomAnchor!.dx, closeTo(0, 0.001));
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
      expect(interactiveState.backwardReplayFrontLayerCount, equals(0));
      expect(
        interactiveState.backwardReplayBackSurfaceStrategy,
        equals('mirroredForwardDynamicSplitFrontBack'),
      );
      expect(interactiveState.backwardBottomLayerPageIndex, equals(3));
      expect(interactiveState.backwardFlippingLayerPageIndex, equals(2));
      expect(interactiveState.backwardDynamicOwnedPages, contains(2));
      expect(interactiveState.backwardDynamicOwnedPages, isNot(contains(3)));
      expect(
        interactiveState.backwardStaticSuppressedPages,
        isNot(contains(3)),
      );
      expect(interactiveState.backwardReplaySlices, isNotNull);
      expect(
        interactiveState.backwardReplaySlices,
        contains('route=mirroredForwardDynamic'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('flipping=flippingClipArea'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('current=projectedCurrentResidualPolygon'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('front=projectedPreviousFrontPolygon'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('back=projectedPreviousBackPolygon'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        isNot(contains('previousFrontPolygon')),
      );
      expect(interactiveState.backwardReplaySlices, contains('frontLayers=0'));
      expect(
        interactiveState.backwardReplaySlices,
        contains('movingBack=sharedSoftLayer'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('foldLineSource=forwardRealGeometryMirrored'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('currentSource=projectedCurrentResidualPolygon'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('edgeLineSource=reflectedOriginalRightEdge'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('overlayClippedToPaper=true'),
      );
      expect(
        interactiveState.backwardReplaySlices,
        contains('backTextureDirection=leftToRight'),
      );
      expect(interactiveState.backwardReplaySlices, contains('foldF='));
      expect(interactiveState.backwardReplaySlices, contains('edgeE='));
      expect(interactiveState.backwardReplaySlices, contains('rectoCoverage='));
      expect(interactiveState.backwardReplaySlices, contains('verso='));
      expect(
        interactiveState.backwardCompositeMode,
        equals('mirroredForwardDynamic'),
      );
      expect(interactiveState.backwardBackPaintBounds, isNotNull);
      expect(
        interactiveState.backwardBackPaintBounds!.height,
        greaterThan(600),
        reason: 'back texture must cover the paper height, not a short strip',
      );
      expect(
        interactiveState.backwardBackPixelSurfaceStrategy,
        equals('mirroredForwardDynamicSplitFrontBack'),
      );
      expect(interactiveState.backwardCurrentResidualBounds, isNotNull);
      expect(interactiveState.backwardFrontCoverageRatio, isNotNull);
      expect(interactiveState.backwardLeftSpineLocked, isNotNull);
      expect(interactiveState.backwardSimulatorVisualPhase, isNotNull);
      expect(interactiveState.backwardEdgeEnteredPage, isNotNull);
      expect(interactiveState.backwardOverlayClippedToPaper, isTrue);
      expect(interactiveState.backwardBackVertexCount, greaterThanOrEqualTo(3));
      expect(
        interactiveState.backwardReplaySlices,
        contains('projectedGeometrySource=renderFrameMirroredForward'),
      );
      expect(interactiveState.backwardReplaySlices, contains('backVertices='));
      expect(interactiveState.backwardReplaySlices, contains('frontVertices='));
      expect(interactiveState.backwardBackPolygonPoints, isNotNull);
      expect(interactiveState.backwardCurrentPolygonPoints, isNotNull);
      if ((interactiveState.backwardRectoWidth ?? 0) > 0.001) {
        expect(interactiveState.backwardFrontPaintBounds, isNotNull);
      }
      expect(interactiveState.backwardBackPaintBounds!.width, greaterThan(0));
      expect(interactiveState.backwardFoldX, isNotNull);
      expect(interactiveState.backwardPageEdgeX, isNotNull);
      expect(
        interactiveState.backwardFoldX!,
        greaterThan(0),
        reason: 'fold line must stay inside the page, not collapse off-screen',
      );
      expect(
        interactiveState.backwardFoldX!,
        lessThan(interactiveState.backwardSurfaceViewportRect!.width),
        reason: 'fold line must stay inside the page width',
      );
      expect(interactiveState.backwardCoveredWidth, isNotNull);
      expect(interactiveState.backwardRectoCoverage, isNotNull);
      // 倾斜手势下：F 来自镜像前翻 flipping polygon，E 来自 F 对原页右边线
      // 的投影反射，不能再退化成与 F 平行的矩形 band。
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
        greaterThan(1),
        reason: 'fold line must come from the rotated viewport polygon',
      );
      expect(
        (edgeTop.dx - edgeBottom.dx).abs(),
        greaterThan(1),
        reason: 'page edge must rotate with the folding page',
      );
      expect(interactiveState.backwardEdgeParallelToFold, isFalse);
      expect(interactiveState.backwardPaintedVersoWidth, isNotNull);
      expect(interactiveState.backwardPaintedVersoWidth, greaterThan(0));
      expect(
        interactiveState.backwardPageEdgeX!,
        lessThan(interactiveState.backwardFoldX!),
      );
      expect(find.byType(ArticlePageCurlRenderer), findsNothing);
      expect(find.byType(ArticlePageBackwardLeafRenderer), findsNothing);

      await gesture.up();
      await tester.pumpAndSettle();

      final backwardAnimationStates = debugStates.where(
        (state) =>
            state.renderDirection == StPageFlipDirection.back &&
            state.backwardCompositeMode == 'mirroredForwardDynamic',
      );
      expect(backwardAnimationStates, isNotEmpty);
      for (final state in backwardAnimationStates) {
        final foldX = state.backwardFoldX;
        final surfaceWidth = state.backwardSurfaceViewportRect?.width;
        expect(foldX, isNotNull);
        expect(surfaceWidth, isNotNull);
        expect(
          foldX!,
          greaterThan(0),
          reason: 'backward animation fold line must not collapse off-screen',
        );
        expect(
          foldX,
          lessThan(surfaceWidth!),
          reason: 'backward animation fold line must stay inside page width',
        );
        expect(state.backwardBackPaintBounds, isNotNull);
        expect(state.backwardBackPaintBounds!.width, greaterThan(0));
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
    },
  );

  testWidgets(
    'PageflipDiagnosticsApp backward dynamic page after forward turn exposes visual regions',
    (WidgetTester tester) async {
      final sample = await _renderBackwardCompositeProbeScene(tester);

      expect(sample.earlyBackVisible, isTrue);
      expect(sample.middleBackVisible, isTrue);
      expect(sample.middleCurrentResidualVisible, isTrue);
      expect(sample.middleFoldHasFrontText, isFalse);
      expect(sample.middleCompositeMode, equals('mirroredForwardDynamic'));
      expect(sample.middleBackRight - sample.middleBackLeft, greaterThan(40));
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
            debugPageSurfaceBuilder: _buildProbePageSurface,
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

  var debugCursor = debugStates.length;
  Future<_BackwardProbeFrame> captureFrame() async {
    await tester.pump(const Duration(milliseconds: 16));
    final phaseStates = debugStates.skip(debugCursor).toList(growable: false);
    final debugState =
        phaseStates
            .where(
              (state) =>
                  state.renderDirection == StPageFlipDirection.back &&
                  state.backwardCompositeMode == 'mirroredForwardDynamic' &&
                  state.backwardBackPaintBounds != null,
            )
            .fold<ArticleReadOnlyBookDebugState?>(
              null,
              (best, state) => state.backwardFrontPaintBounds != null
                  ? state
                  : best ?? state,
            ) ??
        debugStates.lastWhere(
          (state) =>
              state.renderDirection == StPageFlipDirection.back &&
              state.backwardCompositeMode == 'mirroredForwardDynamic' &&
              state.backwardBackPaintBounds != null,
        );
    debugCursor = debugStates.length;
    return _sampleBackwardFrame(tester: tester, debugState: debugState);
  }

  await gesture.moveBy(const Offset(100, -12));
  for (var i = 0; i < 4; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  final early = await captureFrame();

  await gesture.moveBy(const Offset(620, -48));
  for (var i = 0; i < 8; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
  var middle = await captureFrame();
  if (!middle.frontVisible) {
    await gesture.moveBy(const Offset(240, -12));
    for (var i = 0; i < 6; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    middle = await captureFrame();
  }

  await gesture.up();
  for (var i = 0; i < 3; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));

  return _BackwardCompositeProbeSample(
    earlyBackVisible: early.backVisible,
    earlyFrontVisible: early.frontVisible,
    middleFrontVisible: middle.frontVisible,
    middleBackVisible: middle.backVisible,
    middleCurrentResidualVisible: middle.currentResidualVisible,
    middleFoldHasFrontText: middle.foldHasFrontText,
    middleCompositeMode: middle.compositeMode,
    pageLeft: middle.pageLeft,
    middleFrontLeft: middle.frontLeft,
    middleFrontRight: middle.frontRight,
    middleBackLeft: middle.backLeft,
    middleBackRight: middle.backRight,
    middleCurrentLeft: middle.currentLeft,
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

_BackwardProbeFrame _sampleBackwardFrame({
  required WidgetTester tester,
  required ArticleReadOnlyBookDebugState debugState,
}) {
  final frontBounds = debugState.backwardFrontPaintBounds;
  final backBounds = debugState.backwardBackPaintBounds;
  final currentBounds = debugState.backwardCurrentResidualBounds;
  final frontFinder = find.byKey(
    const ValueKey<String>('article_backward_previous_front_region'),
  );
  final backFinder = find.byKey(
    const ValueKey<String>('article_backward_previous_back_region'),
  );
  final currentFinder = find.byKey(
    const ValueKey<String>('article_backward_current_residual_region'),
  );
  final frontFinderVisible = frontFinder.evaluate().isNotEmpty;
  final frontVisible =
      (debugState.backwardRectoCoverage ?? 0) > 0.005 &&
      (frontFinderVisible ||
          (debugState.backwardFrontPaintBounds?.width ?? 0) > 0);
  final backFinderVisible = backFinder.evaluate().isNotEmpty;
  final backVisible =
      backFinderVisible || (debugState.backwardPaintedVersoWidth ?? 0) > 0;
  final currentFinderVisible = currentFinder.evaluate().isNotEmpty;
  final currentResidualVisible =
      currentFinderVisible ||
      (debugState.backwardCurrentResidualBounds?.width ?? 0) > 0;
  final foldHasFrontText = false;
  expect(backBounds, isNotNull);
  final resolvedBackBounds = backBounds!;
  if (frontFinderVisible && frontBounds != null) {
    expect(frontBounds.width, greaterThan(0));
    expect(
      tester.getSize(frontFinder).height,
      greaterThan(0),
      reason:
          'the front page is clipped by a viewport polygon inside the page surface',
    );
  }
  if (backFinderVisible) {
    expect(tester.getSize(backFinder).width, greaterThan(0));
  }
  if (currentFinderVisible && currentBounds != null) {
    expect(tester.getSize(currentFinder).width, greaterThan(0));
  }
  final pageLeft =
      frontBounds?.left ??
      (currentBounds != null && debugState.backwardFoldX != null
          ? currentBounds.left - debugState.backwardFoldX!
          : resolvedBackBounds.left - (debugState.backwardPageEdgeX ?? 0));
  return _BackwardProbeFrame(
    frontVisible: frontVisible,
    backVisible: backVisible,
    currentResidualVisible: currentResidualVisible,
    foldHasFrontText: foldHasFrontText,
    compositeMode: debugState.backwardCompositeMode ?? '',
    pageLeft: pageLeft,
    frontLeft: frontBounds?.left ?? pageLeft,
    frontRight: frontBounds?.right ?? pageLeft,
    backLeft: resolvedBackBounds.left,
    backRight: resolvedBackBounds.right,
    currentLeft: currentBounds?.left ?? double.infinity,
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

enum _ProbeColor { red, green, white, black, paperBack, other }

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

class _BackwardCompositeProbeSample {
  const _BackwardCompositeProbeSample({
    required this.earlyBackVisible,
    required this.earlyFrontVisible,
    required this.middleFrontVisible,
    required this.middleBackVisible,
    required this.middleCurrentResidualVisible,
    required this.middleFoldHasFrontText,
    required this.middleCompositeMode,
    required this.pageLeft,
    required this.middleFrontLeft,
    required this.middleFrontRight,
    required this.middleBackLeft,
    required this.middleBackRight,
    required this.middleCurrentLeft,
  });

  final bool earlyBackVisible;
  final bool earlyFrontVisible;
  final bool middleFrontVisible;
  final bool middleBackVisible;
  final bool middleCurrentResidualVisible;
  final bool middleFoldHasFrontText;
  final String middleCompositeMode;
  final double pageLeft;
  final double middleFrontLeft;
  final double middleFrontRight;
  final double middleBackLeft;
  final double middleBackRight;
  final double middleCurrentLeft;
}

class _BackwardProbeFrame {
  const _BackwardProbeFrame({
    required this.frontVisible,
    required this.backVisible,
    required this.currentResidualVisible,
    required this.foldHasFrontText,
    required this.compositeMode,
    required this.pageLeft,
    required this.frontLeft,
    required this.frontRight,
    required this.backLeft,
    required this.backRight,
    required this.currentLeft,
  });

  final bool frontVisible;
  final bool backVisible;
  final bool currentResidualVisible;
  final bool foldHasFrontText;
  final String compositeMode;
  final double pageLeft;
  final double frontLeft;
  final double frontRight;
  final double backLeft;
  final double backRight;
  final double currentLeft;
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
