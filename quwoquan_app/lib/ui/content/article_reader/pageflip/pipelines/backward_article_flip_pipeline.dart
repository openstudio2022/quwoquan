import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class BackwardArticleFlipPipeline extends ArticleFlipPipeline {
  const BackwardArticleFlipPipeline();

  @override
  StPageFlipDirection get direction => StPageFlipDirection.back;

  @override
  ArticleFlipPipelineOutput resolve(ArticleFlipPipelineInput input) {
    final hasBackwardFoldFrame =
        input.renderFrame.flippingClipArea.length >= 3 &&
        input.renderFrame.bottomClipArea.length >= 3;
    final dynamicOwnedPages = <int>{
      if (hasBackwardFoldFrame && input.scene.flippingPageIndex != null)
        input.scene.flippingPageIndex!,
      if (hasBackwardFoldFrame && input.textureBinding?.bottomPageIndex != null)
        input.textureBinding!.bottomPageIndex!,
      if (hasBackwardFoldFrame && input.scene.bottomPageIndex != null)
        input.scene.bottomPageIndex!,
    };
    return ArticleFlipPipelineOutput(
      direction: direction,
      staticSuppressionPages: dynamicOwnedPages,
      renderBranchName: 'backwardThreeFacePaperFoldPipeline',
      debugLabel: hasBackwardFoldFrame
          ? 'backward/three-face-paper-fold'
          : 'backward/waiting-fold-frame',
    );
  }
}
