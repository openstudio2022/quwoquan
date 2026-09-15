import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/immersive_viewer_layout.dart';
import 'package:quwoquan_app/service/content_service/media/media_asset/presentation/video_player_surface_builder.dart';

// spec_ref: specs/feature-tree/discovery-content/content-display-consistency/video-display-journey/spec.md#gwt-004
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-005
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-021
// spec_ref: specs/feature-tree/discovery-content/dual-rail-discovery-redesign/works-immersive-viewer/spec.md#gwt-023
void main() {
  group('整栏透明档位', () {
    const size = Size(400, 880);
    for (final sample in <({double height, Rect viewport})>[
      (height: 619.99, viewport: const Rect.fromLTWH(0, 80.0045, 400, 619.99)),
      (height: 620, viewport: const Rect.fromLTWH(0, 80, 400, 620)),
      (height: 620.01, viewport: const Rect.fromLTWH(0, 80, 400, 620)),
      (height: 660, viewport: const Rect.fromLTWH(0, 80, 400, 620)),
      (height: 699.99, viewport: const Rect.fromLTWH(0, 80, 400, 620)),
      (height: 700, viewport: const Rect.fromLTWH(0, 0, 400, 700)),
      (height: 700.01, viewport: const Rect.fromLTWH(0, 0, 400, 700)),
      (height: 760, viewport: const Rect.fromLTWH(0, 0, 400, 700)),
      (height: 879.99, viewport: const Rect.fromLTWH(0, 0, 400, 700)),
      (height: 880, viewport: const Rect.fromLTWH(0, 0, 400, 880)),
      (height: 880.01, viewport: const Rect.fromLTWH(0, 0, 400, 880)),
      (height: 960, viewport: const Rect.fromLTWH(0, 0, 400, 880)),
    ]) {
      test('自然高度 ${sample.height} 只落整栏窗口且上下等裁', () {
        final geometry = ImmersiveMediaGeometry(
          size: size,
          aspectRatio: size.width / sample.height,
          topInset: 80,
          bottomInset: 180,
        );
        _expectRectClose(geometry.viewportRect, sample.viewport);
        expect(geometry.contentRect.width, size.width);
        expect(geometry.contentRect.height, closeTo(sample.height, 0.00001));
        expect(geometry.contentRect.left, 0);
        expect(geometry.contentRect.right, size.width);
        expect(
          geometry.viewportRect.top - geometry.contentRect.top,
          closeTo(
            geometry.contentRect.bottom - geometry.viewportRect.bottom,
            0.00001,
          ),
        );
        expect(geometry.entryRect, Rect.zero);
      });
    }
  });

  test('宽媒体留白按45/55分配且入口紧贴实际画面', () {
    final geometry = ImmersiveMediaGeometry(
      size: const Size(400, 880),
      aspectRatio: 16 / 9,
      topInset: 80,
      bottomInset: 180,
      entryExtent: 52,
    );
    const slack = (700 - 52 - 80) - 225;
    _expectRectClose(
      geometry.contentRect,
      const Rect.fromLTWH(0, 80 + slack * .45, 400, 225),
    );
    _expectRectClose(geometry.viewportRect, geometry.contentRect);
    expect(
      geometry.entryRect,
      Rect.fromLTWH(0, geometry.viewportRect.bottom, 400, 52),
    );
    expect(648 - geometry.entryRect.top, closeTo(slack * .55, .00001));
  });

  for (final ratio in <double>[
    21 / 9,
    16 / 9,
    4 / 3,
    1,
    3 / 4,
    9 / 16,
    400 / 880,
    1 / 8,
  ]) {
    for (final size in <Size>[
      const Size(320, 640),
      const Size(400, 880),
      const Size(1024, 1366),
    ]) {
      test('自然比例 $ratio 在 $size 不左右裁、不拉伸', () {
        final geometry = ImmersiveMediaGeometry(
          size: size,
          aspectRatio: ratio,
          topInset: 80,
          bottomInset: 160,
          entryExtent: ratio > 1 ? 44 : 0,
        );
        expect(geometry.contentRect.width, size.width);
        expect(
          geometry.contentRect.width / geometry.contentRect.height,
          closeTo(ratio, .00001),
        );
        expect(geometry.viewportRect.left, 0);
        expect(geometry.viewportRect.right, size.width);
        expect(geometry.viewportRect.height, greaterThan(0));
        expect(geometry.viewportRect.bottom, lessThanOrEqualTo(size.height));
      });
    }
  }

  test('未知比例不冒用16:9且不提供入口', () {
    for (final ratio in [0.0, -1.0, double.nan, double.infinity]) {
      final geometry = ImmersiveMediaGeometry(
        size: const Size(400, 880),
        aspectRatio: ratio,
        topInset: 80,
        bottomInset: 180,
        entryExtent: 52,
      );
      expect(geometry.contentRect, Rect.zero);
      expect(geometry.entryRect, Rect.zero);
      expect(geometry.viewportRect, const Rect.fromLTWH(0, 80, 400, 620));
    }
  });

  test('横向全屏完整contain且上下控制栏不压缩媒体', () {
    for (final ratio in [21 / 9, 16 / 9, 1.0, 9 / 16]) {
      final geometry = ImmersiveMediaGeometry(
        size: const Size(880, 400),
        aspectRatio: ratio,
        topInset: 80,
        bottomInset: 180,
        entryExtent: 52,
        fullscreen: true,
      );
      expect(geometry.viewportRect, const Rect.fromLTWH(0, 0, 880, 400));
      expect(geometry.contentRect.center.dx, closeTo(440, .00001));
      expect(geometry.contentRect.center.dy, closeTo(200, .00001));
      expect(
        geometry.contentRect.width / geometry.contentRect.height,
        closeTo(ratio, .00001),
      );
      expect(geometry.contentRect.width, lessThanOrEqualTo(880));
      expect(geometry.contentRect.height, lessThanOrEqualTo(400));
      expect(geometry.entryRect, Rect.zero);
    }
  });

  test('视频从同pass信息测量消费共享几何，不按竖视频强制cover', () {
    for (final size in [
      const Size(320, 640),
      const Size(402, 874),
      const Size(1024, 1366),
    ]) {
      for (final ratio in [16 / 9, 1.0, 9 / 16, 1 / 8]) {
        for (final scale in [1.0, 2.0, 3.0]) {
          for (final association in [0.0, 24.0]) {
            for (final caption in [0.0, 40.0]) {
              final geometry = WorksVideoGeometry(
                size: size,
                aspectRatio: ratio,
                topInset: 48,
                toolbarHeight: 80,
                captionHeight: caption * scale,
                associationHeight: association * scale,
                entryHeight: ratio > 1 ? 44 : 0,
              );
              final shared = ImmersiveMediaGeometry(
                size: size,
                aspectRatio: ratio,
                topInset: 48,
                bottomInset: size.height - geometry.informationRect.top,
                entryExtent: ratio > 1 ? 44 : 0,
              );
              expect(geometry.stageRect, shared.viewportRect);
              expect(geometry.videoRect, shared.contentRect);
              expect(geometry.entryRect, shared.entryRect);
              expect(geometry.timelineRect.bottom, geometry.toolbarRect.top);
              expect(geometry.captionRect.height, caption * scale);
              expect(geometry.associationRect.height, association * scale);
              expect(
                geometry.associationRect.overlaps(geometry.captionRect),
                isFalse,
              );
              expect(
                geometry.captionRect.bottom,
                lessThan(geometry.timelineRect.top),
              );
              if (ratio > 1) {
                expect(
                  geometry.entryRect.bottom,
                  lessThanOrEqualTo(geometry.informationRect.top),
                );
              }
            }
          }
        }
      }
    }
  });

  group('横向三轨几何', () {
    test('外槽与stage不随素材比例移动，内部轨跟随实际像素', () {
      final values = [21 / 9, 16 / 9, 1.01]
          .map(
            (ratio) => ImmersiveLandscapeGeometry(
              size: const Size(880, 400),
              safeInsets: const EdgeInsets.fromLTRB(47, 0, 34, 0),
              aspectRatio: ratio,
            ),
          )
          .toList();
      for (final geometry in values) {
        expect(geometry.leftControlSlot.width, greaterThanOrEqualTo(44));
        expect(geometry.rightControlSlot.width, greaterThanOrEqualTo(44));
        expect(
          geometry.leftControlSlot.right,
          lessThan(geometry.mediaStageRect.left),
        );
        expect(
          geometry.mediaStageRect.right,
          lessThan(geometry.rightControlSlot.left),
        );
        expect(
          geometry.visibleMediaRect.left,
          greaterThanOrEqualTo(geometry.mediaStageRect.left),
        );
        expect(
          geometry.visibleMediaRect.top,
          greaterThanOrEqualTo(geometry.mediaStageRect.top),
        );
        expect(
          geometry.visibleMediaRect.right,
          lessThanOrEqualTo(geometry.mediaStageRect.right),
        );
        expect(
          geometry.visibleMediaRect.bottom,
          lessThanOrEqualTo(geometry.mediaStageRect.bottom),
        );
        expect(geometry.mediaInnerRail.left, geometry.visibleMediaRect.left);
        expect(geometry.mediaInnerRail.right, geometry.visibleMediaRect.right);
      }
      for (final geometry in values.skip(1)) {
        expect(geometry.leftControlSlot, values.first.leftControlSlot);
        expect(geometry.mediaStageRect, values.first.mediaStageRect);
        expect(geometry.rightControlSlot, values.first.rightControlSlot);
      }
      expect(
        values.last.visibleMediaRect.width,
        lessThan(values.first.visibleMediaRect.width),
      );
    });

    test('非对称安全区分别约束左右外槽且无效比例不猜测', () {
      final geometry = ImmersiveLandscapeGeometry(
        size: const Size(874, 402),
        safeInsets: const EdgeInsets.fromLTRB(47, 3, 34, 5),
        aspectRatio: 16 / 9,
      );
      expect(geometry.safeViewportRect, const Rect.fromLTRB(47, 3, 840, 397));
      expect(geometry.leftControlSlot.left, 47);
      expect(geometry.rightControlSlot.right, 840);
      expect(geometry.visibleMediaRect.center, geometry.mediaStageRect.center);

      final invalid = ImmersiveLandscapeGeometry(
        size: const Size(874, 402),
        safeInsets: EdgeInsets.zero,
        aspectRatio: double.nan,
      );
      expect(invalid.visibleMediaRect, Rect.zero);
    });
  });

  testWidgets('独立播放器 contain 保持完整，显式cover仍保留原始比例', (tester) async {
    for (final fit in [BoxFit.cover, BoxFit.contain]) {
      await tester.pumpWidget(
        Directionality(
          textDirection: TextDirection.ltr,
          child: Center(
            child: SizedBox(
              width: 402,
              height: 700,
              child: VideoPlayerSurfaceBuilder.buildCenteredFrame(
                aspectRatio: 9 / 16,
                fit: fit,
                child: const SizedBox(key: ValueKey('frame')),
              ),
            ),
          ),
        ),
      );
      final frame = tester.getSize(find.byKey(const ValueKey('frame')));
      expect(frame.width / frame.height, closeTo(9 / 16, 0.001));
      if (fit == BoxFit.cover) {
        expect(frame.width, greaterThanOrEqualTo(402));
        expect(frame.height, greaterThanOrEqualTo(700));
      } else {
        expect(frame.width, lessThanOrEqualTo(402));
        expect(frame.height, lessThanOrEqualTo(700));
      }
    }
  });
}

void _expectRectClose(Rect actual, Rect expected) {
  expect(actual.left, closeTo(expected.left, .00001));
  expect(actual.top, closeTo(expected.top, .00001));
  expect(actual.width, closeTo(expected.width, .00001));
  expect(actual.height, closeTo(expected.height, .00001));
}
