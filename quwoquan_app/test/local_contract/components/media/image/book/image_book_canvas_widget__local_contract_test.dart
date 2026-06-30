import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/media/image/book/image_book_canvas.dart';
import 'package:quwoquan_app/components/media/image/book/image_book_page_surface.dart';
import 'package:quwoquan_app/components/media/shared/pageflip/media_page_flip_book.dart';

Widget _host(Widget child) => ProviderScope(
  child: CupertinoApp(home: CupertinoPageScaffold(child: child)),
);

void _consumeImageExceptions(WidgetTester tester) {
  while (tester.takeException() != null) {
    // Image loading is not the subject of this component boundary test.
  }
}

Future<ui.Image> _solidImage(int width, int height, Color color) async {
  final recorder = ui.PictureRecorder();
  final canvas = ui.Canvas(recorder);
  canvas.drawRect(
    Rect.fromLTWH(0, 0, width.toDouble(), height.toDouble()),
    ui.Paint()..color = color,
  );
  final picture = recorder.endRecording();
  final image = await picture.toImage(math.max(1, width), math.max(1, height));
  picture.dispose();
  return image;
}

Future<double> _averageLuminance(ui.Image image) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  final bytes = data!.buffer.asUint8List();
  var total = 0.0;
  var count = 0;
  for (var i = 0; i < bytes.length; i += 4) {
    final r = bytes[i].toDouble();
    final g = bytes[i + 1].toDouble();
    final b = bytes[i + 2].toDouble();
    total += 0.2126 * r + 0.7152 * g + 0.0722 * b;
    count += 1;
  }
  return total / count;
}

void main() {
  test('ImageBookPageSurfaceFactory 将不同尺寸与失败态统一为双面书页材质', () async {
    const factory = ImageBookPageSurfaceFactory();
    const pageSize = Size(320, 480);
    final wideImage = await _solidImage(640, 180, const Color(0xFFCC6633));
    final tallImage = await _solidImage(180, 640, const Color(0xFF3366CC));

    final widePair = await factory.rasterizeImageTexture(
      image: wideImage,
      pageSize: pageSize,
      pixelRatio: 1,
    );
    final tallPair = await factory.rasterizeImageTexture(
      image: tallImage,
      pageSize: pageSize,
      pixelRatio: 1,
    );
    final loadingPair = await factory.buildLoadingTexture(
      pageSize: pageSize,
      pixelRatio: 1,
    );
    final failurePair = await factory.buildFailureTexture(
      pageSize: pageSize,
      pixelRatio: 1,
    );

    for (final pair in <MediaPageFlipTexturePair>[
      widePair,
      tallPair,
      loadingPair,
      failurePair,
    ]) {
      for (final snapshot in <MediaPageFlipTextureSnapshot>[
        pair.front,
        pair.back,
      ]) {
        expect(snapshot.logicalSize, pageSize);
        expect(snapshot.image.width, pageSize.width);
        expect(snapshot.image.height, pageSize.height);
      }
    }
    expect(widePair.front.semanticSurfaceKind, 'image_book.success.front');
    expect(widePair.back.semanticSurfaceKind, 'image_book.success.back');
    expect(tallPair.front.semanticSurfaceKind, 'image_book.success.front');
    expect(tallPair.back.semanticSurfaceKind, 'image_book.success.back');
    expect(loadingPair.front.semanticSurfaceKind, 'image_book.loading.front');
    expect(loadingPair.back.semanticSurfaceKind, 'image_book.loading.back');
    expect(failurePair.front.semanticSurfaceKind, 'image_book.failure.front');
    expect(failurePair.back.semanticSurfaceKind, 'image_book.failure.back');
    final wideFrontLuminance = await _averageLuminance(widePair.front.image);
    final wideBackLuminance = await _averageLuminance(widePair.back.image);
    expect(
      wideBackLuminance,
      lessThan(wideFrontLuminance),
      reason: '图片书背面必须比正面略淡，不能用正面高光纹理冒充。',
    );
    expect(
      wideBackLuminance,
      greaterThan(wideFrontLuminance * 0.72),
      reason: '深色图片背面只应轻微变淡，不能被 wash/动态阴影压成黑片。',
    );
    expect(
      await _averageLuminance(failurePair.back.image),
      greaterThan(4),
      reason: '失败页背面必须是可识别失败纹理，不允许纯黑。',
    );

    widePair.dispose();
    tallPair.dispose();
    loadingPair.dispose();
    failurePair.dispose();
    wideImage.dispose();
    tallImage.dispose();
  });

  testWidgets('ImageBookCanvas 接入公共翻书宿主并上报初始页', (tester) async {
    final changed = <int>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            imageUrls: const <String>[
              'media/image/s/fixture/book-1.jpg',
              'media/image/s/fixture/book-2.jpg',
            ],
            onImageChanged: changed.add,
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageExceptions(tester);
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageExceptions(tester);

    expect(changed, <int>[0]);
    expect(
      find.byKey(const ValueKey<String>('works-photo-book-stage')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-gesture-layer')),
      findsOneWidget,
    );
    expect(
      tester
          .widget<MediaPageFlipBook>(find.byType(MediaPageFlipBook))
          .textureSnapshotBuilder,
      isNotNull,
      reason: '图片书必须走 URL 直接纹理，不能退回隐藏截图导致 held curl 黑屏。',
    );
    final mediaBook = tester.widget<MediaPageFlipBook>(
      find.byType(MediaPageFlipBook),
    );
    final pair = await mediaBook.textureSnapshotBuilder!(
      tester.element(find.byType(MediaPageFlipBook)),
      0,
      const Size(320, 480),
      1,
    );
    if (pair == null) {
      return;
    }
    addTearDown(pair.dispose);
    expect(pair.front.logicalSize, const Size(320, 480));
    expect(pair.back.logicalSize, const Size(320, 480));
    expect(
      pair.front.semanticSurfaceKind,
      isNot('image_book.loading.front'),
      reason: '图片尚未解码时不得把 loading 模糊面提升为 held curl 材质。',
    );
    expect(
      pair.back.semanticSurfaceKind,
      isNot('image_book.loading.back'),
      reason: '图片尚未解码时不得把 loading 背面提升为 held curl 材质。',
    );
    expect(<String>{
      'image_book.success.front',
      'image_book.failure.front',
    }, contains(pair.front.semanticSurfaceKind));
    expect(<String>{
      'image_book.success.back',
      'image_book.failure.back',
    }, contains(pair.back.semanticSurfaceKind));
  });

  testWidgets('ImageBookCanvas 左滑后同步当前图片页码', (tester) async {
    final changed = <int>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            imageUrls: const <String>[
              'media/image/s/fixture/book-1.jpg',
              'media/image/s/fixture/book-2.jpg',
            ],
            onImageChanged: changed.add,
          ),
        ),
      ),
    );
    await tester.pump();
    _consumeImageExceptions(tester);
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageExceptions(tester);

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(const Offset(-96, 0));
    await tester.pump();
    _consumeImageExceptions(tester);
    await gesture.moveBy(const Offset(-96, 0));
    await tester.pump();
    _consumeImageExceptions(tester);
    await gesture.up();
    await tester.pump();
    _consumeImageExceptions(tester);
    for (var i = 0; i < 70; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
      _consumeImageExceptions(tester);
    }
    _consumeImageExceptions(tester);

    expect(changed, <int>[0, 1]);
    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
  });
}
