import 'dart:ui';

import 'package:flutter/gestures.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';

void main() {
  group('PageflipBookSingleBackwardInteractionController', () {
    const pageSize = Size(180, 260);

    test('small drag aborts and animates back to the left edge', () {
      final controller = PageflipBookSingleBackwardInteractionController();

      controller.start(
        localPoint: const Offset(8, 238),
        pageSize: pageSize,
        corner: PageflipBookCorner.bottom,
      );
      controller.update(const Offset(30, 228));

      final result = controller.end(Velocity.zero);

      expect(result, isNotNull);
      expect(result!.shouldCommit, isFalse);
      expect(result.animationPlan.isTurned, isFalse);
      expect(result.pose.commitProgress, lessThan(0.52));
      expect(result.animationPlan.frames.first.dx, greaterThan(0));
      expect(result.animationPlan.frames.last.dx, closeTo(0, 0.001));
    });

    test('large drag commits and animates toward the right edge', () {
      final controller = PageflipBookSingleBackwardInteractionController();

      controller.start(
        localPoint: const Offset(8, 18),
        pageSize: pageSize,
        corner: PageflipBookCorner.top,
      );
      controller.update(const Offset(118, 26));

      final result = controller.end(Velocity.zero);

      expect(result, isNotNull);
      expect(result!.shouldCommit, isTrue);
      expect(result.animationPlan.isTurned, isTrue);
      expect(result.pose.commitProgress, greaterThanOrEqualTo(0.52));
      expect(
        result.animationPlan.frames.last.dx,
        closeTo(pageSize.width, 0.001),
      );
    });

    test('high positive horizontal velocity can assist commit', () {
      final controller = PageflipBookSingleBackwardInteractionController();

      controller.start(
        localPoint: const Offset(8, 238),
        pageSize: pageSize,
        corner: PageflipBookCorner.bottom,
      );
      controller.update(const Offset(42, 232));

      final result = controller.end(
        const Velocity(pixelsPerSecond: Offset(420, 0)),
      );

      expect(result, isNotNull);
      expect(result!.shouldCommit, isTrue);
    });

    test('update keeps pose tied to latest finger point', () {
      final controller = PageflipBookSingleBackwardInteractionController();

      controller.start(
        localPoint: const Offset(6, 22),
        pageSize: pageSize,
        corner: PageflipBookCorner.top,
      );

      final state = controller.update(const Offset(90, 34));

      expect(state, isNotNull);
      expect(state!.pose.dragPoint.dx, closeTo(90, 0.001));
      expect(state.pose.coveredWidthNormalized, closeTo(0.5, 0.05));
      expect(
        state.pose.coveredWidthNormalized,
        greaterThanOrEqualTo(state.pose.laidDownWidthNormalized),
      );
    });
  });
}
