import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

class ForwardArticleFlipPipeline extends ArticleFlipPipeline {
  const ForwardArticleFlipPipeline();

  @override
  StPageFlipDirection get direction => StPageFlipDirection.forward;

  @override
  ArticleFlipPipelineOutput resolve(ArticleFlipPipelineInput input) {
    final pages = <int>{
      if (input.textureBinding != null)
        ...input.textureBinding!.requiredPageIndices,
    };
    return ArticleFlipPipelineOutput(
      direction: direction,
      staticSuppressionPages: pages,
      renderBranchName: 'forwardSharedPipeline',
      debugLabel: 'forward/shared',
    );
  }
}
