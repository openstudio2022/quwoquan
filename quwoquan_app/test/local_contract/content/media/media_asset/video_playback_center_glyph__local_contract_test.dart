import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/content/media/media_asset/presentation/video_playback_center_glyph.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

void main() {
  testWidgets('暂停态播放三角放大且不绘制背景容器', (tester) async {
    final repaintKey = GlobalKey();
    await tester.pumpWidget(
      MaterialApp(
        home: Center(
          child: RepaintBoundary(
            key: repaintKey,
            child: const VideoPlaybackCenterPlayGlyph(
              key: ValueKey<String>('center-play-glyph'),
            ),
          ),
        ),
      ),
    );

    final glyph = find.byKey(const ValueKey<String>('center-play-glyph'));
    final paint = find.byKey(
      const ValueKey<String>('video-rounded-play-glyph-paint'),
    );
    expect(tester.getSize(glyph), const Size.square(52));
    expect(tester.getSize(paint), const Size.square(44));
    expect(
      find.descendant(of: glyph, matching: find.byType(DecoratedBox)),
      findsNothing,
    );

    final boundary =
        repaintKey.currentContext!.findRenderObject()! as RenderRepaintBoundary;
    final image = (await tester.runAsync(
      () => boundary.toImage(pixelRatio: 1),
    ))!;
    final bytes = (await tester.runAsync(
      () => image.toByteData(format: ui.ImageByteFormat.rawRgba),
    ))!;
    final cornerAlpha = bytes.getUint8(3);
    final centerOffset =
        ((image.height ~/ 2) * image.width + image.width ~/ 2) * 4;
    final centerAlpha = bytes.getUint8(centerOffset + 3);
    expect(cornerAlpha, 0, reason: '控件四角必须保持透明，不能恢复圆形背景');
    expect(centerAlpha, greaterThan(0), reason: '放大的圆角播放三角必须可见');
  });

  testWidgets('播放三角只作装饰且不建立第二个按钮语义', (tester) async {
    await tester.pumpWidget(
      const MaterialApp(home: VideoPlaybackCenterPlayGlyph()),
    );

    expect(
      find.descendant(
        of: find.byType(VideoPlaybackCenterPlayGlyph),
        matching: find.byWidgetPredicate(
          (widget) => widget is Semantics && widget.properties.button == true,
        ),
      ),
      findsNothing,
    );
    expect(AppSpacing.videoPlayRoundedGlyphSize, greaterThan(22));
  });
}
