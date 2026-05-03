import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/modes/single_page_mode_strategy.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart';
import 'package:quwoquan_app/ui/content/pageflip/book_layout.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/ui/content/pageflip/spread_model.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

void main() {
  test('article reader pipelines isolate forward and backward outputs', () {
    final forwardScene = _interactiveScene(
      initialPage: 1,
      startPoint: const Offset(400, 650),
      foldPoint: const Offset(300, 620),
    );
    final backwardScene = _interactiveScene(
      initialPage: 2,
      startPoint: const Offset(18, 650),
      foldPoint: const Offset(120, 510),
    );

    final forwardOutput = const ForwardArticleFlipPipeline().resolve(
      _pipelineInput(forwardScene),
    );
    final backwardOutput = const BackwardArticleFlipPipeline().resolve(
      _pipelineInput(backwardScene),
    );

    expect(forwardOutput.direction, StPageFlipDirection.forward);
    expect(backwardOutput.direction, StPageFlipDirection.back);
    expect(forwardOutput.renderBranchName, equals('forwardSharedPipeline'));
    expect(
      backwardOutput.renderBranchName,
      equals('backwardThreeFacePaperFoldPipeline'),
    );
    expect(
      backwardOutput.staticSuppressionPages,
      contains(backwardScene.flippingPageIndex),
    );
    expect(
      forwardOutput.renderBranchName,
      isNot(equals(backwardOutput.renderBranchName)),
      reason: 'direction-specific behavior must stay in local pipeline classes',
    );
  });
}

StPageFlipScene _interactiveScene({
  required int initialPage,
  required Offset startPoint,
  required Offset foldPoint,
}) {
  final controller = StPageFlipController(
    spreadModel: StPageFlipSpreadModel(pageCount: 5),
    layout: computeStPageFlipLayout(
      viewportSize: const Size(430, 900),
      pageWidth: 398,
      pageHeight: 553,
      usePortrait: true,
    ),
    initialPage: initialPage,
  );
  expect(controller.start(startPoint), isTrue);
  controller.fold(foldPoint);
  expect(controller.scene.renderFrame, isNotNull);
  return controller.scene;
}

ArticleFlipPipelineInput _pipelineInput(StPageFlipScene scene) {
  final binding = resolveArticlePageTextureBinding(
    direction: scene.direction!,
    flippingPageIndex: scene.flippingPageIndex!,
    bottomPageIndex: scene.bottomPageIndex!,
    currentPageIndex: scene.currentPageIndex,
  );
  return ArticleFlipPipelineInput(
    scene: scene,
    renderFrame: scene.renderFrame!,
    pageSize: Size(scene.layout.bounds.pageWidth, scene.layout.bounds.height),
    modeLayout: const SinglePageModeStrategy().resolveLayout(
      scene: scene,
      dynamicallyRenderedPages: const <int>{},
    ),
    textureBinding: binding,
    textureBundle: null,
  );
}
