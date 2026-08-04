import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart' show Icons;
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/media/media_asset/presentation/image_book_canvas.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

Widget _host(
  Size viewport,
  ImageBookImageLoader loader,
  ValueChanged<int> onPage,
) {
  return ProviderScope(
    child: CupertinoApp(
      home: CupertinoPageScaffold(
        child: Center(
          child: SizedBox.fromSize(
            size: viewport,
            child: ImageBookCanvas(
              imageUrls: const <String>[
                'media/image/s/uat/book-0.jpg',
                'media/image/s/uat/book-1.jpg',
              ],
              imageLoader: loader,
              onImageChanged: onPage,
            ),
          ),
        ),
      ),
    ),
  );
}

Future<ui.Image> _pageImage(int pageIndex, Size pageSize) async {
  final recorder = ui.PictureRecorder();
  final canvas = ui.Canvas(recorder);
  final width = math.max(1, pageSize.width.round());
  final height = math.max(1, pageSize.height.round());
  final colors = pageIndex.isEven
      ? const <Color>[
          Color(0xFF174A72),
          Color(0xFF2D7A68),
          Color(0xFFB6A15F),
          Color(0xFF8F4E58),
        ]
      : const <Color>[
          Color(0xFF713E5A),
          Color(0xFFB06C49),
          Color(0xFF3B7693),
          Color(0xFF52734D),
        ];
  final stripeWidth = width / colors.length;
  for (var index = 0; index < colors.length; index += 1) {
    canvas.drawRect(
      Rect.fromLTWH(index * stripeWidth, 0, stripeWidth, height.toDouble()),
      ui.Paint()..color = colors[index],
    );
  }
  final picture = recorder.endRecording();
  final image = await picture.toImage(width, height);
  picture.dispose();
  return image;
}

Future<void> _exerciseTenTurns(WidgetTester tester, Size viewport) async {
  await tester.binding.setSurfaceSize(viewport);
  addTearDown(() => tester.binding.setSurfaceSize(null));
  final changed = <int>[];

  await tester.pumpWidget(
    _host(
      viewport,
      ({
        required context,
        required pageIndex,
        required candidates,
        required pageSize,
      }) => _pageImage(pageIndex, pageSize),
      changed.add,
    ),
  );
  await tester.pump();
  for (var i = 0; i < 20; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  var expectedPage = 0;
  for (var turn = 0; turn < 10; turn += 1) {
    final forward = expectedPage == 0;
    final gestureLayer = find.byKey(
      const ValueKey<String>('media-pageflip-gesture-layer'),
    );
    final rect = tester.getRect(gestureLayer);
    final gesture = await tester.startGesture(rect.center);
    await gesture.moveBy(Offset((forward ? -1 : 1) * rect.width * 0.64, 0));
    await tester.pump(const Duration(milliseconds: 16));

    final movingSheet = find.byKey(
      const ValueKey<String>('media-pageflip-flipping-layer'),
    );
    expect(movingSheet, findsOneWidget);
    expect(
      find.descendant(of: movingSheet, matching: find.byType(RawImage)),
      findsOneWidget,
      reason: '$viewport 第 ${turn + 1} 次翻页只能有一个完整页面材质。',
    );
    expect(
      find.descendant(
        of: movingSheet,
        matching: find.byType(FractionallySizedBox),
      ),
      findsNothing,
      reason: '$viewport 不得恢复两个重叠纹理子平面。',
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-loading-overlay')),
      findsNothing,
    );
    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsNothing,
    );

    await gesture.up();
    for (var i = 0; i < 40; i += 1) {
      await tester.pump(const Duration(milliseconds: 16));
    }
    expectedPage = forward ? 1 : 0;
    expect(changed.last, expectedPage);
    expect(
      find.byKey(ValueKey<String>('media-pageflip-static-page-$expectedPage')),
      findsOneWidget,
    );
  }
}

void main() {
  for (final viewport in const <Size>[
    Size(390, 844),
    Size(430, 932),
    Size(834, 1112),
  ]) {
    testWidgets('视频书 $viewport 连续前后翻 10 次保持单纸面', (tester) {
      return _exerciseTenTurns(tester, viewport);
    });
  }

  testWidgets('视频书静态图片失败使用无图标统一文字重试', (tester) async {
    const viewport = Size(390, 844);
    await tester.binding.setSurfaceSize(viewport);
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(
      _host(
        viewport,
        ({
          required context,
          required pageIndex,
          required candidates,
          required pageSize,
        }) => Future<ui.Image>.error(StateError('controlled image failure')),
        (_) {},
      ),
    );
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 360));

    expect(
      find.byKey(const ValueKey<String>('image-book-failure-overlay')),
      findsOneWidget,
    );
    expect(find.byIcon(Icons.image_not_supported_outlined), findsNothing);
    expect(find.byIcon(CupertinoIcons.refresh), findsNothing);
    expect(find.text(SearchText.reload), findsOneWidget);
    expect(
      tester
          .getRect(find.byKey(const ValueKey<String>('image-book-retry')))
          .size
          .shortestSide,
      greaterThanOrEqualTo(AppSpacing.minInteractiveSize),
    );

    expect(
      find.descendant(
        of: find.byKey(const ValueKey<String>('image-book-failure-overlay')),
        matching: find.byWidgetPredicate(
          (widget) =>
              widget is Semantics && widget.properties.liveRegion == true,
        ),
      ),
      findsOneWidget,
    );
  });
}
