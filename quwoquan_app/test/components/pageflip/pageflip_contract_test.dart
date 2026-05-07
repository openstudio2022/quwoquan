import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/article_reader_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/single_page_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/backward_render_frame_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/curl_mesh_builder.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

void main() {
  group('Pageflip', () {
    test('article reader product host keeps single-page pipeline contracts', () {
      final hostSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
      );
      final forwardPipelineSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart',
      );
      final backwardPipelineSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart',
      );
      final controllerSource = _readAppSource(
        'lib/ui/content/pageflip/controller.dart',
      );
      final backwardBuilderSource = _readAppSource(
        'lib/ui/content/pageflip/backward_render_frame_builder.dart',
      );
      final diagnosticSignaturesSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart',
      );
      final debugMapperSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_mapper.dart',
      );
      final currentBarrelSource = _readAppSource(
        'lib/ui/content/widgets/article_paged_canvas.dart',
      );

      expect(hostSource, contains('final SinglePageModeStrategy'));
      expect(hostSource, contains('const SinglePageModeStrategy()'));
      expect(hostSource, isNot(contains('SpreadDoublePageModeStrategy(')));
      expect(hostSource, isNot(contains('spreadDoublePage')));
      expect(hostSource, contains('paperFoldDynamic'));
      expect(hostSource, isNot(contains('highFidelity')));
      expect(hostSource, isNot(contains('HighFidelity')));
      expect(hostSource, isNot(contains('_tryBuildHighFidelityRenderScene')));
      expect(hostSource, isNot(contains('ArticlePageCurlRenderer')));
      expect(hostSource, isNot(contains('genericDynamic')));
      expect(hostSource, isNot(contains('mirroredForwardDynamic')));

      final forwardImports = _sourceImportLines(forwardPipelineSource);
      expect(forwardImports, isNot(contains(contains('backward'))));
      expect(forwardImports, isNot(contains(contains('diagnostics'))));
      expect(forwardImports, isNot(contains(contains('projection'))));
      expect(
        forwardPipelineSource,
        isNot(contains('BackwardArticleFlipPipeline')),
      );
      expect(forwardPipelineSource, isNot(contains('backwardProjectedFrame')));
      expect(
        forwardPipelineSource,
        isNot(contains('ArticlePageBackwardProjectedFrame')),
      );
      expect(
        '$forwardPipelineSource\n$backwardPipelineSource',
        isNot(contains('SpreadDoublePageModeStrategy')),
      );
      expect(
        '$forwardPipelineSource\n$backwardPipelineSource',
        isNot(contains('spreadDoublePage')),
      );
      expect(
        hostSource,
        isNot(contains('class BackwardGenericDynamicFoldProjection')),
      );
      expect(hostSource, isNot(contains('class PaperFoldSurfaceSlices')));
      expect(
        hostSource,
        isNot(contains('resolveBackwardGenericDynamicFoldProjection({')),
      );
      expect(
        hostSource,
        isNot(contains('resolveBackwardPaperFoldSurfaceSlices({')),
      );
      expect(
        hostSource,
        isNot(contains('resolveBackwardPaperFoldProjection(')),
      );
      expect(
        hostSource,
        isNot(contains('resolveBackwardPaperFoldSurfaceSlices(')),
      );
      expect(
        hostSource,
        isNot(contains('String articleDiagnosticOffsetSignature(')),
      );
      expect(
        hostSource,
        isNot(contains('String articleDiagnosticRectSignature(')),
      );
      expect(
        hostSource,
        isNot(contains('String articleDiagnosticPolygonSignature(')),
      );
      expect(
        hostSource,
        isNot(contains('double articleDiagnosticPolygonArea(')),
      );
      expect(
        diagnosticSignaturesSource,
        contains('String articleDiagnosticOffsetSignature('),
      );
      expect(
        controllerSource,
        contains('movingEdgeLine: calculation.getBackwardMovingEdgeLine()'),
      );
      expect(
        debugMapperSource,
        contains('resolveBackwardFoldFrameGeometry('),
        reason:
            'diagnostics must consume the same M1 BackwardFoldFrame resolver as paint',
      );
      expect(
        debugMapperSource,
        isNot(contains('backwardProjectedFrame')),
        reason:
            'backwardProjectedFrame is retired diagnostics-only data and must not drive M1/M2 diagnostics',
      );
      expect(backwardBuilderSource, isNot(contains('_resolveMovingEdgeLine(')));
      expect(
        backwardBuilderSource,
        contains('edgeLineSource: canonicalMovingEdgeLine == null'),
      );

      expect(
        currentBarrelSource,
        isNot(contains('class ArticleReadOnlyBookDeck')),
      );
      expect(
        currentBarrelSource,
        contains(
          "export 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart'",
        ),
      );
    });

    test(
      'article reader forward soft paint stays isolated from BACK resolver',
      () {
        final hostSource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
        );
        final softLayerStart = hostSource.indexOf('Widget _buildSoftPageLayer');
        final hardLayerStart = hostSource.indexOf(
          'Widget _buildHardFlippingPageLayer',
        );
        expect(softLayerStart, isNonNegative);
        expect(hardLayerStart, greaterThan(softLayerStart));
        final softLayerSource = hostSource.substring(
          softLayerStart,
          hardLayerStart,
        );
        final forwardFallbackStart = softLayerSource.indexOf(
          'final layerOrigin = softLayerOrigin',
        );
        expect(forwardFallbackStart, isNonNegative);
        final forwardFallbackSource = softLayerSource.substring(
          forwardFallbackStart,
        );

        expect(
          softLayerSource,
          contains('direction == StPageFlipDirection.back && isFlippingPage'),
        );
        expect(forwardFallbackSource, contains('Transform.rotate('));
        expect(
          forwardFallbackSource,
          isNot(contains('resolveBackwardSoftPageGeometry(')),
        );
      },
    );

    test('article reader BACK paint consumes only render-frame soft inputs', () {
      final hostSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
      );
      final backwardStart = hostSource.indexOf(
        'ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers',
      );
      final commitStart = hostSource.indexOf('bool _shouldCommitPageFlip');
      expect(backwardStart, isNonNegative);
      expect(commitStart, greaterThan(backwardStart));
      final backwardLayerSource = hostSource.substring(
        backwardStart,
        commitStart,
      );

      expect(
        backwardLayerSource,
        contains('final flippingArea = frame.flippingClipArea;'),
      );
      expect(
        backwardLayerSource,
        contains('_buildBackwardCurrentResidualLayer('),
      );
      expect(
        backwardLayerSource,
        contains('_buildBackwardPreviousFrontPlaneLayer('),
      );
      expect(
        backwardLayerSource,
        contains('_buildBackwardPreviousBackSoftLayer('),
      );
      expect(
        backwardLayerSource,
        contains('_buildBackwardGeometryGuideLayer('),
      );
      expect(hostSource, contains('debugPureBackwardGeometry'));
      expect(hostSource, contains('if (!widget.debugPureBackwardGeometry)'));
      expect(
        backwardLayerSource,
        isNot(contains('resolveBackwardSoftPageGeometry(')),
      );
      expect(hostSource, contains('resolveBackwardFoldFrameGeometry('));
      expect(hostSource, isNot(contains('frame.backwardProjectedFrame')));
      expect(
        backwardLayerSource,
        isNot(contains('previousFoldSurfacePolygon')),
      );
      expect(backwardLayerSource, isNot(contains('previousBackFoldPolygon')));
      expect(backwardLayerSource, isNot(contains('previousFrontFoldPolygon')));
      expect(hostSource, isNot(contains('_buildBackwardSpineFoldLayer(')));
      expect(hostSource, isNot(contains('resolveBackwardSpineFoldGeometry(')));
      final softGeometrySource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
      );
      expect(
        softGeometrySource,
        isNot(contains('resolveBackwardFoldSurfaceGeometry({')),
        reason: 'M1 keeps one public BACK three-face resolver',
      );
      expect(softGeometrySource, isNot(contains('const tilt = 0.0')));
      expect(softGeometrySource, isNot(contains('final _ = localPagePoint')));
    });

    test(
      'single-page mode layout records role window and suppression policy',
      () {
        final scene = _buildInteractiveForwardStScene();
        final modeLayout = const SinglePageModeStrategy().resolveLayout(
          scene: scene,
          dynamicallyRenderedPages: const <int>{2, 3},
        );

        expect(modeLayout.mode, ArticleReaderFlipMode.singlePage);
        expect(
          modeLayout.rolePolicy,
          ArticleReaderPageRolePolicy.singleVisiblePage,
        );
        expect(
          modeLayout.windowPolicy,
          ArticleReaderPageWindowPolicy.currentWithAdjacentPages,
        );
        expect(
          modeLayout.staticSuppressionPolicy,
          ArticleReaderStaticSuppressionPolicy.dynamicallyRenderedPages,
        );
        expect(modeLayout.staticSuppressionPages, unorderedEquals(<int>{2, 3}));
        expect(modeLayout.windowPageIndices, unorderedEquals(<int>{1, 2, 3}));
      },
    );

    test(
      'forward pipeline promotes required textures to static suppression',
      () {
        final scene = _buildInteractiveForwardStScene();
        expect(scene.renderFrame, isNotNull);
        final modeLayout = const SinglePageModeStrategy().resolveLayout(
          scene: scene,
          dynamicallyRenderedPages: const <int>{},
        );
        const textureBinding = ArticlePageTextureBinding(
          direction: StPageFlipDirection.forward,
          rectoPageIndex: 2,
          versoPageIndex: 2,
          bottomPageIndex: 3,
        );

        final output = const ForwardArticleFlipPipeline().resolve(
          ArticleFlipPipelineInput(
            scene: scene,
            renderFrame: scene.renderFrame!,
            pageSize: const Size(420, 584),
            modeLayout: modeLayout,
            textureBinding: textureBinding,
            textureBundle: null,
          ),
        );

        expect(output.direction, StPageFlipDirection.forward);
        expect(output.staticSuppressionPages, unorderedEquals(<int>{2, 3}));
        expect(output.renderBranchName, 'forwardSharedPipeline');
        expect(output.debugLabel, 'forward/shared');
      },
    );

    test(
      'backward pipeline suppresses covered current and owns residual paint',
      () {
        final scene = _buildInteractiveBackwardStScene();
        expect(scene.renderFrame, isNotNull);
        final modeLayout = const SinglePageModeStrategy().resolveLayout(
          scene: scene,
          dynamicallyRenderedPages: const <int>{},
        );
        const textureBinding = ArticlePageTextureBinding(
          direction: StPageFlipDirection.back,
          rectoPageIndex: 2,
          versoPageIndex: 2,
          bottomPageIndex: 3,
        );

        final output = const BackwardArticleFlipPipeline().resolve(
          ArticleFlipPipelineInput(
            scene: scene,
            renderFrame: scene.renderFrame!,
            pageSize: const Size(420, 584),
            modeLayout: modeLayout,
            textureBinding: textureBinding,
            textureBundle: null,
          ),
        );

        expect(output.direction, StPageFlipDirection.back);
        expect(
          output.staticSuppressionPages,
          contains(scene.flippingPageIndex),
        );
        expect(
          output.staticSuppressionPages,
          contains(textureBinding.bottomPageIndex),
          reason:
              'BACK dynamic paint must suppress the complete current page and redraw only currentResidualPolygon',
        );
        expect(output.renderBranchName, 'backwardThreeFacePaperFoldPipeline');
        expect(output.debugLabel, 'backward/three-face-paper-fold');

        final hostSource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
        );
        expect(hostSource, contains('_buildBackwardCurrentResidualLayer('));
        final backwardStart = hostSource.indexOf(
          'ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers',
        );
        final commitStart = hostSource.indexOf('bool _shouldCommitPageFlip');
        final backwardLayerSource = hostSource.substring(
          backwardStart,
          commitStart,
        );
        expect(
          backwardLayerSource,
          contains('_buildBackwardCurrentResidualLayer('),
        );
        expect(
          backwardLayerSource,
          contains('_buildBackwardPreviousFrontPlaneLayer('),
        );
        expect(
          backwardLayerSource,
          contains('_buildBackwardPreviousBackSoftLayer('),
        );
      },
    );

    test(
      'single-page role resolver maps turning and covered pages by direction',
      () {
        const resolver = PageflipSinglePageRoleResolver();

        final forward = resolver.resolve(
          mode: PageflipMode.single,
          direction: PageflipDirection.forward,
          currentPageIndex: 2,
          pageCount: 5,
        );
        final backward = resolver.resolve(
          mode: PageflipMode.single,
          direction: PageflipDirection.back,
          currentPageIndex: 2,
          pageCount: 5,
        );

        expect(forward.underlayPageIndex, 3);
        expect(backward.underlayPageIndex, 2);
        expect(forward.turningPageIndex, 2);
        expect(backward.turningPageIndex, 1);
        expect(forward.coveredPageIndex, 2);
        expect(backward.coveredPageIndex, 2);
      },
    );

    test('forward render frame matches long-form canonical angle', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      expect(
        engine.start(Offset(pageRect.right - 18, pageRect.bottom - 18)),
        isTrue,
      );
      engine.fold(Offset(pageRect.center.dx + 48, pageRect.center.dy));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      final renderFrame = scene!.renderFrame;
      expect(renderFrame, isNotNull);
      expect(renderFrame!.direction, PageflipDirection.forward);

      final canonical = StPageFlipCalculation(
        direction: StPageFlipDirection.forward,
        corner: renderFrame.canonicalFrame.corner,
        pageWidth: 420,
        pageHeight: 584,
      );
      expect(canonical.calc(renderFrame.canonicalFrame.localPagePoint), isTrue);
      expect(renderFrame.angle, closeTo(canonical.getAngle(), 1e-9));
      expect(
        renderFrame.canonicalFrame.timeline.diagonalExtent,
        lessThanOrEqualTo(420 * 0.078),
      );
      expect(
        renderFrame.canonicalFrame.timeline.sheetShift.abs(),
        lessThanOrEqualTo(420 * 0.02),
      );
      expect(
        renderFrame.canonicalFrame.timeline.leadingRadius,
        greaterThan(renderFrame.canonicalFrame.timeline.trailingRadius),
      );
      expect(
        renderFrame.canonicalFrame.timeline.heightLiftBias,
        lessThan(0.08),
      );
      expect(renderFrame.canonicalFrame.flippingClipArea, isNotEmpty);
      expect(renderFrame.canonicalFrame.bottomClipArea, isNotEmpty);
      expect(
        renderFrame.canonicalFrame.bottomClipArea.any(
          (point) => point.dx >= 420 - 0.001,
        ),
        isTrue,
      );
    });

    test('reverse render frame uses shared backward replay contract', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final y = layout.bounds.top + (layout.bounds.height / 2);
      expect(engine.start(Offset(layout.bounds.left + 12, y)), isTrue);
      engine.fold(Offset(layout.bounds.left + 42, y));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      final renderFrame = scene!.renderFrame;
      expect(renderFrame, isNotNull);
      expect(renderFrame!.direction, PageflipDirection.back);
      expect(renderFrame.canonicalFrame.reversePose, isNull);
      // backwardLeafFrame is retained for diagnostics/timeline use only and is
      // no longer the source of geometry. Keep the existence check so we know
      // the timeline pipeline still runs.
      expect(renderFrame.canonicalFrame.backwardLeafFrame, isNotNull);
      expect(scene.turningPageIndex, 1);
      expect(scene.underlayPageIndex, 2);
      expect(scene.coveredPageIndex, 2);
      expect(scene.turningPageIndex, isNot(scene.underlayPageIndex));
      // Backward 主线统一：polygon 直接来自 BACK StPageFlipCalculation，
      // 不再通过 forward calculation 镜像，也不再走 seam 矩形伪几何。
      expect(
        renderFrame.canonicalFrame.flippingClipArea.length,
        greaterThanOrEqualTo(3),
      );
      expect(
        renderFrame.canonicalFrame.bottomClipArea.length,
        greaterThanOrEqualTo(3),
      );
      expect(renderFrame.canonicalFrame.bottomAnchor.dx.isFinite, isTrue);
      expect(renderFrame.canonicalFrame.angle.isFinite, isTrue);
      final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
        localPagePoint: renderFrame.canonicalFrame.localPagePoint,
        pageSize: const Size(420, 584),
      );
      expect(
        renderFrame.canonicalFrame.timeline.curlAngleBand,
        resolveForwardCurlAngleBand(
          localPagePoint: replayLocalPoint,
          pageSize: const Size(420, 584),
          corner: renderFrame.canonicalFrame.corner,
        ),
      );
    });

    test('backward dynamic render frame consumes native BACK calculation', () {
      const pageSize = Size(420, 584);
      const localPagePoint = Offset(-96, 496);
      final backCalculation = StPageFlipCalculation(
        direction: StPageFlipDirection.back,
        corner: StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      expect(backCalculation.calc(localPagePoint), isTrue);

      final frame = buildBackwardDynamicRenderFrame(
        BackwardRenderFrameData(
          localPagePoint: localPagePoint,
          progress: 0.42,
          orientation: StPageFlipOrientation.portrait,
          corner: StPageFlipCorner.bottom,
          pageSize: pageSize,
          flippingClipArea: backCalculation.getFlippingClipArea(),
          bottomClipArea: backCalculation.getBottomClipArea(),
          flippingAnchor: backCalculation.getActiveCorner(),
          bottomAnchor: backCalculation.getBottomPagePosition(),
          angle: backCalculation.getAngle(),
          movingEdgeLine: backCalculation.getBackwardMovingEdgeLine(),
          maxShadowOpacity: 0.2,
        ),
      );

      expect(frame.direction, StPageFlipDirection.back);
      expect(frame.renderDirection, StPageFlipDirection.back);
      expect(frame.flippingClipArea, backCalculation.getFlippingClipArea());
      expect(frame.bottomClipArea, backCalculation.getBottomClipArea());
      expect(frame.flippingAnchor, backCalculation.getActiveCorner());
      expect(frame.bottomAnchor, backCalculation.getBottomPagePosition());
      expect(frame.angle, closeTo(backCalculation.getAngle(), 1e-9));
      final projectedFrame = frame.backwardProjectedFrame;
      expect(projectedFrame, isNotNull);
      expect(
        projectedFrame!.previousFrontPolygon.length,
        anyOf(0, greaterThanOrEqualTo(3)),
      );
      expect(projectedFrame.previousLaidFrontPolygon, isEmpty);
      expect(projectedFrame.previousBackPagePolygon, isEmpty);
      expect(
        projectedFrame.previousFoldSurfacePolygon.length,
        greaterThanOrEqualTo(3),
      );
      expect(
        projectedFrame.previousBackFoldPolygon.length,
        anyOf(0, greaterThanOrEqualTo(3)),
      );
      expect(
        projectedFrame.previousFrontFoldPolygon.length,
        anyOf(0, greaterThanOrEqualTo(3)),
      );
      expect(
        projectedFrame.previousBackPolygon.length,
        anyOf(0, greaterThanOrEqualTo(3)),
      );
      expect(
        projectedFrame.currentResidualPolygon.length,
        greaterThanOrEqualTo(3),
      );
      expect(_allXWithinPage(projectedFrame.foldLine, pageSize.width), isTrue);
      expect(projectedFrame.edgeLineSource, 'backCalculationRectRightEdge');
      expect(
        _allPolygonXWithinPage(
          projectedFrame.previousLaidFrontPolygon,
          pageSize.width,
        ),
        isTrue,
      );
      expect(
        _allPolygonXWithinPage(
          projectedFrame.previousBackPagePolygon,
          pageSize.width,
        ),
        isTrue,
      );
      expect(
        _allPolygonXWithinPage(
          projectedFrame.previousFoldSurfacePolygon,
          pageSize.width,
        ),
        isTrue,
      );
      expect(
        _allPolygonXWithinPage(
          projectedFrame.previousFrontPolygon,
          pageSize.width,
        ),
        isTrue,
      );
      expect(
        _allPolygonXWithinPage(
          projectedFrame.previousBackPolygon,
          pageSize.width,
        ),
        isTrue,
      );
      expect(
        _allPolygonXWithinPage(
          projectedFrame.currentResidualPolygon,
          pageSize.width,
        ),
        isTrue,
      );
      expect(
        _polygonArea(projectedFrame.currentResidualPolygon),
        greaterThan(1),
      );
      expect(
        _polygonArea(projectedFrame.previousFoldSurfacePolygon),
        greaterThan(1),
      );
      expect(
        _polygonArea(projectedFrame.previousFoldSurfacePolygon),
        greaterThan(1),
      );
      expect(
        _polygonArea(projectedFrame.previousFoldSurfacePolygon),
        greaterThanOrEqualTo(
          _polygonArea(projectedFrame.previousBackFoldPolygon),
        ),
      );
      expect(projectedFrame.foldLineSource, 'backCalculationParallelBoundary');
      expect(projectedFrame.edgeLineSource, 'backCalculationRectRightEdge');
    });

    test('backward soft page geometry matches StPageFlip BACK drawSoft', () {
      const pageSize = Size(420, 584);
      const bounds = StPageFlipBoundsRect(
        left: -210,
        top: 12,
        width: 840,
        height: 584,
        pageWidth: 420,
      );
      final calculation = StPageFlipCalculation(
        direction: StPageFlipDirection.back,
        corner: StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      expect(calculation.calc(const Offset(-120, 510)), isTrue);
      final anchor = calculation.getActiveCorner();
      final angle = calculation.getAngle();
      final area = calculation.getFlippingClipArea();

      final geometry = resolveBackwardSoftPageGeometry(
        area: area,
        anchor: anchor,
        angle: angle,
        bounds: bounds,
        pageSize: pageSize,
      );
      final expectedPosition = convertBookPointToViewport(
        anchor,
        bounds,
        direction: StPageFlipDirection.back,
      );
      final expectedLocalClipPolygon = area
          .map((point) => Offset(anchor.dx - point.dx, point.dy - anchor.dy))
          .toList(growable: false);
      expect(geometry.surfaceOrigin, anchor);
      expect(geometry.pivotLocal, Offset.zero);
      expect(geometry.positionViewport.dx, closeTo(expectedPosition.dx, 0.001));
      expect(geometry.positionViewport.dy, closeTo(expectedPosition.dy, 0.001));
      expect(geometry.clipLocalBounds, isNotNull);
      expect(rotationZFromMatrix(geometry.transform), closeTo(angle, 0.001));
      expect(geometry.localClipPolygon.length, expectedLocalClipPolygon.length);
      for (var index = 0; index < expectedLocalClipPolygon.length; index += 1) {
        expect(
          geometry.localClipPolygon[index].dx,
          closeTo(expectedLocalClipPolygon[index].dx, 0.001),
        );
        expect(
          geometry.localClipPolygon[index].dy,
          closeTo(expectedLocalClipPolygon[index].dy, 0.001),
        );
      }
      expect(
        geometry.clipViewportBounds,
        polygonBounds(
          transformSoftLayerLocalPolygon(
            polygon: geometry.localClipPolygon,
            geometry: geometry,
          ),
        ),
      );
    });

    test('backward fold frame derives ordered three-face geometry', () {
      const pageSize = Size(420, 584);
      const bounds = StPageFlipBoundsRect(
        left: -210,
        top: 12,
        width: 840,
        height: 584,
        pageWidth: 420,
      );
      final calculation = StPageFlipCalculation(
        direction: StPageFlipDirection.back,
        corner: StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      expect(calculation.calc(const Offset(-180, 502)), isTrue);
      final pageViewportRect = Rect.fromLTWH(
        bounds.left + bounds.pageWidth,
        bounds.top,
        bounds.pageWidth,
        bounds.height,
      );

      final geometry = resolveBackwardFoldFrameGeometry(
        flippingArea: calculation.getFlippingClipArea(),
        bottomArea: calculation.getBottomClipArea(),
        anchor: calculation.getActiveCorner(),
        angle: calculation.getAngle(),
        bounds: bounds,
        pageSize: pageSize,
        pageViewportRect: pageViewportRect,
      );

      expect(geometry, isNotNull);
      final resolved = geometry!;
      expect(
        resolved.previousFrontViewportPolygon.length,
        greaterThanOrEqualTo(3),
      );
      expect(
        resolved.previousBackViewportPolygon.length,
        greaterThanOrEqualTo(3),
      );
      expect(
        resolved.currentResidualViewportPolygon.length,
        greaterThanOrEqualTo(3),
      );

      final pageEdgeX = _lineAverageX(resolved.frontBackBoundaryViewport);
      final foldX = _lineAverageX(resolved.foldLineViewport);
      final pageEdgeRight = _lineMaxX(resolved.frontBackBoundaryViewport);
      final foldLeft = _lineMinX(resolved.foldLineViewport);
      final frontBounds = resolved.previousFrontViewportBounds!;
      final backBounds = resolved.previousBackViewportBounds!;
      final currentBounds = resolved.currentResidualViewportBounds!;
      expect(
        pageEdgeX,
        lessThan(foldX),
        reason:
            'previous front, previous back and current must stay ordered left-to-right',
      );
      expect(frontBounds.left, closeTo(pageViewportRect.left, 1));
      expect(frontBounds.right, closeTo(pageEdgeRight, 16));
      expect(backBounds.left, lessThanOrEqualTo(pageEdgeRight + 16));
      expect(backBounds.right, greaterThanOrEqualTo(foldLeft - 16));
      expect(currentBounds.left, closeTo(foldLeft, 16));
      expect(
        <double>[
          frontBounds.right,
          backBounds.right,
          currentBounds.right,
        ].reduce((a, b) => a > b ? a : b),
        greaterThan(pageViewportRect.left + pageViewportRect.width * 0.65),
        reason:
            'the three faces must not collapse into the left half of the page',
      );
    });

    test('backward fold frame keeps M1 geometry ordered across phases', () {
      const pageSize = Size(420, 584);
      const bounds = StPageFlipBoundsRect(
        left: -210,
        top: 12,
        width: 840,
        height: 584,
        pageWidth: 420,
      );
      final pageViewportRect = Rect.fromLTWH(
        bounds.left + bounds.pageWidth,
        bounds.top,
        bounds.pageWidth,
        bounds.height,
      );
      const samples = <Offset>[
        Offset(-48, 520),
        Offset(-180, 502),
        Offset(-284, 480),
      ];

      for (final sample in samples) {
        final calculation = StPageFlipCalculation(
          direction: StPageFlipDirection.back,
          corner: StPageFlipCorner.bottom,
          pageWidth: pageSize.width,
          pageHeight: pageSize.height,
        );
        expect(calculation.calc(sample), isTrue);
        final geometry = resolveBackwardFoldFrameGeometry(
          flippingArea: calculation.getFlippingClipArea(),
          bottomArea: calculation.getBottomClipArea(),
          anchor: calculation.getActiveCorner(),
          angle: calculation.getAngle(),
          bounds: bounds,
          pageSize: pageSize,
          pageViewportRect: pageViewportRect,
        );
        expect(geometry, isNotNull, reason: 'sample=$sample');
        _expectM1BackwardGeometryOrder(
          geometry!,
          pageViewportRect: pageViewportRect,
          reason: 'sample=$sample',
        );
      }
    });

    test('backward previous-page fold surface edge stays page-clipped', () {
      const pageSize = Size(420, 584);
      const localPoints = <Offset>[
        Offset(-48, 520),
        Offset(-124, 506),
        Offset(-220, 492),
      ];
      final edgeXs = <double>[];

      for (var index = 0; index < localPoints.length; index += 1) {
        final calculation = StPageFlipCalculation(
          direction: StPageFlipDirection.back,
          corner: StPageFlipCorner.bottom,
          pageWidth: pageSize.width,
          pageHeight: pageSize.height,
        );
        expect(calculation.calc(localPoints[index]), isTrue);
        final frame = buildBackwardDynamicRenderFrame(
          BackwardRenderFrameData(
            localPagePoint: localPoints[index],
            progress: 0.18 + index * 0.24,
            orientation: StPageFlipOrientation.portrait,
            corner: StPageFlipCorner.bottom,
            pageSize: pageSize,
            flippingClipArea: calculation.getFlippingClipArea(),
            bottomClipArea: calculation.getBottomClipArea(),
            flippingAnchor: calculation.getActiveCorner(),
            bottomAnchor: calculation.getBottomPagePosition(),
            angle: calculation.getAngle(),
            movingEdgeLine: calculation.getBackwardMovingEdgeLine(),
            maxShadowOpacity: 0.2,
          ),
        );
        final projectedFrame = frame.backwardProjectedFrame;
        expect(projectedFrame, isNotNull);
        edgeXs.add(_lineAverageX(projectedFrame!.foldSurfaceMovingEdgeLine));
        expect(projectedFrame.edgeLineSource, 'backCalculationRectRightEdge');
        final currentResidualBounds = _polygonBounds(
          projectedFrame.currentResidualPolygon,
        );
        if (currentResidualBounds != null) {
          expect(currentResidualBounds.width, greaterThan(1));
        }
      }

      expect(edgeXs, everyElement(greaterThanOrEqualTo(0)));
      expect(edgeXs, everyElement(lessThanOrEqualTo(pageSize.width)));
      expect(edgeXs.any((x) => x > 0), isTrue);
    });

    test('backward mesh keeps spine and seam vertically aligned', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      final startPoint = Offset(pageRect.left + pageRect.width * 0.18, 600);
      expect(engine.start(startPoint), isTrue);
      engine.fold(Offset(startPoint.dx + 120, startPoint.dy - 36));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      final renderFrame = scene!.renderFrame;
      expect(renderFrame, isNotNull);
      expect(renderFrame!.direction, PageflipDirection.back);

      const builder = ArticlePageCurlMeshBuilder();
      final meshFrame = builder.build(
        pageRect: scene.pageRect,
        pageSize: scene.pageSize,
        dragPoint: renderFrame.canonicalFrame.localPagePoint,
        progress: renderFrame.progress,
        direction: StPageFlipDirection.back,
        corner: renderFrame.canonicalFrame.corner,
        renderFrame: renderFrame.canonicalFrame,
        deriveBottomClipPathFromMesh: true,
      );

      expect(meshFrame.alignmentDiagnostics, isNotNull);
      expect(
        meshFrame.alignmentDiagnostics!.spineTopX,
        closeTo(scene.pageRect.left, 0.5),
      );
      expect(
        meshFrame.alignmentDiagnostics!.spineBottomX,
        closeTo(scene.pageRect.left, 0.5),
      );
      expect(
        meshFrame.alignmentDiagnostics!.spineDelta,
        lessThanOrEqualTo(0.01),
      );
      expect(
        meshFrame.alignmentDiagnostics!.seamDelta,
        lessThanOrEqualTo(0.01),
      );
      expect(meshFrame.frontDiagnostics, isNotNull);
      expect(meshFrame.backDiagnostics, isNotNull);
      expect(meshFrame.frontDiagnostics!.hasOverflow, isFalse);
      expect(meshFrame.backDiagnostics!.hasOverflow, isFalse);
    });

    test('backward seam moves monotonically from spine toward page edge', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      final startPoint = Offset(pageRect.left + pageRect.width * 0.18, 600);
      expect(engine.start(startPoint), isTrue);

      const sampleMoves = <Offset>[
        Offset(42, -12),
        Offset(140, -24),
        Offset(248, -36),
      ];
      final seamTopXs = <double>[];
      final seamBottomXs = <double>[];
      const builder = ArticlePageCurlMeshBuilder();

      for (final move in sampleMoves) {
        engine.fold(Offset(startPoint.dx + move.dx, startPoint.dy + move.dy));
        final scene = engine.buildScene(const Size(900, 1200));
        expect(scene, isNotNull);
        final renderFrame = scene!.renderFrame;
        expect(renderFrame, isNotNull);
        final meshFrame = builder.build(
          pageRect: scene.pageRect,
          pageSize: scene.pageSize,
          dragPoint: renderFrame!.canonicalFrame.localPagePoint,
          progress: renderFrame.progress,
          direction: StPageFlipDirection.back,
          corner: renderFrame.canonicalFrame.corner,
          renderFrame: renderFrame.canonicalFrame,
          deriveBottomClipPathFromMesh: true,
        );
        expect(meshFrame.alignmentDiagnostics, isNotNull);
        seamTopXs.add(meshFrame.alignmentDiagnostics!.seamTopX);
        seamBottomXs.add(meshFrame.alignmentDiagnostics!.seamBottomX);
      }

      expect(seamTopXs, orderedEquals([...seamTopXs]..sort()));
      expect(seamBottomXs, orderedEquals([...seamBottomXs]..sort()));
      expect(seamTopXs.first, greaterThanOrEqualTo(pageRect.left));
      expect(seamTopXs.last, lessThanOrEqualTo(pageRect.right + 0.5));
      expect(seamBottomXs.first, greaterThanOrEqualTo(pageRect.left));
      expect(seamBottomXs.last, lessThanOrEqualTo(pageRect.right + 0.5));
    });

    test('backward stopMove commits to previous page', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 2);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final y = layout.bounds.top + (layout.bounds.height / 2);
      expect(engine.start(Offset(layout.bounds.left + 12, y)), isTrue);
      engine.fold(Offset(layout.bounds.left + 8, y));

      final plan = engine.stopMove(
        Velocity(pixelsPerSecond: const Offset(-480, 0)),
      );

      expect(plan.commitsTurn, isTrue);
      expect(plan.direction, PageflipDirection.back);
      expect(engine.currentPageIndex, 1);
    });

    test('single-page backward can start from the visible page left half', () {
      final engine = PageflipEngine(pageCount: 5, initialPage: 3);
      engine.updateViewport(
        stageSize: const Size(900, 1200),
        pageSize: const Size(420, 584),
      );

      final layout = engine.buildScene(const Size(900, 1200))!.layout;
      final pageRect = layout.resolvePageRect(isRightPage: true);
      final startPoint = Offset(
        pageRect.left + pageRect.width * 0.18,
        pageRect.bottom - 24,
      );
      expect(engine.start(startPoint), isTrue);
      engine.fold(Offset(startPoint.dx + 120, startPoint.dy - 36));

      final scene = engine.buildScene(const Size(900, 1200));
      expect(scene, isNotNull);
      expect(scene!.direction, PageflipDirection.back);
      expect(scene.turningPageIndex, 2);
      expect(scene.underlayPageIndex, 3);
      expect(scene.coveredPageIndex, 3);

      final plan = engine.stopMove(
        const Velocity(pixelsPerSecond: Offset(420, 0)),
      );
      expect(plan.commitsTurn, isTrue);
      expect(plan.direction, PageflipDirection.back);
      expect(engine.currentPageIndex, 2);
    });

    test('scene buildBottomClipPath returns full page rect', () {
      const layoutResolver = PageflipLayoutResolver();
      final layout = layoutResolver.resolve(
        viewportSize: const Size(900, 1200),
        pageWidth: 420,
        pageHeight: 584,
        mode: PageflipMode.single,
      );
      const pageRect = Rect.fromLTWH(240, 308, 420, 584);
      final scene = PageflipScene(
        stageSize: const Size(900, 1200),
        pageRect: pageRect,
        pageSize: const Size(420, 584),
        layout: layout,
        state: const PageflipState(
          mode: PageflipMode.single,
          currentPageIndex: 2,
        ),
      );

      final clipPath = scene.buildBottomClipPath();
      expect(clipPath.getBounds().width, equals(pageRect.width));
      expect(clipPath.getBounds().height, equals(pageRect.height));
    });
  });
}

