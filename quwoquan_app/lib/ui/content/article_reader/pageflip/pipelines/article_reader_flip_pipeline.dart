import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/article_reader_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ArticleFlipPipelineInput {
  const ArticleFlipPipelineInput({
    required this.scene,
    required this.renderFrame,
    required this.pageSize,
    required this.modeLayout,
    required this.textureBinding,
    required this.textureBundle,
  });

  final StPageFlipScene scene;
  final StPageFlipRenderFrame renderFrame;
  final Size pageSize;
  final ArticleReaderModeLayout modeLayout;
  final ArticlePageTextureBinding? textureBinding;
  final ArticlePageTextureBundle? textureBundle;
}

@immutable
class ArticleFlipPipelineOutput {
  const ArticleFlipPipelineOutput({
    required this.direction,
    required this.staticSuppressionPages,
    required this.renderBranchName,
    this.debugLabel,
  });

  final StPageFlipDirection direction;
  final Set<int> staticSuppressionPages;
  final String renderBranchName;
  final String? debugLabel;
}

abstract class ArticleFlipPipeline {
  const ArticleFlipPipeline();

  StPageFlipDirection get direction;

  ArticleFlipPipelineOutput resolve(ArticleFlipPipelineInput input);
}
