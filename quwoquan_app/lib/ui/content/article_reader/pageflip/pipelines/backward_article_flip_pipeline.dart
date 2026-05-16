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
    };
    return ArticleFlipPipelineOutput(
      direction: direction,
      staticSuppressionPages: dynamicOwnedPages,
      renderBranchName: 'backwardPaperFoldMainlinePipeline',
      debugLabel: hasBackwardFoldFrame
          ? 'backward/paper-fold-mainline'
          : 'backward/waiting-fold-frame',
    );
  }
}
