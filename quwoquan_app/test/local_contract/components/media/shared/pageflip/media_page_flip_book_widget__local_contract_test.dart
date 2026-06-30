import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';
import 'package:quwoquan_app/components/pageflip/page_surface_snapshot.dart';

Widget _host(Widget child) =>
    CupertinoApp(home: CupertinoPageScaffold(child: child));

class _ReadyMediaBookHarness extends StatefulWidget {
  const _ReadyMediaBookHarness({super.key, required this.pageCount});

  final int pageCount;

  @override
  State<_ReadyMediaBookHarness> createState() => _ReadyMediaBookHarnessState();
}

class _ReadyMediaBookHarnessState extends State<_ReadyMediaBookHarness> {
  final Set<int> readyPages = <int>{};

  void markReady(Iterable<int> indices) {
    setState(() {
      readyPages.addAll(indices);
    });
  }

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      width: 320,
      height: 480,
      child: MediaPageFlipBook(
        pageCount: widget.pageCount,
        textureReadinessSignature: Object.hashAll(readyPages),
        isPageTextureReady: readyPages.contains,
        pageBuilder: (context, index) => ColoredBox(
          key: ValueKey<String>('media-ready-page-$index'),
          color: index.isEven
              ? const Color(0xFF3366CC)
              : const Color(0xFFCC6633),
        ),
      ),
    );
  }
}

