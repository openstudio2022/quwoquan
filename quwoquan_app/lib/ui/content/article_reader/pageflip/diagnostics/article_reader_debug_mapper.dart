import 'dart:ui';

import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_state.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

/// Diagnostic mapper follows the same StPageFlip native BACK soft render as
/// the host: BACK uses `(anchor.x - p.x, p.y - anchor.y)` and BACK projection,
/// so the previous page enters from the visible current page's left spine.
class ArticleReaderDebugMapper {
  const ArticleReaderDebugMapper();

  ArticleReaderPipelineDebugState mapPipelineOutput({
    required ArticleFlipPipelineOutput output,
    required ArticleFlipPipelineInput input,
  }) {
    final flippingArea = input.renderFrame.flippingClipArea;
    final isBackward = output.direction == StPageFlipDirection.back;
    List<Offset> sheetLocalPolygon = const <Offset>[];
    List<Offset> sheetViewportPolygon = const <Offset>[];
    List<Offset> frontLocalPolygon = const <Offset>[];
    List<Offset> backLocalPolygon = const <Offset>[];
    List<Offset> currentResidualViewportPolygon = const <Offset>[];
    Rect? currentResidualViewportBounds;
    bool edgeEnteredPage = false;
    if (isBackward && flippingArea.length >= 3) {
      final pageRect = resolveBookPageRect(
        input.scene.layout,
        isRightPage: true,
      );
      final anchor = input.renderFrame.flippingAnchor;
      final angle = input.renderFrame.angle;
      final pageSize = Size(
        input.scene.layout.bounds.pageWidth,
        input.scene.layout.bounds.height,
      );
      final settledProgress = input.renderFrame.progress.clamp(0.0, 1.0);
      final displayFactor = 0.35 - settledProgress * (0.35 - 0.18);
      final rectoCoverage =
          input.renderFrame.backwardLeafFrame?.rectoCoverageNormalized ?? 0;
      final positionViewport =
          convertBookPointToViewport(
            anchor,
            input.scene.layout.bounds,
            direction: StPageFlipDirection.back,
          ) +
          (rectoCoverage > 0.001
              ? Offset.zero
              : Offset(pageSize.width * displayFactor, 0));
      sheetLocalPolygon = flippingArea
          .map((p) {
            final translated = Offset(anchor.dx - p.dx, p.dy - anchor.dy);
            return rotatePointForCanvasTransform(translated, angle);
          })
          .toList(growable: false);
      sheetViewportPolygon = sheetLocalPolygon
          .map((p) => positionViewport + p)
          .toList(growable: false);
      final leafFrame = input.renderFrame.backwardLeafFrame;
      if (leafFrame != null) {
        List<Offset> intervalToClipPolygon(double startX, double endX) {
          if (endX <= startX) {
            return const <Offset>[];
          }
          return <Offset>[
            Offset(startX, 0),
            Offset(endX, 0),
            Offset(endX, pageSize.height),
            Offset(startX, pageSize.height),
          ];
        }

        final rectoWidth =
            pageSize.width * leafFrame.totalRectoVisibleWidthNormalized;
        final coveredWidth = pageSize.width * leafFrame.coveredWidthNormalized;
        frontLocalPolygon = intervalToClipPolygon(0, rectoWidth);
        backLocalPolygon = intervalToClipPolygon(rectoWidth, coveredWidth);
      } else {
        backLocalPolygon = sheetLocalPolygon;
      }
      if (input.renderFrame.bottomClipArea.length >= 3) {
        currentResidualViewportPolygon = input.renderFrame.bottomClipArea
            .map((p) => pageRect.topLeft + p)
            .toList(growable: false);
        currentResidualViewportBounds = polygonBounds(
          currentResidualViewportPolygon,
        );
      }
      edgeEnteredPage = true;
    }
    return ArticleReaderPipelineDebugState(
      pipelineName: output.debugLabel ?? output.renderBranchName,
      renderBranchName: output.renderBranchName,
      backward: isBackward
          ? BackwardDebugState(
              coveredPageIndex: input.textureBinding?.bottomPageIndex,
              leafRectoPageIndex: input.textureBinding?.rectoPageIndex,
              leafVersoPageIndex: input.textureBinding?.versoPageIndex,
              mainline: output.renderBranchName,
              phase: input.renderFrame.backwardLeafFrame?.phase.name,
              currentResidualBounds: currentResidualViewportBounds,
              backVertexCount: backLocalPolygon.length,
              frontVertexCount: frontLocalPolygon.length,
              edgeEnteredPage: edgeEnteredPage,
              backPolygonPoints: backLocalPolygon.length < 3
                  ? null
                  : articleDiagnosticPolygonSignature(backLocalPolygon),
              frontPolygonPoints: frontLocalPolygon.length < 3
                  ? null
                  : articleDiagnosticPolygonSignature(frontLocalPolygon),
              sheetPolygonPoints: sheetViewportPolygon.length < 3
                  ? null
                  : articleDiagnosticPolygonSignature(sheetViewportPolygon),
              bottomClipPolygonPoints:
                  input.renderFrame.bottomClipArea.length < 3
                  ? null
                  : articleDiagnosticPolygonSignature(
                      input.renderFrame.bottomClipArea,
                    ),
              currentPolygonPoints: currentResidualViewportPolygon.length < 3
                  ? null
                  : articleDiagnosticPolygonSignature(
                      currentResidualViewportPolygon,
                    ),
            )
          : null,
    );
  }
}
