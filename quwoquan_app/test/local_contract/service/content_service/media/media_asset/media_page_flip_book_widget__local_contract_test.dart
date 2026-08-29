import 'dart:io';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/design_system/gestures/immersive_gesture_intent_controller.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_page_flip_book.dart';
import 'package:quwoquan_app/design_system/pageflip/page_surface_snapshot.dart';

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

Future<double> _nearBlackPixelRatio(ui.Image image) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  final bytes = data!.buffer.asUint8List();
  var nearBlackPixels = 0;
  var pixelCount = 0;
  for (var offset = 0; offset < bytes.length; offset += 4) {
    if (bytes[offset] <= 2 &&
        bytes[offset + 1] <= 2 &&
        bytes[offset + 2] <= 2) {
      nearBlackPixels += 1;
    }
    pixelCount += 1;
  }
  return nearBlackPixels / pixelCount;
}

void main() {
  test('图片书与文章宿主只消费父级 gesture intent 坐标源', () {
    final mediaSource = File(
      'lib/service/content_service/media/media_asset/presentation/media_page_flip_book.dart',
    ).readAsStringSync();
    final articleSource = File(
      'lib/service/content_service/content/post/presentation/article_reader/pageflip/host/article_read_only_book_deck.dart',
    ).readAsStringSync();

    expect(mediaSource, isNot(contains('update(position:')));
    expect(mediaSource, isNot(contains('_syncExternalGestureIntent')));
    expect(articleSource, isNot(contains('update(position:')));
    expect(articleSource, isNot(contains('_syncExternalGestureIntent')));
  });

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
      reason: 'idle 首帧没有 moving sheet，必须只展示当前静态页。',
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
      reason: 'dynamic paper layers must not paint from placeholder snapshots before the image page is ready.',
    );

    harnessKey.currentState!.markReady(<int>{0, 1});
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: 'once real page textures are ready, the same held gesture should promote into dynamic paper layers.',
    );

    await gesture.up();
    await tester.pump(const Duration(milliseconds: 80));
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: 'release 后 80ms 内仍应可见动态翻页层，避免高速松手闪缩。',
    );
    await tester.pumpAndSettle();
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
      reason: 'image BACK must inherit the shared pageflip dynamic path while held.',
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
      reason: 'image book must render a held page curl from direct URL textures, not wait for release-only page changes.',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 直接纹理路径不被 ready 门禁或加载回调打断跟手', (tester) async {
    var readinessSignature = 0;
    StateSetter? setHarnessState;

    await tester.pumpWidget(
      _host(
        StatefulBuilder(
          builder: (context, setState) {
            setHarnessState = setState;
            return SizedBox(
              width: 320,
              height: 480,
              child: MediaPageFlipBook(
                pageCount: 2,
                textureReadinessSignature: readinessSignature,
                isPageTextureReady: (_) => false,
                textureSnapshotBuilder: _solidTextureBuilder,
                pageBuilder: (context, index) => ColoredBox(
                  key: ValueKey<String>('media-direct-ready-gate-page-$index'),
                  color: index.isEven
                      ? const Color(0xFF2E5FAA)
                      : const Color(0xFFAA6B2E),
                ),
              ),
            );
          },
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
    await gesture.moveBy(const Offset(-12, 0));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: '直接 URL/page surface 材质已经有成功/失败兜底，不能再被外部 ready=false 阻塞。',
    );

    setHarnessState!(() {
      readinessSignature += 1;
    });
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: '图片加载回调刷新 signature 时，不得清空正在跟手翻页的动态材质。',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 两张图在中心小幅前翻/后翻都立即跟手', (tester) async {
    Future<void> pumpBook({
      required int initialPage,
      required ImmersiveGestureIntentController intentController,
    }) async {
      await tester.pumpWidget(
        _host(
          SizedBox(
            width: 320,
            height: 480,
            child: MediaPageFlipBook(
              pageCount: 2,
              initialPage: initialPage,
              textureSnapshotBuilder: _solidTextureBuilder,
              gestureIntentController: intentController,
              pageBuilder: (context, index) => ColoredBox(
                key: ValueKey<String>('media-two-page-center-$index'),
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
    }

    final forwardIntent = ImmersiveGestureIntentController();
    await pumpBook(initialPage: 0, intentController: forwardIntent);
    final forwardLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final forwardRect = tester.getRect(forwardLayer);
    final forwardGesture = await tester.startGesture(forwardRect.center);
    await forwardGesture.moveBy(const Offset(-10, 0));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: '两张图第一页从中心左滑时，preview 阶段也要立即出现前翻跟手层。',
    );
    await forwardGesture.up();
    await tester.pumpAndSettle();

    final backIntent = ImmersiveGestureIntentController();
    await pumpBook(initialPage: 1, intentController: backIntent);
    final backLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final backRect = tester.getRect(backLayer);
    final backGesture = await tester.startGesture(backRect.center);
    await backGesture.moveBy(const Offset(10, 0));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: '两张图第二页从中心右滑时，preview 阶段也要立即出现后翻跟手层。',
    );
    await backGesture.up();
    await tester.pumpAndSettle();
  });

  testWidgets('MediaPageFlipBook 前翻绑定 current.front、current.back、next.front', (
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
      reason: '前翻必须沿用文章基线，让当前静态正面在 moving sheet 下连续离场。',
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
      find.descendant(
        of: find.byKey(const ValueKey<String>('media-pageflip-bottom-layer')),
        matching: find.byKey(
          const ValueKey<String>('media-pageflip-surface-1-front'),
        ),
      ),
      findsOneWidget,
      reason: '下一页正面必须停留在底页，不应替换 moving sheet。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-moving-face-0-back')),
      findsOneWidget,
      reason: '前翻 moving sheet 只能使用当前页背面。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-surface-1-back')),
      findsNothing,
      reason: '下一页背面不得贴到当前页 moving sheet。',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook moving sheet 只有一个完整 RawImage 材质面', (
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
    final gesture = await tester.startGesture(
      tester.getRect(gestureLayer).center,
    );
    await gesture.moveBy(const Offset(-140, 0));
    for (var i = 0; i < 8; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }

    final movingSheet = find.byKey(
      const ValueKey<String>('media-pageflip-flipping-layer'),
    );
    expect(
      find.descendant(of: movingSheet, matching: find.byType(RawImage)),
      findsOneWidget,
      reason: 'moving sheet 只能绘制一张完整页面材质。',
    );
    expect(
      find.descendant(
        of: movingSheet,
        matching: find.byType(FractionallySizedBox),
      ),
      findsNothing,
      reason: 'moving sheet 不得用两个 FractionallySizedBox 重叠压缩完整纹理。',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 后翻三面绑定不创建独立 previous.front 平面', (
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
      find.byKey(
        const ValueKey<String>(
          'media-pageflip-backward-previous-front-replacement',
        ),
      ),
      findsNothing,
      reason: 'Route-B 后翻只能保留一张 moving sheet，不得额外复制 previous.front 平面。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-bottom-layer')),
      findsOneWidget,
      reason: '后翻必须保留文章基线中的 current bottom clip。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
    );
    final movingSheet = find.byKey(
      const ValueKey<String>('media-pageflip-flipping-layer'),
    );
    expect(
      find.descendant(of: movingSheet, matching: find.byType(RawImage)),
      findsOneWidget,
      reason: '后翻 moving sheet 每帧只能选择上一页正面或背面之一。',
    );
    expect(
      find.descendant(
        of: movingSheet,
        matching: find.byKey(
          const ValueKey<String>('media-pageflip-surface-1-front'),
        ),
      ),
      findsNothing,
      reason: '当前页正面只能属于静态页和 bottom，不得贴到上一页 moving sheet。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
      reason: '后翻 L0 必须是唯一的 current 静态 underlay。',
    );

    await gesture.up();
    await tester.pump();
  });

  testWidgets('MediaPageFlipBook 前后翻动态帧整页材质无黑色漏绘区域', (tester) async {
    const captureKey = ValueKey<String>('media-pageflip-pixel-capture');
    for (final scenario in <({int initialPage, Offset delta, String label})>[
      (initialPage: 0, delta: const Offset(-128, -26), label: 'FORWARD'),
      (initialPage: 1, delta: const Offset(128, -26), label: 'BACK'),
    ]) {
      await tester.pumpWidget(
        _host(
          SizedBox(
            width: 320,
            height: 480,
            child: RepaintBoundary(
              key: captureKey,
              child: MediaPageFlipBook(
                pageCount: 2,
                initialPage: scenario.initialPage,
                textureSnapshotBuilder: _solidTextureBuilder,
                pageBuilder: (context, index) => ColoredBox(
                  color: index.isEven
                      ? const Color(0xFF2E5FAA)
                      : const Color(0xFFAA6B2E),
                ),
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
      final gesture = await tester.startGesture(
        tester.getRect(gestureLayer).center,
      );
      await gesture.moveBy(scenario.delta);
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }

      final boundary = tester.renderObject<RenderRepaintBoundary>(
        find.byKey(captureKey),
      );
      final frame = await tester.runAsync<ui.Image>(
        () => boundary.toImage(pixelRatio: 1),
      );
      if (frame == null) {
        fail(
          'failed to capture MediaPageFlipBook ${scenario.label} framebuffer',
        );
      }
      final nearBlackRatio = await tester.runAsync<double>(
        () => _nearBlackPixelRatio(frame),
      );
      frame.dispose();
      expect(nearBlackRatio, isNotNull);
      expect(
        nearBlackRatio!,
        lessThanOrEqualTo(0.001),
        reason: '非黑测试材质的 ${scenario.label} 动态合成不应暴露舞台底色或背面漏绘黑区。',
      );

      await gesture.cancel();
      await tester.pump();
    }
  });

  testWidgets('MediaPageFlipBook 减弱动态时只更新页态不启动 curl layer', (tester) async {
    final motionEvents = <MediaPageFlipMotionEvent>[];
    final changedPages = <int>[];

    await tester.pumpWidget(
      _host(
        MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: SizedBox(
            width: 320,
            height: 480,
            child: MediaPageFlipBook(
              pageCount: 2,
              textureSnapshotBuilder: _solidTextureBuilder,
              onPageChanged: changedPages.add,
              onMotionEvent: motionEvents.add,
              pageBuilder: (context, index) => ColoredBox(
                key: ValueKey<String>('media-reduced-motion-page-$index'),
                color: index.isEven
                    ? const Color(0xFF2E5FAA)
                    : const Color(0xFFAA6B2E),
              ),
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
    await gesture.moveBy(const Offset(-72, 0));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsNothing,
      reason: '系统 Reduce Motion 开启时图片书不得启动 3D curl 动态层。',
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
      reason: 'Reduce Motion 下仍要完成轻量页态更新。',
    );

    await gesture.up();
    await tester.pump();

    expect(changedPages, contains(1));
    expect(motionEvents, isNotEmpty);
    expect(motionEvents.last.reducedMotion, isTrue);
    expect(motionEvents.last.motionProfile, 'reduced_motion');
    expect(motionEvents.last.committed, isTrue);
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