bool _allXWithinPage((Offset, Offset) line, double width) {
  return line.$1.dx >= -0.001 &&
      line.$1.dx <= width + 0.001 &&
      line.$2.dx >= -0.001 &&
      line.$2.dx <= width + 0.001;
}

bool _allPolygonXWithinPage(List<Offset> polygon, double width) {
  return polygon.every(
    (point) => point.dx >= -0.001 && point.dx <= width + 0.001,
  );
}

double _lineAverageX((Offset, Offset) line) {
  return (line.$1.dx + line.$2.dx) / 2;
}

double _lineMinX((Offset, Offset) line) {
  return line.$1.dx < line.$2.dx ? line.$1.dx : line.$2.dx;
}

double _lineMaxX((Offset, Offset) line) {
  return line.$1.dx > line.$2.dx ? line.$1.dx : line.$2.dx;
}

void _expectM1BackwardGeometryOrder(
  BackwardFoldSurfaceGeometry geometry, {
  required Rect pageViewportRect,
  required String reason,
}) {
  final pageEdgeX = _lineAverageX(geometry.frontBackBoundaryViewport);
  final foldX = _lineAverageX(geometry.foldLineViewport);
  final pageEdgeRight = _lineMaxX(geometry.frontBackBoundaryViewport);
  final foldLeft = _lineMinX(geometry.foldLineViewport);
  final frontBounds = geometry.previousFrontViewportBounds;
  final backBounds = geometry.previousBackViewportBounds;
  final currentBounds = geometry.currentResidualViewportBounds;
  expect(frontBounds, isNotNull, reason: reason);
  expect(backBounds, isNotNull, reason: reason);
  expect(currentBounds, isNotNull, reason: reason);
  expect(pageEdgeX, lessThan(foldX), reason: reason);
  expect(frontBounds!.left, closeTo(pageViewportRect.left, 1), reason: reason);
  expect(frontBounds.right, closeTo(pageEdgeRight, 18), reason: reason);
  expect(
    backBounds!.left,
    lessThanOrEqualTo(pageEdgeRight + 18),
    reason: reason,
  );
  expect(backBounds.right, greaterThanOrEqualTo(foldLeft - 18), reason: reason);
  expect(currentBounds!.left, closeTo(foldLeft, 18), reason: reason);
  expect(
    <double>[
      frontBounds.right,
      backBounds.right,
      currentBounds.right,
    ].reduce((a, b) => a > b ? a : b),
    greaterThan(pageViewportRect.left + pageViewportRect.width * 0.65),
    reason: reason,
  );
}

