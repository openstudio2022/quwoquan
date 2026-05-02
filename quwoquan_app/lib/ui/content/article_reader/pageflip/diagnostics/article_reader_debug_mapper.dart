import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_debug_state.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/diagnostics/article_reader_diagnostic_signatures.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class ArticleReaderDebugMapper {
  const ArticleReaderDebugMapper();

  ArticleReaderPipelineDebugState mapPipelineOutput({
    required ArticleFlipPipelineOutput output,
    required ArticleFlipPipelineInput input,
  }) {
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
                  input.renderFrame.backwardProjectedFrame == null
                  ? null
                  : polygonBounds(
                      input
                          .renderFrame
                          .backwardProjectedFrame!
                          .currentResidualPolygon,
                    ),
              backVertexCount: input
                  .renderFrame
                  .backwardProjectedFrame
                  ?.previousBackPolygon
                  .length,
              frontVertexCount: input
                  .renderFrame
                  .backwardProjectedFrame
                  ?.previousFrontPolygon
                  .length,
              edgeEnteredPage:
                  input.renderFrame.backwardProjectedFrame?.edgeEnteredPage,
              backPolygonPoints:
                  input.renderFrame.backwardProjectedFrame == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      input
                          .renderFrame
                          .backwardProjectedFrame!
                          .previousBackPolygon,
                    ),
              frontPolygonPoints:
                  input.renderFrame.backwardProjectedFrame == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      input
                          .renderFrame
                          .backwardProjectedFrame!
                          .previousFrontPolygon,
                    ),
              currentPolygonPoints:
                  input.renderFrame.backwardProjectedFrame == null
                  ? null
                  : articleDiagnosticPolygonSignature(
                      input
                          .renderFrame
                          .backwardProjectedFrame!
                          .currentResidualPolygon,
                    ),
            )
          : null,
    );
  }
}
