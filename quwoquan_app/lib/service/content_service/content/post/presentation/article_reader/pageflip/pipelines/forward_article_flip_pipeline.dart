import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/design_system/pageflip/types.dart';

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
