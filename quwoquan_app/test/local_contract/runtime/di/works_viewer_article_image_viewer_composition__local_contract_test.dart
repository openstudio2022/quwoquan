// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t1
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t2
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t4

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/runtime/di/works_viewer_article_dependencies.dart';
import 'package:quwoquan_app/service/content_service/content/post/application/public/article_document_models.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';

ArticleDocumentData _documentWithMixedImageAvailability() {
  return ArticleDocumentData(
    nodes: const <ArticleDocumentNode>[
      ArticleDocumentNode(
        id: 'figure-1',
        type: ArticleDocumentNodeType.figure,
        assetId: 'asset-1',
        imageUrl: 'https://cdn.example.com/article/1.jpg',
      ),
      ArticleDocumentNode(
        id: 'figure-absent',
        type: ArticleDocumentNodeType.figure,
        assetId: 'asset-absent',
      ),
      ArticleDocumentNode(
        id: 'figure-3',
        type: ArticleDocumentNodeType.figure,
        assetId: 'asset-3',
        imageUrl: 'https://cdn.example.com/article/3.jpg',
      ),
    ],
  );
}

Future<void> _turnImageBook(WidgetTester tester, double deltaX) async {
  final gestureLayer = find.byKey(
    const ValueKey<String>('media-pageflip-gesture-layer'),
  );
  final rect = tester.getRect(gestureLayer);
  final gesture = await tester.startGesture(rect.center);
  await gesture.moveBy(Offset(deltaX / 2, 0));
  await tester.pump();
  await gesture.moveBy(Offset(deltaX / 2, 0));
  await tester.pump();
  await gesture.up();
  await tester.pump();
  for (var frame = 0; frame < 70; frame += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }
}

void main() {
  testWidgets('runtime/DI 复用 ImageBookCanvas，保留缺席页位并按 canonical ID 定位', (
    tester,
  ) async {
    late BuildContext hostContext;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) {
            hostContext = context;
            return const SizedBox.expand();
          },
        ),
      ),
    );
    final document = _documentWithMixedImageAvailability();
    final opened = <String>[];
    final closed = <String>[];
    final mediaLoads = <ImageBookMediaLoadEvent>[];

    final presentation = presentWorksArticleImageViewer(
      context: hostContext,
      document: document,
      initialAsset: document.assets.last,
      onOpened: (assetId) => opened.add(assetId),
      onClosed: (assetId) => closed.add(assetId),
      onMediaLoad: mediaLoads.add,
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(find.byKey(worksArticleImageViewerSurfaceKey), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('works-top-progress-label')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('works-format-tab-strip')),
      findsNothing,
    );
    final canvas = tester.widget<ImageBookCanvas>(find.byType(ImageBookCanvas));
    expect(
      canvas.deliveries
          .map((binding) => binding.publicUrl)
          .toList(growable: false),
      <String>[
        'https://cdn.example.com/article/1.jpg',
        '',
        'https://cdn.example.com/article/3.jpg',
      ],
    );
    expect(canvas.initialIndex, 2);
    expect(canvas.onMediaLoad, isNotNull);
    const mediaLoadEvent = ImageBookMediaLoadEvent(
      result: 'success',
      durationMs: 12,
      candidatesTried: 1,
    );
    mediaLoads.clear();
    canvas.onMediaLoad!(mediaLoadEvent);
    expect(mediaLoads.single, same(mediaLoadEvent));
    expect(opened, <String>['asset-3']);
    expect(closed, isEmpty);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-2')),
      findsOneWidget,
      reason: '浏览层必须从被点击的第三张图片开始，而不是重置到首图。',
    );

    await _turnImageBook(tester, 192);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
    await _turnImageBook(tester, 192);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-0')),
      findsOneWidget,
    );
    await _turnImageBook(tester, -192);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
      reason: '文章图片书必须能从首图左滑回到下一张，左右两个方向都可达。',
    );

    await tester.tap(find.byKey(worksArticleImageViewerCloseKey));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 300));

    expect(await presentation, isTrue);
    expect(find.byKey(worksArticleImageViewerSurfaceKey), findsNothing);
    expect(closed, <String>['asset-absent']);
  });

  testWidgets('clicked asset 不可浏览时明确返回 absent，不打开空 modal', (tester) async {
    late BuildContext hostContext;
    await tester.pumpWidget(
      CupertinoApp(
        home: Builder(
          builder: (context) {
            hostContext = context;
            return const SizedBox.expand();
          },
        ),
      ),
    );
    final document = ArticleDocumentData(
      nodes: const <ArticleDocumentNode>[
        ArticleDocumentNode(
          id: 'figure-absent',
          type: ArticleDocumentNodeType.figure,
          assetId: 'asset-absent',
        ),
      ],
    );
    final lifecycle = <String>[];

    final presented = await presentWorksArticleImageViewer(
      context: hostContext,
      document: document,
      initialAsset: document.assets.single,
      onOpened: lifecycle.add,
      onClosed: lifecycle.add,
    );

    expect(presented, isFalse);
    expect(find.byKey(worksArticleImageViewerSurfaceKey), findsNothing);
    expect(lifecycle, isEmpty);
  });
}
