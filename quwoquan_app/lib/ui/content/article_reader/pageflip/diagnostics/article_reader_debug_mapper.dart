import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_state.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class ArticleReaderDebugMapper {
  const ArticleReaderDebugMapper();

  ArticleReaderPipelineDebugState mapPipelineOutput({
    required ArticleFlipPipelineOutput output,
    required ArticleFlipPipelineInput input,
  }) {
    final backwardProjectedFrame = input.renderFrame.backwardProjectedFrame;
    final backwardGeometry =
        output.direction == StPageFlipDirection.back &&
            backwardProjectedFrame != null
        ? resolveBackwardFoldFrameGeometry(
            flippingArea: input.renderFrame.flippingClipArea,
            bottomArea: input.renderFrame.bottomClipArea,
            anchor: input.renderFrame.flippingAnchor,
            angle: input.renderFrame.angle,
            foldLine: backwardProjectedFrame.foldLine,
            freeEdgeLine: backwardProjectedFrame.projectedRightEdgeLine,
            frontBackBoundaryLine: backwardProjectedFrame.frontBackBoundaryLine,
            rectoCoverageNormalized:
                input.renderFrame.backwardLeafFrame?.rectoCoverageNormalized ??
                0,
            bounds: input.scene.layout.bounds,
            pageSize: input.pageSize,
            pageViewportRect: resolveBookPageRect(
              input.scene.layout,
              isRightPage: true,
            ),
          )
        : null;
    return ArticleReaderPipelineDebugState(
      pipelineName: output.debugLabel ?? output.renderBranchName,
      renderBranchName: output.renderBranchName,
      backward: output.direction == StPageFlipDirection.back
          ? BackwardDebugState(
              coveredPageIndex: input.textureBinding?.bottomPageIndex,
              leafRectoPageIndex: input.textureBinding?.rectoPageIndex,
              leafVersoPageIndex: input.textureBinding?.versoPageIndex,
              mainline: output.renderBranchName,
              phase: input.renderFrame.backwardLeafFrame?.phase.name,
              currentResidualBounds:
                  backwardGeometry?.currentResidualViewportBounds,
              backVertexCount:
                  backwardGeometry?.previousBackLocalPolygon.length,
              frontVertexCount:
                  backwardGeometry?.previousFrontViewportPolygon.length,
              edgeEnteredPage: backwardGeometry != null,
              backPolygonPoints: backwardGeometry == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      backwardGeometry.previousBackLocalPolygon,
                    ),
              frontPolygonPoints: backwardGeometry == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      backwardGeometry.previousFrontViewportPolygon,
                    ),
              sheetPolygonPoints: backwardGeometry == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      backwardGeometry.sheetViewportPolygon,
                    ),
              bottomClipPolygonPoints:
                  input.renderFrame.bottomClipArea.length < 3
                  ? null
                  : articleDiagnosticPolygonSignature(
                      input.renderFrame.bottomClipArea,
                    ),
              currentPolygonPoints: backwardGeometry == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      backwardGeometry.currentResidualViewportPolygon,
                    ),
            )
          : null,
    );
  }
}
