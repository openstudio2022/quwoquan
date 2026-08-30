// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-017.t4
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019.t1
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019.t2
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019.t3
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019.t4
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-019.t5
import 'dart:async';
import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/image_book_page_surface.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/media_page_flip_book.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_media_failure_content.dart';
import 'package:quwoquan_app/service/content_service/media/original_access_quota/presentation/media_delivery_image.dart'
    show MediaDeliveryBinding;
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/spacing/immersive_media_wait_motion.dart';

Widget _host(Widget child) => ProviderScope(
  child: CupertinoApp(home: CupertinoPageScaffold(child: child)),
);

/// 公开交付页序：本文件的主题是解码/等待/翻页编排，交付形态固定为公开。
/// 私有交付分流由 image_book_signed_delivery 锚点覆盖。
List<MediaDeliveryBinding> _publicPages(List<String> urls) => urls
    .map(
      (url) => MediaDeliveryBinding(
        assetId: '',
        accessMode: null,
        publicUrl: url,
      ),
    )
    .toList(growable: false);

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

Future<ui.Image> _quadrantImage({
  required int width,
  required int height,
  required Color topLeft,
  required Color topRight,
  required Color bottomLeft,
  required Color bottomRight,
}) async {
  final recorder = ui.PictureRecorder();
  final canvas = ui.Canvas(recorder);
  final halfWidth = width / 2;
  final halfHeight = height / 2;
  canvas
    ..drawRect(
      Rect.fromLTWH(0, 0, halfWidth, halfHeight),
      ui.Paint()..color = topLeft,
    )
    ..drawRect(
      Rect.fromLTWH(halfWidth, 0, halfWidth, halfHeight),
      ui.Paint()..color = topRight,
    )
    ..drawRect(
      Rect.fromLTWH(0, halfHeight, halfWidth, halfHeight),
      ui.Paint()..color = bottomLeft,
    )
    ..drawRect(
      Rect.fromLTWH(halfWidth, halfHeight, halfWidth, halfHeight),
      ui.Paint()..color = bottomRight,
    );
  final picture = recorder.endRecording();
  final image = await picture.toImage(math.max(1, width), math.max(1, height));
  picture.dispose();
  return image;
}

Future<double> _sampleLuminance(
  ui.Image image, {
  required int x,
  required int y,
}) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  final bytes = data!.buffer.asUint8List();
  final sampleX = x.clamp(0, image.width - 1).toInt();
  final sampleY = y.clamp(0, image.height - 1).toInt();
  final offset = (sampleY * image.width + sampleX) * 4;
  final r = bytes[offset].toDouble();
  final g = bytes[offset + 1].toDouble();
  final b = bytes[offset + 2].toDouble();
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
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

Future<double> _averageSaturation(ui.Image image) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  final bytes = data!.buffer.asUint8List();
  var total = 0.0;
  var count = 0;
  for (var i = 0; i < bytes.length; i += 4) {
    final r = bytes[i].toDouble();
    final g = bytes[i + 1].toDouble();
    final b = bytes[i + 2].toDouble();
    final maxChannel = math.max(r, math.max(g, b));
    final minChannel = math.min(r, math.min(g, b));
    if (maxChannel > 0) {
      total += (maxChannel - minChannel) / maxChannel;
    }
    count += 1;
  }
  return total / count;
}

class _ControlledImageLoadOperation implements ImageBookImageLoadOperation {
  _ControlledImageLoadOperation()
    : _completer = Completer<ImageBookImageLoadResult>();

  final Completer<ImageBookImageLoadResult> _completer;
  int _candidatesTried = 1;
  bool cancelled = false;

  @override
  Future<ImageBookImageLoadResult> get result => _completer.future;

  @override
  int get candidatesTried => _candidatesTried;

  void complete(ui.Image image, {int candidatesTried = 1}) {
    _candidatesTried = candidatesTried;
    _completer.complete(
      ImageBookImageLoadResult(image: image, candidatesTried: candidatesTried),
    );
  }

