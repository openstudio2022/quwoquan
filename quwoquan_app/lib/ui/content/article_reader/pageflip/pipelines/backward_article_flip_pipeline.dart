import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class BackwardArticleFlipPipeline extends ArticleFlipPipeline {
  const BackwardArticleFlipPipeline();

  @override
  StPageFlipDirection get direction => StPageFlipDirection.back;

  @override
  ArticleFlipPipelineOutput resolve(ArticleFlipPipelineInput input) {
    final projectedFrame = input.renderFrame.backwardProjectedFrame;
    final dynamicOwnedPages = <int>{
      if (projectedFrame != null && input.scene.flippingPageIndex != null)
        input.scene.flippingPageIndex!,
      if (projectedFrame != null &&
          input.textureBinding?.bottomPageIndex != null)
        input.textureBinding!.bottomPageIndex!,
      if (projectedFrame != null && input.scene.bottomPageIndex != null)
        input.scene.bottomPageIndex!,
    };
    return ArticleFlipPipelineOutput(
      direction: direction,
      staticSuppressionPages: dynamicOwnedPages,
      renderBranchName: 'backwardThreeLayerPaperFoldPipeline',
      debugLabel: projectedFrame == null
          ? 'backward/waiting-projection'
          : 'backward/three-layer-paper-fold',
    );
  }
}
