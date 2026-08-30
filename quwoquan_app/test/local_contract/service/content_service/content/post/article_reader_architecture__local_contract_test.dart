// spec_ref: specs/feature-tree/discovery-content/feed-orchestration-recommendation/streaming-feed-performance/spec.md#gwt-002
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-020.t2

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/modes/single_page_mode_strategy.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/pipelines/article_reader_flip_pipeline.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/pipelines/backward_article_flip_pipeline.dart';
import 'package:quwoquan_app/service/content_service/content/post/presentation/article_reader/pageflip/pipelines/forward_article_flip_pipeline.dart';
import 'package:quwoquan_app/design_system/pageflip/book_layout.dart';
import 'package:quwoquan_app/design_system/pageflip/controller.dart';
import 'package:quwoquan_app/design_system/pageflip/page_surface_snapshot.dart';
import 'package:quwoquan_app/design_system/pageflip/spread_model.dart';
import 'package:quwoquan_app/design_system/pageflip/types.dart';
import 'package:quwoquan_app/service/content_service/content/post/domain/article_presentation_models.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_presentation_values.dart';

void main() {
  testWidgets('article page textures stay inside the current page window', (
    tester,
  ) async {
    await tester.binding.setSurfaceSize(const Size(430, 800));
    addTearDown(() => tester.binding.setSurfaceSize(null));
    final pages = List<ArticlePageData>.unmodifiable(
      List<ArticlePageData>.generate(
        12,
        (index) => ArticlePageData(
          id: 'page_$index',
          title: 'Page $index',
          body: 'Bounded page texture cache $index',
        ),
      ),
    );
    final debugStates = <ArticleReadOnlyBookDebugState>[];
    var initialPage = 1;
    late StateSetter rebuildDeck;

    await tester.pumpWidget(
      MaterialApp(
        home: StatefulBuilder(
          builder: (context, setState) {
            rebuildDeck = setState;
            return ArticleReadOnlyBookDeck(
              pages: pages,
              template: ArticleTemplatePreset.gentle,
              fontPreset: ArticleFontPreset.clean,
              metrics: ArticleCanvasMetrics.snapshot(),
              enablePageCurl: true,
              initialPage: initialPage,
              onDebugStateChanged: debugStates.add,
            );
          },
        ),
      ),
    );
    await tester.pumpAndSettle();

    for (final page in <int>[4, 7, 10]) {
      rebuildDeck(() => initialPage = page);
      await tester.pumpAndSettle();
    }

    final latest = debugStates.lastWhere(
      (state) => state.currentPageIndex == 10,
    );
    expect(
      latest.availableSnapshotIndices.length,
      lessThanOrEqualTo(ArticleReadOnlyBookDeck.maxResidentPageTextures),
    );
    expect(
      latest.availableSnapshotIndices,
      everyElement(isIn(<int>{9, 10, 11})),
    );
    expect(latest.pendingCaptureIndices, everyElement(isIn(<int>{9, 10, 11})));
  });

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
      equals('backwardPaperFoldMainlinePipeline'),
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

  test(
    'business article readers enter pageflip only through host adapters',
    () {
      final libDir = Directory('lib').existsSync()
          ? Directory('lib')
          : Directory('quwoquan_app/lib');
      expect(libDir.existsSync(), isTrue);

      const allowedDirectDeckEntrypoints = <String>{
        'lib/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart',
        'lib/service/content_service/content/post/presentation/article_reader/pageflip/host/article_reader_flip_host.dart',
      };

      final offenders = <String>[];
      for (final entity in libDir.listSync(recursive: true)) {
        if (entity is! File || !entity.path.endsWith('.dart')) {
          continue;
        }
        final normalizedPath = entity.path.replaceAll('\\', '/');
        final libRelativePath = normalizedPath.contains('quwoquan_app/lib/')
            ? 'lib/${normalizedPath.split('quwoquan_app/lib/').last}'
            : normalizedPath.contains('/lib/')
            ? 'lib/${normalizedPath.split('/lib/').last}'
            : normalizedPath;
        if (allowedDirectDeckEntrypoints.contains(libRelativePath)) {
          continue;
        }
        if (entity.readAsStringSync().contains('ArticleReadOnlyBookDeck(')) {
          offenders.add(libRelativePath);
        }
      }

      expect(
        offenders,
        isEmpty,
        reason:
            '业务页面必须通过 ArticleReaderFlipHost + ArticleReaderHostAdapter 接入；'
            'diagnostics 入口才允许直连 deck 验证组件本体。',
      );
    },
  );

  test('article page curl effective flag has no host or deck constructor default', () {
    final appLib = Directory('lib').existsSync()
        ? Directory('lib')
        : Directory('quwoquan_app/lib');
    final hostAdapter = File(
      '${appLib.path}/service/content_service/content/post/presentation/article_reader/hosts/article_reader_host_adapter.dart',
    ).readAsStringSync();
    final deck = File(
      '${appLib.path}/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart',
    ).readAsStringSync();

    for (final source in <String>[hostAdapter, deck]) {
      expect(source, contains('required this.enablePageCurl'));
      expect(
        source,
        isNot(contains('this.enablePageCurl =')),
        reason: 'effective runtime flag 必须由调用方显式传入，不得在宿主或 deck 建第二默认值',
      );
    }
  });

  test('article reader page surface files remain below R03 threshold', () {
    final appLib = Directory('lib').existsSync()
        ? Directory('lib')
        : Directory('quwoquan_app/lib');
    for (final relative in const <String>[
      'service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces.dart',
      'service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces_blocks.dart',
      'service/content_service/content/post/presentation/article_reader/content/article_reader_page_surfaces_backdrops.dart',
    ]) {
      final file = File('${appLib.path}/$relative');
      expect(file.existsSync(), isTrue, reason: relative);
      expect(
        file.readAsLinesSync().length,
        lessThan(1000),
        reason: '$relative must stay below the R03 hard limit',
      );
    }
  });

  test('article reader deck library files remain below R03 threshold', () {
    final appLib = Directory('lib').existsSync()
        ? Directory('lib')
        : Directory('quwoquan_app/lib');
    final hostDir = Directory(
      '${appLib.path}/service/content_service/content/post/presentation/article_reader/pageflip/host',
    );
    final deckFiles =
        hostDir
            .listSync()
            .whereType<File>()
            .where(
              (file) =>
                  file.uri.pathSegments.last.startsWith(
                    'article_read_only_book_deck',
                  ) &&
                  file.path.endsWith('.dart'),
            )
            .toList(growable: false)
          ..sort((a, b) => a.path.compareTo(b.path));

    expect(deckFiles, isNotEmpty);
    for (final file in deckFiles) {
      expect(
        file.readAsLinesSync().length,
        lessThan(1000),
        reason: '${file.path} must stay below the R03 hard limit',
      );
    }
  });

  test('article reader deck does not expose deprecated hard page flipping', () {
    final appLib = Directory('lib').existsSync()
        ? Directory('lib')
        : Directory('quwoquan_app/lib');
    final hostDir = Directory(
      '${appLib.path}/service/content_service/content/post/presentation/article_reader/pageflip/host',
    );
    final hostSources = hostDir
        .listSync()
        .whereType<File>()
        .where(
          (file) =>
              file.uri.pathSegments.last.startsWith(
                'article_read_only_book_deck',
              ) &&
              file.path.endsWith('.dart'),
        )
        .map((file) => file.readAsStringSync())
        .join('\n');

    expect(
      hostSources,
      isNot(contains('_buildHardFlippingPageLayer')),
      reason: '文章阅读 deck 必须只走 soft/paperFold 主线，不能保留旧 3D 硬翻页入口。',
    );
    expect(
      hostSources,
      isNot(contains('rotateY(')),
      reason: '截图中的侧翻残影来自 rotateY 硬翻页路径，article reader deck 中应不可达。',
    );
    expect(
      hostSources,
      contains('hardPagePolicy: StPageFlipHardPagePolicy.none'),
      reason: 'coverUrl 只能决定扉页内容，不能再隐式启用 hard density。',
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