  void completeError(Object error, {int candidatesTried = 1}) {
    _candidatesTried = candidatesTried;
    _completer.completeError(error);
  }

  @override
  void cancel() {
    cancelled = true;
    if (!_completer.isCompleted) {
      _completer.completeError(const _ControlledImageLoadCancelled());
    }
  }
}

class _ControlledImageLoadCancelled implements Exception {
  const _ControlledImageLoadCancelled();
}

class _ControlledImageLoader {
  final Map<int, List<_ControlledImageLoadOperation>> attempts =
      <int, List<_ControlledImageLoadOperation>>{};
  final Map<int, List<List<String>>> candidateAttempts =
      <int, List<List<String>>>{};

  ImageBookImageLoadOperation call({
    required BuildContext context,
    required int pageIndex,
    required List<String> candidates,
    required Size pageSize,
  }) {
    final operation = _ControlledImageLoadOperation();
    attempts
        .putIfAbsent(pageIndex, () => <_ControlledImageLoadOperation>[])
        .add(operation);
    candidateAttempts
        .putIfAbsent(pageIndex, () => <List<String>>[])
        .add(List<String>.unmodifiable(candidates));
    return operation;
  }

  _ControlledImageLoadOperation latest(int pageIndex) =>
      attempts[pageIndex]!.last;
}