Rect? _polygonBounds(List<Offset> polygon) {
  if (polygon.isEmpty) {
    return null;
  }
  var left = polygon.first.dx;
  var right = polygon.first.dx;
  var top = polygon.first.dy;
  var bottom = polygon.first.dy;
  for (final point in polygon.skip(1)) {
    left = left < point.dx ? left : point.dx;
    right = right > point.dx ? right : point.dx;
    top = top < point.dy ? top : point.dy;
    bottom = bottom > point.dy ? bottom : point.dy;
  }
  return Rect.fromLTRB(left, top, right, bottom);
}

double _polygonArea(List<Offset> polygon) {
  if (polygon.length < 3) {
    return 0;
  }
  var sum = 0.0;
  for (var i = 0; i < polygon.length; i += 1) {
    final current = polygon[i];
    final next = polygon[(i + 1) % polygon.length];
    sum += current.dx * next.dy - next.dx * current.dy;
  }
  return sum.abs() / 2;
}

StPageFlipScene _buildInteractiveForwardStScene() {
  final layout = computeStPageFlipLayout(
    viewportSize: const Size(900, 1200),
    pageWidth: 420,
    pageHeight: 584,
  );
  final controller = StPageFlipController(
    spreadModel: StPageFlipSpreadModel(pageCount: 5),
    layout: layout,
    initialPage: 2,
  );
  final pageRect = resolveBookPageRect(layout, isRightPage: true);
  expect(
    controller.start(Offset(pageRect.right - 18, pageRect.bottom - 18)),
    isTrue,
  );
  controller.fold(Offset(pageRect.center.dx + 48, pageRect.center.dy));
  return controller.scene;
}

StPageFlipScene _buildInteractiveBackwardStScene() {
  final layout = computeStPageFlipLayout(
    viewportSize: const Size(900, 1200),
    pageWidth: 420,
    pageHeight: 584,
  );
  final controller = StPageFlipController(
    spreadModel: StPageFlipSpreadModel(pageCount: 5),
    layout: layout,
    initialPage: 3,
  );
  final pageRect = resolveBookPageRect(layout, isRightPage: false);
  expect(
    controller.start(Offset(pageRect.left + 18, pageRect.bottom - 18)),
    isTrue,
  );
  controller.fold(Offset(pageRect.center.dx + 120, pageRect.center.dy - 32));
  return controller.scene;
}

String _readAppSource(String relativePath) {
  return File(relativePath).readAsStringSync();
}

List<String> _sourceImportLines(String source) {
  return source
      .split('\n')
      .where((line) => line.trimLeft().startsWith('import '))
      .toList(growable: false);
}
