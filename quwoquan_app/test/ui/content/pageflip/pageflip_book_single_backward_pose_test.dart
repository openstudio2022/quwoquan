import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';

void main() {
  group('PageflipBookSingleBackwardPoseSolver', () {
    const solver = PageflipBookSingleBackwardPoseSolver();
    const pageSize = Size(180, 260);

    test('covered width grows monotonically with horizontal drag distance', () {
      final poses = <PageflipBookSingleBackwardPose>[
        solver.solve(
          pageSize: pageSize,
          localPoint: const Offset(12, 28),
          startPoint: const Offset(0, 20),
          corner: PageflipBookCorner.top,
        ),
        solver.solve(
          pageSize: pageSize,
          localPoint: const Offset(48, 28),
          startPoint: const Offset(0, 20),
          corner: PageflipBookCorner.top,
        ),
        solver.solve(
          pageSize: pageSize,
          localPoint: const Offset(96, 28),
          startPoint: const Offset(0, 20),
          corner: PageflipBookCorner.top,
        ),
        solver.solve(
          pageSize: pageSize,
          localPoint: const Offset(144, 28),
          startPoint: const Offset(0, 20),
          corner: PageflipBookCorner.top,
        ),
      ];

      expect(
        poses
            .map((pose) => pose.coveredWidthNormalized)
            .toList(growable: false),
        orderedEquals(
          poses
              .map((pose) => pose.coveredWidthNormalized)
              .toList(growable: false)
            ..sort(),
        ),
      );
      expect(
        poses.last.commitProgress,
        greaterThan(poses.first.commitProgress),
      );
      for (final pose in poses) {
        expect(
          pose.coveredWidthNormalized,
          greaterThanOrEqualTo(pose.laidDownWidthNormalized),
        );
        expect(
          pose.curlPivotNormalized,
          inInclusiveRange(
            pose.laidDownWidthNormalized,
            pose.coveredWidthNormalized,
          ),
        );
      }
    });

    test('top and bottom corners produce different lift characteristics', () {
      final topPose = solver.solve(
        pageSize: pageSize,
        localPoint: const Offset(72, 34),
        startPoint: const Offset(0, 12),
        corner: PageflipBookCorner.top,
      );
      final bottomPose = solver.solve(
        pageSize: pageSize,
        localPoint: const Offset(72, 226),
        startPoint: const Offset(0, 248),
        corner: PageflipBookCorner.bottom,
      );

      expect(topPose.liftDirection, lessThan(0));
      expect(bottomPose.liftDirection, greaterThan(0));
      expect(topPose.edgeLift, isNot(closeTo(bottomPose.edgeLift, 0.0001)));
      expect(topPose.shadowAxisNormalized, lessThanOrEqualTo(topPose.coveredWidthNormalized));
      expect(
        bottomPose.shadowAxisNormalized,
        lessThanOrEqualTo(bottomPose.coveredWidthNormalized),
      );
    });
  });
}