void main() {
  test('ImageBookPageSurfaceFactory 将不同尺寸 ready 图片统一为双面书页材质', () async {
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
    final neutralPair = await factory.buildNeutralTexture(
      pageSize: pageSize,
      pixelRatio: 1,
    );

    for (final pair in <MediaPageFlipTexturePair>[
      widePair,
      tallPair,
      neutralPair,
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
    expect(neutralPair.front.semanticSurfaceKind, 'image_book.neutral.front');
    expect(neutralPair.back.semanticSurfaceKind, 'image_book.neutral.back');
    expect(
      await _averageLuminance(neutralPair.back.image),
      greaterThan(4),
      reason: 'pending/failed 的中性背面必须完整可见，不能形成黑色缺口。',
    );
    final wideFrontLuminance = await _averageLuminance(widePair.front.image);
    final wideBackLuminance = await _averageLuminance(widePair.back.image);
    expect(
      wideBackLuminance,
      lessThan(wideFrontLuminance),
      reason: '图片书背面必须比正面略淡，不能用正面高光纹理冒充。',
    );
    final backBrightnessRatio = wideBackLuminance / wideFrontLuminance;
    expect(
      backBrightnessRatio,
      greaterThanOrEqualTo(0.62),
      reason: '背面 wash 不能把图片压成黑片。',
    );
    expect(
      backBrightnessRatio,
      lessThanOrEqualTo(0.78),
      reason: '背面必须降低亮度刺激，不能保留高对比镜像图。',
    );
    expect(
      await _averageSaturation(widePair.back.image),
      lessThan(await _averageSaturation(widePair.front.image) * 0.72),
      reason: '图片书背面必须降低饱和度，降低连续翻页刺激。',
    );
    widePair.dispose();
    tallPair.dispose();
    neutralPair.dispose();
    wideImage.dispose();
    tallImage.dispose();
  });

  test('ImageBookPageSurfaceFactory 翻页材质不烘焙底部黑角 chrome', () async {
    const factory = ImageBookPageSurfaceFactory();
    const pageSize = Size(120, 180);
    final quadrantImage = await _quadrantImage(
      width: 120,
      height: 180,
      topLeft: const Color(0xFFE7DCCF),
      topRight: const Color(0xFFC6D7EA),
      bottomLeft: const Color(0xFF8FC98F),
      bottomRight: const Color(0xFFD7C29B),
    );

    final pair = await factory.rasterizeImageTexture(
      image: quadrantImage,
      pageSize: pageSize,
      pixelRatio: 1,
    );

    final frontTopRight = await _sampleLuminance(
      pair.front.image,
      x: pair.front.image.width - 4,
      y: 4,
    );
    final frontBottomRight = await _sampleLuminance(
      pair.front.image,
      x: pair.front.image.width - 4,
      y: pair.front.image.height - 4,
    );
    final backBottomRight = await _sampleLuminance(
      pair.back.image,
      x: pair.back.image.width - 4,
      y: pair.back.image.height - 4,
    );

    expect(
      frontBottomRight,
      greaterThan(frontTopRight * 0.58),
      reason: '翻页 front texture 不得再带静态底部黑渐变，否则右下角会先被压暗。',
    );
    expect(
      backBottomRight,
      greaterThan(45),
      reason: '镜像后的背面右下角必须保留图片语义纹理，不允许被 chrome/wash 压成黑角。',
    );

    pair.dispose();
    quadrantImage.dispose();
  });

  testWidgets('ImageBookCanvas 保留缺席图片页位并呈现独立不可重试状态', (tester) async {
    final loader = _ControlledImageLoader();
    final mediaEvents = <ImageBookMediaLoadEvent>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/book-1.jpg',
              'asset://unresolved-article-image',
              'media/image/s/fixture/v1/book-3.jpg',
            ]),
            initialIndex: 1,
            imageLoader: loader.call,
            onMediaLoad: mediaEvents.add,
            onImageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));

    final book = tester.widget<MediaPageFlipBook>(
      find.byType(MediaPageFlipBook),
    );
    expect(book.pageCount, 3);
    expect(
      loader.attempts.containsKey(1),
      isFalse,
      reason: 'Unresolved asset identities must not enter the network loader.',
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-status-absent')),
      findsOneWidget,
    );
    expect(find.text(ContentText.imageLoadFailed), findsOneWidget);
    expect(
      find.byKey(const ValueKey<String>('image-book-retry')),
      findsNothing,
    );
    expect(mediaEvents.map((event) => event.result), <String>['absent']);

    await tester.pumpWidget(_host(const SizedBox()));
  });

  testWidgets('ImageBookCanvas 接入公共翻书宿主并上报初始页', (tester) async {
    final changed = <int>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/book-1.jpg',
              'media/image/s/fixture/v1/book-2.jpg',
            ]),
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
      'image_book.neutral.front',
    }, contains(pair.front.semanticSurfaceKind));
    expect(<String>{
      'image_book.success.back',
      'image_book.neutral.back',
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
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/book-1.jpg',
              'media/image/s/fixture/v1/book-2.jpg',
            ]),
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

  testWidgets('ImageBookCanvas 第一页中心左滑立即进入公共翻书跟手层', (tester) async {
    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/book-1.jpg',
              'media/image/s/fixture/v1/book-2.jpg',
            ]),
            onImageChanged: (_) {},
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
    await gesture.moveBy(const Offset(-12, 0));
    await tester.pump(const Duration(milliseconds: 16));
    _consumeImageExceptions(tester);

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
      reason: '图片书第一页从画面中心左滑应与文章一样立即跟手前翻，不能等待 release。',
    );

    await gesture.up();
    await tester.pump();
    _consumeImageExceptions(tester);
  });

  testWidgets('ImageBookCanvas pending 翻到中性纸面，拖动中 ready 落平后才淡入', (
    tester,
  ) async {
    final loader = _ControlledImageLoader();
    final targetImage = await _solidImage(240, 360, const Color(0xFF38A169));

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/pending-0.jpg',
              'media/image/s/fixture/v1/pending-1.jpg',
            ]),
            imageLoader: loader.call,
            onImageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));
    expect(loader.attempts.keys, containsAll(<int>[0, 1]));

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final gesture = await tester.startGesture(
      tester.getRect(gestureLayer).center,
    );
    await gesture.moveBy(const Offset(-120, 0));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-flipping-layer')),
      findsOneWidget,
    );
    final bottomLayer = find.byKey(
      const ValueKey<String>('media-pageflip-bottom-layer'),
    );
    final frozenBottomImage = tester
        .widget<RawImage>(
          find.descendant(of: bottomLayer, matching: find.byType(RawImage)),
        )
        .image;
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsNothing,
    );

    loader.latest(1).complete(targetImage);
    for (var i = 0; i < 6; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expect(
      tester
          .widget<RawImage>(
            find.descendant(of: bottomLayer, matching: find.byType(RawImage)),
          )
          .image,
      same(frozenBottomImage),
      reason: '事务中的 ready 只能排队，不能替换正在翻动的中性 bottom 材质。',
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsNothing,
    );

    await gesture.moveBy(const Offset(-120, 0));
    await gesture.up();
    for (var i = 0; i < 60; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
      if (find
              .byKey(const ValueKey<String>('media-pageflip-static-page-1'))
              .evaluate()
              .isNotEmpty &&
          find
              .byKey(const ValueKey<String>('media-pageflip-flipping-layer'))
              .evaluate()
              .isEmpty) {
        break;
      }
    }

    expect(
      find.byKey(const ValueKey<String>('media-pageflip-static-page-1')),
      findsOneWidget,
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsNothing,
      reason: '落页首个静态帧必须继续使用事务冻结的中性材质，不能同步换成晚到图片。',
    );
    for (var i = 0; i < 3; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
      if (find
          .byKey(const ValueKey<String>('image-book-decoded-surface'))
          .evaluate()
          .isNotEmpty) {
        break;
      }
    }
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsOneWidget,
      reason: '图片只能在目标页完全落平后进入静态页。',
    );
    expect(
      tester
          .widget<AnimatedOpacity>(
            find.byKey(const ValueKey<String>('image-book-ready-fade')),
          )
          .duration,
      ImmersiveMediaWaitMotion.quickReveal,
      reason: '等待指示未出现过的完成走快速淡入，感知为瞬时。',
    );
    // 卸载画布，回收首页仍在等待的 3s/6s 定时器。
    await tester.pumpWidget(_host(const SizedBox()));
  });

  testWidgets('ImageBookCanvas loading 延迟、失败静态提示、翻动退出与重试成功', (tester) async {
    final loader = _ControlledImageLoader();
    final mediaEvents = <ImageBookMediaLoadEvent>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/failure-0.jpg',
              'media/image/s/fixture/v1/failure-1.jpg',
            ]),
            imageLoader: loader.call,
            onMediaLoad: mediaEvents.add,
            onImageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 450));
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsNothing,
      reason: '延迟阈值内不得出现任何等待指示。',
    );
    await tester.pump(const Duration(milliseconds: 70));
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsOneWidget,
    );

    loader.latest(0).completeError(StateError('fixture failed'));
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsNothing,
      reason: 'A visible indicator must complete its minimum display window.',
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsOneWidget,
    );
    await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsOneWidget,
    );
    final failureEvent = mediaEvents.singleWhere(
      (event) => event.result == 'failure',
    );
    expect(failureEvent.durationMs, isNotNull);
    expect(failureEvent.durationMs, greaterThanOrEqualTo(0));
    expect(
      failureEvent.candidatesTried,
      loader.candidateAttempts[0]!.first.length,
    );
    // 交叉淡出退场的 loading 指示走完转场后彻底移除。
    await tester.pump(ImmersiveMediaWaitMotion.crossFade);
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsNothing,
    );
    expect(find.byType(ImmersiveMediaFailureContent), findsOneWidget);
    expect(find.byIcon(Icons.image_not_supported_outlined), findsNothing);
    expect(find.byIcon(CupertinoIcons.refresh), findsNothing);
    expect(find.text(SearchText.reload), findsOneWidget);
    expect(
      tester
          .widget<CupertinoButton>(
            find.byKey(const ValueKey<String>('image-book-retry')),
          )
          .minimumSize,
      const Size(AppSpacing.minInteractiveSize, AppSpacing.minInteractiveSize),
    );

    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final gesture = await tester.startGesture(
      tester.getRect(gestureLayer).center,
    );
    await gesture.moveBy(const Offset(-80, 0));
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsNothing,
      reason: '失败内容仅属于静态状态，拖动开始后不得随纸张翻动。',
    );
    await gesture.cancel();
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsOneWidget,
    );

    await tester.tap(find.byKey(const ValueKey<String>('image-book-retry')));
    await tester.pump();
    expect(loader.attempts[0], hasLength(2));
    expect(loader.candidateAttempts[0], hasLength(2));
    expect(
      loader.candidateAttempts[0]![1],
      orderedEquals(loader.candidateAttempts[0]![0]),
      reason: 'Retry must replay the exact same canonical candidate chain.',
    );
    // 重试跳过延迟阈值：指示立即出现，用户主动动作即时反馈。
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsOneWidget,
    );
    // 失败面走完交叉淡出后移除（动画完成后的下一帧摘除退场层）。
    await tester.pump(ImmersiveMediaWaitMotion.crossFade);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsNothing,
    );
    final retryImage = await _solidImage(240, 360, const Color(0xFF3182CE));
    loader.latest(0).complete(retryImage);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsNothing,
      reason: '指示出现后必须保持满最短展示窗口，不得闪现。',
    );
    await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsOneWidget,
    );
    expect(
      mediaEvents.map((event) => event.result),
      containsAllInOrder(<String>['failure', 'retry', 'success']),
    );
    expect(
      mediaEvents.singleWhere((event) => event.result == 'retry').durationMs,
      0,
      reason: 'retry 是用户触发重放链的即时动作，后续加载耗时由终态事件记录。',
    );
    final successEvent = mediaEvents.singleWhere(
      (event) => event.result == 'success',
    );
    expect(successEvent.durationMs, isNotNull);
    expect(successEvent.durationMs, greaterThanOrEqualTo(0));
    expect(
      successEvent.candidatesTried,
      loader.candidateAttempts[0]!.last.length,
    );
    // 卸载画布，回收另一页仍在等待的 3s/6s 定时器。
    await tester.pumpWidget(_host(const SizedBox()));
  });

  testWidgets('ImageBookCanvas 阈值边界完成时指示保持满最短展示窗口再交叉淡出', (tester) async {
    final loader = _ControlledImageLoader();
    final image = await _solidImage(240, 360, const Color(0xFF38A169));

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>[
              'media/image/s/fixture/v1/hysteresis.jpg',
            ]),
            imageLoader: loader.call,
            onImageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 520));
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsOneWidget,
    );

    // 图片在指示刚出现后就绪（最差闪烁场景）。
    loader.latest(0).complete(image);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsNothing,
      reason: '滞回下界：指示出现后即使图片就绪也保持满最短展示，不得闪现。',
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsOneWidget,
    );

    await tester.pump(ImmersiveMediaWaitMotion.indicatorMinDisplay);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsOneWidget,
    );
    expect(
      tester
          .widget<AnimatedOpacity>(
            find.byKey(const ValueKey<String>('image-book-ready-fade')),
          )
          .duration,
      ImmersiveMediaWaitMotion.crossFade,
      reason: '指示出现过的完成必须经交叉淡出呈现，不得硬切。',
    );
    await tester.pump(ImmersiveMediaWaitMotion.crossFade);
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsNothing,
    );
  });

  testWidgets('ImageBookCanvas 3s 慢提示淡入且不引起指示布局重排', (tester) async {
    final loader = _ControlledImageLoader();

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>['media/image/s/fixture/v1/slow.jpg']),
            imageLoader: loader.call,
            onImageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 600));

    final slowHint = find.byKey(const ValueKey<String>('image-book-slow-hint'));
    expect(tester.widget<AnimatedOpacity>(slowHint).opacity, 0);
    final indicatorCenterBefore = tester.getCenter(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
    );

    await tester.pump(const Duration(milliseconds: 2500));
    expect(
      tester.widget<AnimatedOpacity>(slowHint).opacity,
      1,
      reason: '3 秒（全站 blockedSlowHint 节奏）必须出现慢提示文案。',
    );
    expect(find.text(FoundationText.requestWaitSlow), findsOneWidget);
    expect(
      tester.getCenter(
        find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      ),
      indicatorCenterBefore,
      reason: '慢提示槽位常驻，文字出现不得移动指示位置。',
    );

    await tester.pumpWidget(_host(const SizedBox()));
  });

  testWidgets('ImageBookCanvas 6s 未完成进入失败终态、上报 timeout、重试即时指示', (tester) async {
    final loader = _ControlledImageLoader();
    final mediaEvents = <ImageBookMediaLoadEvent>[];

    await tester.pumpWidget(
      _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(const <String>['media/image/s/fixture/v1/deadline.jpg']),
            imageLoader: loader.call,
            onMediaLoad: mediaEvents.add,
            onImageChanged: (_) {},
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(seconds: 6));
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsOneWidget,
      reason: '6 秒（全站 foregroundReadDeadline）必须进入唯一恢复组失败终态。',
    );
    final timeoutEvent = mediaEvents.singleWhere(
      (event) => event.result == 'timeout',
    );
    expect(timeoutEvent.durationMs, 6000);
    expect(timeoutEvent.candidatesTried, 1);
    expect(
      loader.attempts[0]!.first.cancelled,
      isTrue,
      reason: 'The deadline must cancel the active load operation.',
    );

    await tester.pump(ImmersiveMediaWaitMotion.crossFade);
    await tester.tap(find.byKey(const ValueKey<String>('image-book-retry')));
    await tester.pump();
    expect(loader.attempts[0], hasLength(2));
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsOneWidget,
      reason: '重试必须跳过延迟阈值即时出现指示。',
    );
    expect(
      mediaEvents.map((event) => event.result),
      containsAllInOrder(<String>['timeout', 'retry']),
    );
    expect(
      mediaEvents.singleWhere((event) => event.result == 'retry').durationMs,
      0,
    );

    await tester.pumpWidget(_host(const SizedBox()));
  });

  testWidgets('ImageBookCanvas 等值 URL List 重建不释放已解码图片', (tester) async {
    final loader = _ControlledImageLoader();
    final image = await _solidImage(240, 360, const Color(0xFF2B6CB0));

    Widget buildBook(List<String> urls) {
      return _host(
        SizedBox(
          width: 320,
          height: 480,
          child: ImageBookCanvas(
            deliveries: _publicPages(urls),
            imageLoader: loader.call,
            onImageChanged: (_) {},
          ),
        ),
      );
    }

    await tester.pumpWidget(
      buildBook(<String>['media/image/s/fixture/v1/stable-list.jpg']),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));
    loader.latest(0).complete(image);
    await tester.pump(const Duration(milliseconds: 16));
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsOneWidget,
    );
    expect(loader.attempts[0], hasLength(1));

    await tester.pumpWidget(
      buildBook(<String>['media/image/s/fixture/v1/stable-list.jpg']),
    );
    await tester.pump(const Duration(milliseconds: 16));

    expect(loader.attempts[0], hasLength(1));
    expect(
      find.byKey(const ValueKey<String>('image-book-decoded-surface')),
      findsOneWidget,
      reason: '父级等值重建不得把已落平图片释放成中性页后重新加载。',
    );
  });

  testWidgets('ImageBookCanvas Reduce Motion 图片淡入最长 120ms', (tester) async {
    final loader = _ControlledImageLoader();
    final image = await _solidImage(240, 360, const Color(0xFF805AD5));

    await tester.pumpWidget(
      _host(
        MediaQuery(
          data: const MediaQueryData(disableAnimations: true),
          child: SizedBox(
            width: 320,
            height: 480,
            child: ImageBookCanvas(
              deliveries: _publicPages(const <String>['media/image/s/fixture/v1/reduced.jpg']),
              imageLoader: loader.call,
              onImageChanged: (_) {},
            ),
          ),
        ),
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 16));
    loader.latest(0).complete(image);
    await tester.pump(const Duration(milliseconds: 16));

    expect(
      tester
          .widget<AnimatedOpacity>(
            find.byKey(const ValueKey<String>('image-book-ready-fade')),
          )
          .duration,
      const Duration(milliseconds: 120),
    );
  });
}