Future<ArticlePageTextureSnapshot> _solidTextureSnapshot({
  required int pageIndex,
  required MediaPageFlipSurfaceFace face,
  required Size pageSize,
  required double pixelRatio,
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = Canvas(recorder);
  canvas.scale(pixelRatio, pixelRatio);
  final baseColor = pageIndex.isEven
      ? const Color(0xFF2E5FAA)
      : const Color(0xFFAA6B2E);
  final color = face == MediaPageFlipSurfaceFace.front
      ? baseColor
      : Color.alphaBlend(const Color(0x99000000), baseColor);
  canvas.drawRect(Offset.zero & pageSize, Paint()..color = color);
  canvas.drawCircle(
    Offset(pageSize.width * 0.5, pageSize.height * 0.5),
    math.min(pageSize.width, pageSize.height) * 0.22,
    Paint()
      ..color = face == MediaPageFlipSurfaceFace.front
          ? const Color(0x55FFFFFF)
          : const Color(0x2EFFFFFF),
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(
    math.max(1, (pageSize.width * pixelRatio).round()),
    math.max(1, (pageSize.height * pixelRatio).round()),
  );
  picture.dispose();
  return createMediaPageFlipTextureSnapshot(
    image: image,
    logicalSize: pageSize,
    pixelRatio: pixelRatio,
    semanticSurfaceKind: 'test.media_page.$pageIndex.${face.name}',
  );
}

Future<MediaPageFlipTexturePair?> _solidTextureBuilder(
  BuildContext context,
  int pageIndex,
  Size pageSize,
  double pixelRatio,
) async {
  return MediaPageFlipTexturePair(
    front: await _solidTextureSnapshot(
      pageIndex: pageIndex,
      face: MediaPageFlipSurfaceFace.front,
      pageSize: pageSize,
      pixelRatio: pixelRatio,
    ),
    back: await _solidTextureSnapshot(
      pageIndex: pageIndex,
      face: MediaPageFlipSurfaceFace.back,
      pageSize: pageSize,
      pixelRatio: pixelRatio,
    ),
  );
}

double _rotationZForTransform(WidgetTester tester, Key key) {
  final transform = tester.widget<Transform>(find.byKey(key));
  final matrix = transform.transform;
  return math.atan2(matrix.entry(1, 0), matrix.entry(0, 0));
}

void main() {
  testWidgets('MediaPageFlipBook 首帧只展示静态页，不在 idle 状态启动 curl/capture', (
    tester,
  ) async {
    final changedPages = <int>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 3,
            onPageChanged: changedPages.add,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-page-$index'),
              color: Color(0xFF111111 + index),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    expect(changedPages, <int>[0]);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-gesture-layer')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-0')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsNothing,
    );
  });

  testWidgets('MediaPageFlipBook 支持全屏左滑翻到下一页', (tester) async {
    final changedPages = <int>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 3,
            onPageChanged: changedPages.add,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-page-$index'),
              color: Color(0xFF111111 + index),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    expect(changedPages, <int>[0]);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-0')),
      findsOneWidget,
    );

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-96, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(-96, 0));
    await tester.pump();
    await gesture.up();
    await tester.pump();
    await tester.pumpAndSettle();

    expect(changedPages, <int>[0, 1]);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
  });

  testWidgets('MediaPageFlipBook 支持全屏右滑回到上一页', (tester) async {
    final changedPages = <int>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 3,
            initialPage: 1,
            onPageChanged: changedPages.add,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-page-$index'),
              color: Color(0xFF222222 + index),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    expect(changedPages, <int>[1]);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(96, 0));
    await tester.pump();
    await gesture.moveBy(const Offset(96, 0));
    await tester.pump();
    await gesture.up();
    await tester.pump();
    await tester.pumpAndSettle();

    expect(changedPages, <int>[1, 0]);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-0')),
      findsOneWidget,
    );
  });

  testWidgets('MediaPageFlipBook 等待纹理 ready 后才进入动态翻页，避免捕获黑色占位页', (
    tester,
  ) async {
    final harnessKey = GlobalKey<_ReadyMediaBookHarnessState>();

    await tester.pumpWidget(
      _host(_ReadyMediaBookHarness(key: harnessKey, pageCount: 2)),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-120, 0));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsNothing,
      reason:
          'dynamic paper layers must not paint from placeholder snapshots before the image page is ready.',
    );

    harnessKey.currentState!.markReady(<int>{0, 1});
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason:
          'once real page textures are ready, the same held gesture should promote into dynamic paper layers.',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 右滑后翻持有态进入同源动态翻页层', (tester) async {
    final readyPages = <int>{0, 1, 2};

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 3,
            initialPage: 1,
            textureReadinessSignature: Object.hashAll(readyPages),
            isPageTextureReady: readyPages.contains,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-back-page-$index'),
              color: Color(0xFF442200 + index * 0x001122),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(72, 0));
    for (var i = 0; i < 6; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason:
          'image BACK must inherit the shared pageflip dynamic path while held.',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 支持直接纹理快照，图片书按住左滑即可进入动态翻页', (tester) async {
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 2,
            textureSnapshotBuilder: _solidTextureBuilder,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-direct-texture-page-$index'),
              color: index.isEven
                  ? const Color(0xFF2E5FAA)
                  : const Color(0xFFAA6B2E),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-140, 0));
    for (var i = 0; i < 6; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason:
          'image book must render a held page curl from direct URL textures, not wait for release-only page changes.',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 前翻绑定 current.front、next.back、next.front', (
    tester,
  ) async {
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 3,
            textureSnapshotBuilder: _solidTextureBuilder,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-forward-face-page-$index'),
              color: index.isEven
                  ? const Color(0xFF2E5FAA)
                  : const Color(0xFFAA6B2E),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-140, 0));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-0')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-bottom-layer')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-surface-1-front')),
      findsOneWidget,
      reason: '前翻底页必须是下一页正面。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-surface-1-back')),
      findsOneWidget,
      reason: '前翻翻动纸张背面必须是下一页背面。',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 后翻绑定 prev.front、prev.back、current.front', (
    tester,
  ) async {
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 3,
            initialPage: 1,
            textureSnapshotBuilder: _solidTextureBuilder,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-direct-three-face-page-$index'),
              color: index.isEven
                  ? const Color(0xFF2E5FAA)
                  : const Color(0xFFAA6B2E),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(72, 0));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-backward-front-layer')),
      findsOneWidget,
      reason: '后翻必须先把上一页正面作为同源动态层的一面。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-bottom-layer')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-surface-0-front')),
      findsOneWidget,
      reason: '后翻上一页正面必须进入可见层。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-surface-0-back')),
      findsOneWidget,
      reason: '后翻翻动纸张背面必须是上一页背面。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-surface-1-front')),
      findsOneWidget,
      reason: '后翻底层仍需保留当前页正面。',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 斜向拖拽使用 renderFrame angle 驱动翻页层旋转', (
    tester,
  ) async {
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: MediaPageFlipBook(
            pageCount: 2,
            textureSnapshotBuilder: _solidTextureBuilder,
            pageBuilder: (context, index) => ColoredBox(
              key: ValueKey<String>('media-angled-page-$index'),
              color: index.isEven
                  ? const Color(0xFF2E5FAA)
                  : const Color(0xFFAA6B2E),
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-140, -96));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-transform')),
      findsOneWidget,
    );
    expect(
      _rotationZForTransform(
        tester,
        const ValueKey<String>('media-pageflip-flipping-transform'),
      ).abs(),
      greaterThan(0.01),
      reason: '斜向拖拽必须反映到真实动态层旋转，不能退化成竖直滑条。',
    );

    await gesture.up();
    await tester.pump();
  });
}
