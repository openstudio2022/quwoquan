import 'dart:io';

import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip/pageflip.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart';
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

      expect(
        File(
          'lib/ui/content/pageflip/backward_leaf_renderer.dart',
        ).existsSync(),
        isFalse,
        reason:
            'retired BACK leaf renderer must stay deleted so it cannot re-enter '
            'as a competing geometry/texture path.',
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
        contains(
          'final canonicalFoldGeometry = calculation.getCanonicalFoldGeometry();',
        ),
      );
      expect(
        controllerSource,
        contains('foldLine: canonicalFoldGeometry?.foldLine'),
      );
      expect(
        controllerSource,
        contains('freeEdgeLine: canonicalFoldGeometry?.freeEdgeLine'),
      );
      expect(
        debugMapperSource,
        isNot(contains('resolveBackwardSoftPageGeometry(')),
        reason:
            'BACK 不再使用废止的独立 soft helper；mapper 必须跟 host 共享 '
            'StPageFlip native drawSoft 坐标链。',
      );
      expect(
        debugMapperSource,
        contains('convertBookPointToViewport('),
        reason: 'mapper 必须使用与 host 同源的 direction-aware 投影。',
      );
      expect(
        debugMapperSource,
        contains('StPageFlipDirection.back'),
        reason: 'mapper 必须对齐 StPageFlip BACK convertToGlobal，不能强制 forward 投影。',
      );
      expect(
        debugMapperSource,
        isNot(contains('resolveBackwardFoldFrameGeometry(')),
        reason:
            'BackwardFoldFrameGeometry has been retired; mapper must not '
            're-derive sheet/front/back/current polygons.',
      );
      expect(backwardBuilderSource, isNot(contains('_resolveMovingEdgeLine(')));
      expect(
        backwardBuilderSource,
        contains("foldLineSource: 'backwardForwardIsomorphicFoldLine'"),
      );
      expect(
        backwardBuilderSource,
        contains("edgeLineSource: 'backwardForwardIsomorphicFreeEdgeLine'"),
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
      'article reader soft paint uses visual geometry direction and sheet split',
      () {
        // portrait BACK 保留语义方向，但 soft-layer 几何按
        // `visualGeometryDirection` 消费同构 F/E/clip。
        final hostSource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
        );
        final debugMapperSource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_mapper.dart',
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

        expect(
          softLayerSource,
          isNot(contains('resolveBackwardSoftPageGeometry(')),
          reason: 'BACK 专属 soft helper 已废止，host `_buildSoftPageLayer` 不得再调用。',
        );
        expect(softLayerSource, contains('Transform.rotate('));
        expect(
          hostSource,
          contains('_buildBackwardRectoVersoFlippingPageSurface('),
          reason:
              'BACK flipping sheet must split recto/front and verso/back inside '
              'the same soft surface.',
        );
        expect(
          hostSource,
          contains('backwardLeafFrame: frame.backwardLeafFrame'),
          reason:
              'BACK split widths must come from ArticlePageBackwardLeafFrame, '
              'not a second progress curve.',
        );
        expect(
          hostSource,
          contains('_backwardFoldDerivedFacePolygons('),
          reason:
              'recto/verso page-local polygons must be derived from the same '
              'fold line as the BACK sheet, not from a width-only strip.',
        );
        expect(
          hostSource,
          isNot(contains('_buildBackwardLaidDownFrontLayer(')),
          reason:
              'BACK previous-front must not return to the old full pageRect baseline; '
              'Route-B uses an E/free-edge driven flat segment.',
        );
        expect(
          hostSource,
          contains('_buildBackwardFrontFlatLayer('),
          reason:
              'Route-B must compose a distinct S-E previous-front flat segment '
              'between current residual and the rotating back fold band.',
        );
        expect(
          hostSource,
          contains('backwardFrontFlatPolygon('),
          reason:
              'BACK previous-front flat segment must be derived from E/free-edge '
              'and F/foldLine geometry, not from a full baseline.',
        );
        expect(
          hostSource,
          isNot(contains('backwardSheetRectoPolygon(')),
          reason:
              'BACK recto split must be consumed through shared fold-face geometry, '
              'not re-derived in host branches.',
        );
        expect(
          hostSource,
          isNot(contains('backwardSheetVersoPolygon(')),
          reason:
              'BACK previous-back must be consumed through shared fold-face geometry, '
              'not re-derived in host branches.',
        );
        expect(
          hostSource,
          contains('_buildBackwardBackFoldBandSurface('),
          reason:
              'BACK previous-back must use a dedicated fold-band surface so it '
              'keeps the same backside texture and overlay semantics as FORWARD.',
        );
        expect(
          hostSource,
          isNot(contains('backFacePageIndex: scene.currentPageIndex')),
          reason:
              'BACK back/verso texture must stay on the flipping previous leaf; '
              'covered current is only the bottom/current residual.',
        );
        final splitStart = hostSource.indexOf(
          'BackwardFoldFaceGeometry _backwardFoldDerivedFacePolygons',
        );
        final splitEnd = hostSource.indexOf(
          'String? _resolveBackwardPhaseLabel',
          splitStart,
        );
        expect(splitStart, isNonNegative);
        expect(splitEnd, greaterThan(splitStart));
        final splitSource = hostSource.substring(splitStart, splitEnd);
        expect(
          splitSource,
          contains('backwardFoldFaceGeometry('),
          reason:
              'BACK host resolver must delegate to the shared recto/verso F/E geometry helper.',
        );
        expect(
          hostSource,
          isNot(contains('_buildBackwardRectoFacePolygon(')),
          reason:
              'BACK recto/front must not return to the regressed reflection '
              'builder that delayed front visibility to the final phase.',
        );
        expect(
          hostSource,
          isNot(contains('_reflectionMatrixForLine(')),
          reason:
              'previous front must come from the sheet-local F/E polygon; a child '
              'reflection transform moves the texture out of the visible front slice.',
        );
        final backwardSurfaceStart = hostSource.indexOf(
          'Widget _buildBackwardRectoVersoFlippingPageSurface',
        );
        final backwardSurfaceEnd = hostSource.indexOf(
          'Widget _buildBackwardSheetFacePolygon',
          backwardSurfaceStart,
        );
        expect(backwardSurfaceStart, isNonNegative);
        expect(backwardSurfaceEnd, greaterThan(backwardSurfaceStart));
        final backwardSurfaceSource = hostSource.substring(
          backwardSurfaceStart,
          backwardSurfaceEnd,
        );
        expect(
          backwardSurfaceSource,
          contains('ArticlePageSurfaceKind.front'),
          reason:
              'the moving sheet may keep a narrow recto/front seam while Route-B flat '
              'front owns the S-E area.',
        );
        expect(
          backwardSurfaceSource,
          contains('_buildBackwardBackFoldBandSurface('),
          reason:
              'rotating BACK sheet should route previous-back through the '
              'dedicated backside fold-band surface.',
        );
        expect(
          backwardSurfaceSource,
          contains('_backwardFoldDerivedFacePolygons('),
          reason:
              'BACK recto/front and verso/back polygons must come from the same '
              'fold-face geometry resolver.',
        );
        expect(
          RegExp(r'backwardSheetRectoPolygon\(').allMatches(hostSource).length,
          equals(0),
          reason:
              'BACK recto polygon must not be re-derived in diagnostics or fallback branches.',
        );
        expect(
          RegExp(r'backwardSheetVersoPolygon\(').allMatches(hostSource).length,
          equals(0),
          reason:
              'BACK verso polygon must not be re-derived in diagnostics or fallback branches.',
        );
        expect(
          debugMapperSource,
          isNot(contains('backwardSheetVersoPolygon(')),
          reason:
              'diagnostics must not re-derive BACK verso geometry outside the shared resolver.',
        );
        expect(debugMapperSource, contains('backwardFoldFaceGeometry('));
        final backFoldBandStart = hostSource.indexOf(
          'Widget _buildBackwardBackFoldBandSurface',
        );
        final backFoldBandEnd = hostSource.indexOf(
          'Widget _buildBackwardSheetFacePolygon',
          backFoldBandStart,
        );
        expect(backFoldBandStart, isNonNegative);
        expect(backFoldBandEnd, greaterThan(backFoldBandStart));
        final backFoldBandSource = hostSource.substring(
          backFoldBandStart,
          backFoldBandEnd,
        );
        expect(
          backFoldBandSource,
          contains('_buildBackwardVersoTextureSurface('),
          reason:
              'previous-back fold band must use the explicit verso/backface texture path.',
        );
        expect(
          backFoldBandSource,
          contains('_validPageTextureSnapshotForIndex('),
          reason:
              'previous-back fold band must bind the previous/flipping leafVerso snapshot '
              'before painting the E/F back band.',
        );
        final backTextureStart = hostSource.indexOf(
          'Widget _buildBackwardVersoTextureSurface',
        );
        final backTextureEnd = hostSource.indexOf(
          'Widget _buildBackwardSheetFacePolygon',
          backTextureStart,
        );
        expect(backTextureStart, isNonNegative);
        expect(backTextureEnd, greaterThan(backTextureStart));
        final backTextureSource = hostSource.substring(
          backTextureStart,
          backTextureEnd,
        );
        expect(
          backTextureSource,
          isNot(contains('foldCenterX')),
          reason:
              'BACK verso texture must sample in page-space like forward mesh UV, '
              'not around a moving foldLine axis.',
        );
        expect(
          backTextureSource,
          isNot(contains('foldLine')),
          reason:
              'F/foldLine owns geometry only; it must not become the texture mirror axis.',
        );
        expect(
          backTextureSource,
          contains('_BackwardLeafVersoUvPainter'),
          reason:
              'BACK mainline backBand must use a vertex-UV leafVerso painter, '
              'not a whole-widget mirror.',
        );
        expect(
          backTextureSource,
          contains('leafVersoSnapshot'),
          reason:
              'BACK backBand texture must come from the previous/flipping leafVerso snapshot.',
        );
        expect(
          backTextureSource,
          contains('article_backward_leaf_verso_texture_wait'),
          reason:
              'BACK must expose a diagnostic wait state instead of rendering a fake mirrored backface.',
        );
        expect(
          backTextureSource,
          isNot(contains('_buildOpaqueBackPageSurface(')),
          reason:
              'BACK main texture path must not directly render the old opaque mirrored widget.',
        );
        expect(
          hostSource,
          isNot(contains('Widget _buildBackwardVersoTextureFallback')),
          reason:
              'BACK backBand must not keep a visual fallback branch that can draw the wrong texture.',
        );
        final uvPainterStart = hostSource.indexOf(
          'class _BackwardLeafVersoUvPainter',
        );
        expect(uvPainterStart, isNonNegative);
        final uvPainterSource = hostSource.substring(uvPainterStart);
        expect(
          uvPainterSource,
          contains('buildBackwardLeafVersoUvMesh('),
          reason:
              'BACK leafVerso painter must use the shared, testable UV mesh builder.',
        );
        expect(
          uvPainterSource,
          contains('leafVersoSnapshot.image'),
          reason:
              'BACK leafVerso painter must draw the previous/flipping leaf image, not current content.',
        );
        final uvMeshSource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/layers/backward_leaf_verso_uv_mesh.dart',
        );
        expect(
          uvMeshSource,
          contains('textureCoordinates: textureValues'),
          reason:
              'BACK leafVerso mesh must write per-vertex texture coordinates.',
        );
        expect(
          uvMeshSource,
          contains('pageSize.width - localPoint.dx'),
          reason:
              'BACK leafVerso mesh must lock the forward mesh verso UV semantic.',
        );
        expect(
          backFoldBandSource,
          contains('showBackside: true'),
          reason:
              'previous-back fold band must reuse the same backside wash/opacity '
              'overlay as the forward flip back face.',
        );
        expect(
          _readAppSource(
            'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
          ),
          isNot(contains('narrowBackwardBackBandPolygon(')),
          reason:
              'previous-back must not be narrowed by a synthetic vertical guard; '
              'only StPageFlip F/E geometry owns the back band.',
        );
        final softGeometrySource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
        );
        final versoStart = softGeometrySource.indexOf(
          'List<Offset> backwardSheetVersoPolygon',
        );
        final versoEnd = softGeometrySource.indexOf(
          'List<Offset> clipPolygonByLine',
          versoStart,
        );
        expect(versoStart, isNonNegative);
        expect(versoEnd, greaterThan(versoStart));
        final versoSource = softGeometrySource.substring(versoStart, versoEnd);
        expect(
          versoSource,
          isNot(contains('!linesAreParallel(')),
          reason:
              'F/E near-parallel states must still clip the E-F strip instead '
              'of falling into a separate geometry branch.',
        );
        expect(
          versoSource,
          isNot(contains('return foldSidePolygon')),
          reason:
              'BACK backface must never fall back to the unbounded fold side; '
              'that is the large-back regression from the visual reports.',
        );
        expect(
          hostSource,
          contains('(0.06 + progress * 0.04)'),
          reason:
              'product fold boundary must be a subtle paper shadow, not the '
              'colored debug guide line.',
        );
        expect(
          hostSource,
          contains(
            'controller.applyAnimationFrame(plan.frames[lastFrameIndex])',
          ),
          reason:
              'animation completion must apply the final dynamic frame before '
              'committing the static page to avoid a visible refresh jump.',
        );
        expect(
          _readAppSource(
            'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
          ),
          contains('keepPositiveSideForBackwardRecto('),
          reason:
              'host and diagnostics must share the same recto/verso side helper.',
        );
        expect(
          hostSource,
          contains('backwardFreeEdgeLine:'),
          reason:
              'BACK recto/verso side choice should use the canonical free-edge '
              'line when it is available.',
        );
        expect(
          hostSource,
          contains('clipBehavior: Clip.none'),
          reason:
              'BACK face polygons can live in native drawSoft-local space; they must '
              'not be clipped by an inner Stack before the outer paper clip.',
        );
        expect(
          _readAppSource(
            'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
          ),
          contains('clipPolygonByLine('),
          reason:
              'Route-B visible faces must be split by F/fold line half planes, '
              'not by axis-aligned width strips.',
        );
        expect(
          _readAppSource(
            'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
          ),
          contains('polygonLooksLikeFullPageFallback('),
          reason:
              'BACK verso/back must guard against the full-page uncreased fallback.',
        );
        expect(
          hostSource,
          isNot(contains('_singlePageBackwardFlippingDisplayOffset')),
          reason:
              'BACK render/diagnostics must not use a screen-space display offset; '
              'early visibility must come from the forward-isomorphic frame.',
        );
        expect(
          hostSource,
          isNot(contains('rectoCoverage > 0.001')),
          reason:
              'BACK sheet projection must not jump when recto becomes visible; '
              'that makes the back face disappear and the front face pop in.',
        );
        expect(
          splitSource,
          isNot(contains('totalRectoVisibleWidthNormalized > 0.001')),
          reason:
              'BACK front polygon timing must be driven by F/E clipping, not an '
              'independent recto coverage gate.',
        );
        expect(
          splitSource,
          isNot(contains('versoRevealWidthNormalized > 0.001')),
          reason:
              'BACK back polygon timing must be driven by F/E clipping, not an '
              'independent verso width gate.',
        );
        expect(
          hostSource,
          isNot(contains('_buildBackwardPreviousFrontBaselineLayer(')),
          reason:
              'previous front must only appear through the recto slice; a full '
              'baseline replaces the current page at the start of BACK.',
        );
        expect(
          hostSource,
          isNot(contains('article_backward_previous_front_baseline')),
          reason: 'full previous-front baseline is no longer part of BACK.',
        );
        expect(
          _readAppSource(
            'lib/components/pageflip/src/debug/pageflip_diagnostics.dart',
          ),
          contains('debugPureBackwardGeometry: false'),
          reason:
              'diagnostics screen should not show red/cyan geometry guide lines '
              'during normal visual acceptance.',
        );
        expect(hostSource, contains('previousFrontLocalPolygon'));
        expect(hostSource, contains('previousBackLocalPolygon'));
        final backwardDiagnosticStart = hostSource.indexOf(
          '_BackwardDiagnosticGeometry? _resolveBackwardDiagnosticGeometry',
        );
        final backwardDiagnosticEnd = hostSource.indexOf(
          'Rect _backwardPageRect',
          backwardDiagnosticStart,
        );
        expect(backwardDiagnosticStart, isNonNegative);
        expect(backwardDiagnosticEnd, greaterThan(backwardDiagnosticStart));
        final backwardDiagnosticSource = hostSource.substring(
          backwardDiagnosticStart,
          backwardDiagnosticEnd,
        );
        expect(
          backwardDiagnosticSource,
          isNot(contains('previousFrontViewportBounds: null')),
          reason:
              'diagnostics must expose the real previous-front recto polygon '
              'once rectoCoverage is positive.',
        );

        final localPolygonStart = hostSource.indexOf(
          'List<Offset> _localPolygonFromArea',
        );
        final localPolygonEnd = hostSource.indexOf(
          'ArticlePageCurlCorner? _stageCornerForScene',
          localPolygonStart,
        );
        expect(localPolygonStart, isNonNegative);
        expect(localPolygonEnd, greaterThan(localPolygonStart));
        final localPolygonSource = hostSource.substring(
          localPolygonStart,
          localPolygonEnd,
        );
        expect(
          localPolygonSource,
          contains('direction == StPageFlipDirection.back'),
          reason:
              '`_localPolygonFromArea` 必须对齐 StPageFlip HTMLPage.drawSoft：'
              'BACK 用 `anchor.x - p.x`，书脊固定在当前页左边线。',
        );
        expect(
          localPolygonSource,
          contains('anchor.dx - point.dx'),
          reason: 'BACK 原生局部裁剪公式是 `(anchor.x - p.x, p.y - anchor.y)`。',
        );
        expect(
          localPolygonSource,
          contains('point.dx - anchor.dx'),
          reason: 'forward 仍必须保持 `(p - anchor).rotZ(angle)`。',
        );
      },
    );

    test('article reader BACK paint stays symmetrical with FORWARD mainline', () {
      final hostSource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
      );
      final backwardStart = hostSource.indexOf(
        'ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers',
      );
      final backwardGuideStart = hostSource.indexOf(
        'Widget _buildBackwardGeometryGuideLayer',
        backwardStart,
      );
      expect(backwardStart, isNonNegative);
      expect(backwardGuideStart, greaterThan(backwardStart));
      final backwardLayerSource = hostSource.substring(
        backwardStart,
        backwardGuideStart,
      );

      final dynamicLayerCallIndex = backwardLayerSource.indexOf(
        '_buildDynamicPageLayer(',
      );
      expect(dynamicLayerCallIndex, isNonNegative);
      expect(
        backwardLayerSource,
        isNot(contains('_buildBackwardPreviousFrontBaselineLayer(')),
        reason:
            'current page must stay as the bottom page; full previous-front '
            'baseline must not replace it.',
      );
      expect(
        backwardLayerSource,
        contains('direction: StPageFlipDirection.back,'),
      );
      expect(backwardLayerSource, contains('isFlippingPage: false,'));
      expect(backwardLayerSource, contains('isFlippingPage: true,'));

      // 已删的旧分支必须不再出现，避免再次诱导回旧路径。
      expect(
        backwardLayerSource,
        isNot(contains('_buildBackwardCurrentResidualLayer(')),
      );
      expect(
        backwardLayerSource,
        isNot(contains('_buildBackwardPreviousLeafSoftLayer(')),
      );
      expect(
        backwardLayerSource,
        isNot(contains('_buildBackwardPreviousFrontPlaneLayer(')),
      );
      expect(hostSource, isNot(contains('resolveBackwardFoldFrameGeometry(')));
      expect(hostSource, isNot(contains('BackwardFoldSurfaceGeometry')));
      expect(
        hostSource,
        isNot(contains('_buildBackwardGeometryProbeSurface(')),
      );
      expect(hostSource, isNot(contains('_buildBackwardSpineFoldLayer(')));
      expect(hostSource, isNot(contains('resolveBackwardSpineFoldGeometry(')));
      expect(hostSource, isNot(contains('previousFoldSurfacePolygon')));
      expect(hostSource, isNot(contains('previousBackFoldPolygon')));
      expect(hostSource, isNot(contains('previousFrontFoldPolygon')));

      final softGeometrySource = _readAppSource(
        'lib/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart',
      );
      expect(
        softGeometrySource,
        isNot(contains('class BackwardFoldSurfaceGeometry')),
        reason:
            '路线 B 移除 BackwardFoldSurfaceGeometry：渲染消费 flippingClipArea / '
            'bottomClipArea，不再有派生类。',
      );
      expect(
        softGeometrySource,
        isNot(contains('resolveBackwardSoftPageGeometry(')),
        reason:
            'Route B (M1)：BACK 专属 soft helper 已整体废止，渲染主线 / mapper / '
            '测试只走 forward `_resolveDynamicLayerGeometry`。',
      );
      expect(
        softGeometrySource,
        isNot(contains('_resolveBackwardDisplayPosition(')),
        reason:
            'BACK 显示位置由 frame builder X 镜像 + forward `convertBookPointToViewport` '
            '产出，禁止再引入自定义 display position helper。',
      );
      expect(
        softGeometrySource,
        isNot(contains('pageViewportRect')),
        reason: '`pageViewportRect` 仅在已废止的 BACK soft helper 中使用，不得再次出现。',
      );
      expect(
        softGeometrySource,
        isNot(contains('resolveBackwardFoldFrameGeometry(')),
        reason: '所有 BACK 派生几何已迁回 calc 真相源。',
      );
      expect(
        softGeometrySource,
        isNot(contains('_resolveBackwardDisplaySheetBand(')),
      );
      expect(softGeometrySource, isNot(contains('_pageRectBandPolygon(')));
      expect(
        softGeometrySource,
        isNot(contains('_resolveBottomAreaBoundaryLine(')),
      );
      expect(
        softGeometrySource,
        isNot(contains('_clampBackwardPageEdgeBeforeFold(')),
      );
      expect(
        softGeometrySource,
        contains('return direction;'),
        reason:
            '`softLayerViewportDirection` 必须对齐 StPageFlip convertToGlobal，'
            'BACK 不能强行走 forward 投影。',
      );
    });

    test(
      'BACK verso polygon remains an E-F strip when fold/free-edge are parallel',
      () {
        const pageSize = Size(400, 600);
        final polygon = backwardSheetVersoPolygon(
          pageSize: pageSize,
          sheetLocalPolygon: pageRectPolygon(pageSize),
          foldLine: const (Offset(160, 0), Offset(160, 600)),
          freeEdgeLine: const (Offset(100, 0), Offset(100, 600)),
        );

        expect(polygon, hasLength(greaterThanOrEqualTo(3)));
        final bounds = polygonBounds(polygon);
        expect(bounds, isNotNull);
        expect(bounds!.left, closeTo(100, 0.001));
        expect(bounds.right, closeTo(160, 0.001));
        expect(
          bounds.width,
          lessThan(pageSize.width * 0.25),
          reason:
              'parallel F/E must form a narrow fold strip, not the whole fold side.',
        );
        expect(
          bounds.width,
          greaterThan(pageSize.width * 0.10),
          reason:
              'parallel F/E must not collapse to the near-invisible 5px band.',
        );
      },
    );

    test('BACK verso polygon is empty without a free edge boundary', () {
      const pageSize = Size(400, 600);
      final polygon = backwardSheetVersoPolygon(
        pageSize: pageSize,
        sheetLocalPolygon: pageRectPolygon(pageSize),
        foldLine: const (Offset(160, 0), Offset(160, 600)),
        freeEdgeLine: null,
      );

      expect(
        polygon,
        isEmpty,
        reason:
            'BACK backface must not display the unbounded fold side when E/free-edge is unavailable.',
      );
    });

    test('BACK leafVerso UV mirrors asymmetric page-local samples', () {
      const pageSize = Size(400, 600);
      final mesh = buildBackwardLeafVersoUvMesh(
        pageSize: pageSize,
        polygon: const <Offset>[
          Offset(40, 120),
          Offset(260, 120),
          Offset(260, 480),
          Offset(40, 480),
        ],
      );

      expect(mesh, isNotNull);
      expect(
        mesh!.textureCoordinates,
        equals(const <Offset>[
          Offset(360, 120),
          Offset(140, 120),
          Offset(140, 480),
          Offset(360, 480),
        ]),
        reason:
            'BACK leafVerso must sample the previous leaf as a paper-back mirror, '
            'matching forward mesh `pageSize.width - localX` semantics.',
      );
      expect(mesh.indices, equals(<int>[0, 1, 2, 0, 2, 3]));
    });

    test('BACK leafVerso UV preserves Route-B overflow local coordinates', () {
      const pageSize = Size(400, 600);
      const overflowPolygon = <Offset>[
        Offset(-72, 96),
        Offset(456, 96),
        Offset(428, 504),
        Offset(-44, 504),
      ];

      final mesh = buildBackwardLeafVersoUvMesh(
        pageSize: pageSize,
        polygon: overflowPolygon,
      );

      expect(mesh, isNotNull);
      expect(
        mesh!.positions,
        equals(overflowPolygon),
        reason:
            'Route-B BACK can produce drawSoft-local X outside the page; '
            'the UV mesh must not clamp those vertices back onto page edges.',
      );
      expect(
        mesh.textureCoordinates,
        equals(const <Offset>[
          Offset(472, 96),
          Offset(-56, 96),
          Offset(-28, 504),
          Offset(444, 504),
        ]),
        reason:
            'Verso sampling must mirror raw local X with pageWidth - localX; '
            'ImageShader clamp handles texture edge sampling, not geometry.',
      );
      expect(mesh.indices, equals(<int>[0, 1, 2, 0, 2, 3]));
    });

    test('BACK leafVerso UV drops duplicate points and rejects zero area', () {
      const pageSize = Size(400, 600);
      final dedupedMesh = buildBackwardLeafVersoUvMesh(
        pageSize: pageSize,
        polygon: const <Offset>[
          Offset(-20, 80),
          Offset(-20, 80),
          Offset(240, 80),
          Offset(240, 420),
          Offset(-20, 420),
          Offset(-20, 80),
        ],
      );

      expect(dedupedMesh, isNotNull);
      expect(
        dedupedMesh!.positions,
        equals(const <Offset>[
          Offset(-20, 80),
          Offset(240, 80),
          Offset(240, 420),
          Offset(-20, 420),
        ]),
      );
      expect(dedupedMesh.indices, equals(<int>[0, 1, 2, 0, 2, 3]));

      final flatMesh = buildBackwardLeafVersoUvMesh(
        pageSize: pageSize,
        polygon: const <Offset>[
          Offset(80, 120),
          Offset(200, 120),
          Offset(320, 120),
        ],
      );

      expect(
        flatMesh,
        isNull,
        reason:
            'Degenerate BACK polygons must wait instead of painting an edge strip.',
      );
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
      'backward pipeline keeps current static and owns only previous leaf paint',
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
          isNot(contains(textureBinding.bottomPageIndex)),
          reason:
              'BACK must keep the current page visible as the static bottom; '
              'previous-front can only appear through the moving sheet recto slice.',
        );
        expect(output.renderBranchName, 'backwardPaperFoldMainlinePipeline');
        expect(output.debugLabel, 'backward/paper-fold-mainline');

        final hostSource = _readAppSource(
          'lib/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart',
        );
        final backwardStart = hostSource.indexOf(
          'ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers',
        );
        final backwardGuideStart = hostSource.indexOf(
          'Widget _buildBackwardGeometryGuideLayer',
          backwardStart,
        );
        final backwardLayerSource = hostSource.substring(
          backwardStart,
          backwardGuideStart,
        );
        expect(
          backwardLayerSource,
          isNot(contains('_buildBackwardPreviousFrontBaselineLayer(')),
          reason: 'BACK 不允许 full previous-front baseline 替换 current page。',
        );
        expect(
          backwardLayerSource,
          contains('_buildDynamicPageLayer('),
          reason: 'BACK 渲染必须复用与前翻同一份 _buildDynamicPageLayer。',
        );
        expect(
          backwardLayerSource,
          isNot(contains('_buildBackwardCurrentResidualLayer(')),
          reason: '旧 BACK current 残片层已废弃，禁止再次出现。',
        );
        expect(
          backwardLayerSource,
          isNot(contains('_buildBackwardPreviousLeafSoftLayer(')),
          reason: '旧 BACK leaf soft 层已废弃，禁止再次出现。',
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
      // Backward 主线统一：semantic BACK 绑定不变，portrait visual polygon
      // 来自 forward-isomorphic calculation，不再走 seam 矩形伪几何。
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
      final replayLocalPoint = resolveBackwardVisualReplayLocalPagePoint(
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

    test('backward portrait frame uses forward-isomorphic visual geometry', () {
      // 后翻语义仍是 BACK，但某一静态时刻的 F/E/clip/current residual
      // 必须与 forward 纸张姿态同构，差别只在页面绑定和时间方向。
      const pageSize = Size(420, 584);
      const localPagePoint = Offset(-96, 496);
      final replayPoint = resolveBackwardVisualReplayLocalPagePoint(
        localPagePoint: localPagePoint,
        pageSize: pageSize,
      );
      final backCalculation = StPageFlipCalculation(
        direction: StPageFlipDirection.back,
        corner: StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      expect(backCalculation.calc(localPagePoint), isTrue);
      final canonicalGeometry = backCalculation.getCanonicalFoldGeometry();
      expect(canonicalGeometry, isNotNull);
      final forwardCalculation = StPageFlipCalculation(
        direction: StPageFlipDirection.forward,
        corner: StPageFlipCorner.bottom,
        pageWidth: pageSize.width,
        pageHeight: pageSize.height,
      );
      expect(forwardCalculation.calc(replayPoint), isTrue);
      final forwardGeometry = forwardCalculation.getCanonicalFoldGeometry();
      expect(forwardGeometry, isNotNull);

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
          foldLine: canonicalGeometry!.foldLine,
          freeEdgeLine: canonicalGeometry.freeEdgeLine,
          maxShadowOpacity: 0.2,
        ),
      );

      expect(frame.direction, StPageFlipDirection.back);
      expect(frame.renderDirection, StPageFlipDirection.back);
      expect(frame.visualGeometryDirection, StPageFlipDirection.forward);
      expect(
        frame.routeBSpineMirroredApplied,
        isTrue,
        reason: 'portrait BACK visual geometry must be forward-isomorphic.',
      );
      expect(frame.flippingAnchor, forwardCalculation.getActiveCorner());
      expect(frame.bottomAnchor, forwardCalculation.getBottomPagePosition());
      expect(frame.angle, closeTo(forwardCalculation.getAngle(), 1e-9));
      expect(frame.flippingClipArea, forwardCalculation.getFlippingClipArea());
      expect(frame.bottomClipArea, forwardCalculation.getBottomClipArea());

      final projectedFrame = frame.backwardProjectedFrame;
      expect(projectedFrame, isNotNull);
      expect(
        projectedFrame!.foldLine,
        orderPageLineTopToBottom(forwardGeometry!.foldLine),
      );
      expect(
        projectedFrame.projectedRightEdgeLine,
        orderPageLineTopToBottom(forwardGeometry.freeEdgeLine),
      );
      expect(
        projectedFrame.foldLineSource,
        'backwardForwardIsomorphicFoldLine',
      );
      expect(
        projectedFrame.edgeLineSource,
        'backwardForwardIsomorphicFreeEdgeLine',
      );
      expect(projectedFrame.edgeEnteredPage, isTrue);
    });

    test(
      'backward landscape frame leaves geometry untouched (route B M1 scope)',
      () {
        // landscape 双页 BACK 不在路线 B 范围，frame builder 不应对几何做镜像。
        const pageSize = Size(420, 584);
        const localPagePoint = Offset(-96, 496);
        final backCalculation = StPageFlipCalculation(
          direction: StPageFlipDirection.back,
          corner: StPageFlipCorner.bottom,
          pageWidth: pageSize.width,
          pageHeight: pageSize.height,
        );
        expect(backCalculation.calc(localPagePoint), isTrue);
        final canonicalGeometry = backCalculation.getCanonicalFoldGeometry();
        expect(canonicalGeometry, isNotNull);

        final frame = buildBackwardDynamicRenderFrame(
          BackwardRenderFrameData(
            localPagePoint: localPagePoint,
            progress: 0.42,
            orientation: StPageFlipOrientation.landscape,
            corner: StPageFlipCorner.bottom,
            pageSize: pageSize,
            flippingClipArea: backCalculation.getFlippingClipArea(),
            bottomClipArea: backCalculation.getBottomClipArea(),
            flippingAnchor: backCalculation.getActiveCorner(),
            bottomAnchor: backCalculation.getBottomPagePosition(),
            angle: backCalculation.getAngle(),
            foldLine: canonicalGeometry!.foldLine,
            freeEdgeLine: canonicalGeometry.freeEdgeLine,
            maxShadowOpacity: 0.2,
          ),
        );

        expect(frame.routeBSpineMirroredApplied, isFalse);
        expect(frame.visualGeometryDirection, StPageFlipDirection.back);
        expect(frame.flippingAnchor, backCalculation.getActiveCorner());
        expect(frame.bottomAnchor, backCalculation.getBottomPagePosition());
        expect(frame.angle, closeTo(backCalculation.getAngle(), 1e-9));
        expect(frame.flippingClipArea, backCalculation.getFlippingClipArea());
        expect(frame.bottomClipArea, backCalculation.getBottomClipArea());
      },
    );

    test(
      'backward projected frame exposes forward-isomorphic fold/free-edge lines',
      () {
        // 路线 B：projected frame 仅承载同构 F/E 诊断线。
        // F/E 可超出 page rect；真正的可见分段由 host 内的 polygon-by-line
        // 裁剪负责，projected frame 不应再把同构线强行裁短。
        const pageSize = Size(420, 584);
        const localPoints = <Offset>[
          Offset(-48, 520),
          Offset(-124, 506),
          Offset(-220, 492),
        ];
        final visualReplayXs = <double>[];

        for (var index = 0; index < localPoints.length; index += 1) {
          final replayPoint = resolveBackwardVisualReplayLocalPagePoint(
            localPagePoint: localPoints[index],
            pageSize: pageSize,
          );
          visualReplayXs.add(replayPoint.dx);
          final calculation = StPageFlipCalculation(
            direction: StPageFlipDirection.back,
            corner: StPageFlipCorner.bottom,
            pageWidth: pageSize.width,
            pageHeight: pageSize.height,
          );
          expect(calculation.calc(localPoints[index]), isTrue);
          final canonicalGeometry = calculation.getCanonicalFoldGeometry();
          expect(canonicalGeometry, isNotNull);
          final forwardCalculation = StPageFlipCalculation(
            direction: StPageFlipDirection.forward,
            corner: StPageFlipCorner.bottom,
            pageWidth: pageSize.width,
            pageHeight: pageSize.height,
          );
          expect(forwardCalculation.calc(replayPoint), isTrue);
          final forwardGeometry = forwardCalculation.getCanonicalFoldGeometry();
          expect(forwardGeometry, isNotNull);
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
              foldLine: canonicalGeometry!.foldLine,
              freeEdgeLine: canonicalGeometry.freeEdgeLine,
              maxShadowOpacity: 0.2,
            ),
          );
          final projectedFrame = frame.backwardProjectedFrame;
          expect(projectedFrame, isNotNull);
          expect(projectedFrame!.replayLocalPoint, replayPoint);
          expect(
            projectedFrame.foldLine,
            orderPageLineTopToBottom(forwardGeometry!.foldLine),
          );
          expect(
            projectedFrame.projectedRightEdgeLine,
            orderPageLineTopToBottom(forwardGeometry.freeEdgeLine),
          );
          expect(
            projectedFrame.edgeLineSource,
            'backwardForwardIsomorphicFreeEdgeLine',
          );
        }
        expect(
          visualReplayXs,
          orderedEquals(visualReplayXs.toList()..sort()),
          reason:
              'BACK 向右拖时，同构 forward visual pose 必须从左向右推进，'
              '不能沿用前翻的右到左输入时间。',
        );
        expect(
          visualReplayXs.first,
          lessThan(0),
          reason:
              '刚开始后翻必须映射到 forward 完成态的负 X 区间，'
              '让 previous 从书脊左侧不可见区进入。',
        );
        expect(
          visualReplayXs.last,
          greaterThan(0),
          reason: '继续后翻时 visual pose 必须越过书脊向右推进。',
        );
      },
    );

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
