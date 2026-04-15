import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/pageflip_book.dart';

void main() {
  group('PageflipBookIsolatedController', () {
    test(
      'backward scene keeps mirrored working-page touch state and dedicated binding',
      () {
        final controller = PageflipBookIsolatedController(
          pageCount: 4,
          initialPage: 1,
        );
        const stageSize = Size(900, 1200);
        const pageSize = Size(420, 584);
        controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

        expect(controller.start(const Offset(320, 600)), isTrue);
        controller.fold(const Offset(400, 640));

        final scene = controller.sceneForStage(stageSize);
        expect(scene, isNotNull);
        expect(scene!.sheetBinding, isNotNull);
        expect(
          scene.sheetBinding!.direction,
          PageflipBookIsolatedDirection.backward,
        );
        expect(scene.sheetBinding!.rectoPageIndex, 0);
        expect(scene.sheetBinding!.versoPageIndex, 1);
        expect(scene.sheetBinding!.bottomPageIndex, 0);
        expect(scene.coveredCurrentPageIndex, 1);
        expect(scene.turningFrontPageIndex, 0);
        expect(scene.turningBackPageIndex, 1);
        expect(scene.nextUnderPageIndex, 0);
        expect(scene.drawsCoveredCurrentPage, isTrue);
        expect(scene.touchState, isNotNull);
        expect(scene.foldAxisState, isNotNull);
        expect(scene.pose, isNotNull);
        expect(scene.pose!.direction, PageflipBookIsolatedDirection.backward);
        expect(scene.touchState!.bookPoint.dx, closeTo(580, 0.001));
        expect(scene.touchState!.workingPagePoint.dx, closeTo(260, 0.001));
        expect(scene.foldAxisState!.progress, greaterThan(0));
      },
    );

    test(
      'forward scene preserves full 2D working-page input beyond page edge',
      () {
        final controller = PageflipBookIsolatedController(
          pageCount: 4,
          initialPage: 1,
        );
        const stageSize = Size(900, 1200);
        const pageSize = Size(420, 584);
        controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

        final idleScene = controller.sceneForStage(stageSize);
        expect(idleScene, isNotNull);
        final pageRect = idleScene!.pageRect;

        expect(
          controller.start(Offset(pageRect.right - 18, pageRect.bottom - 18)),
          isTrue,
        );
        controller.fold(Offset(pageRect.left - 48, pageRect.center.dy));

        final scene = controller.sceneForStage(stageSize);
        expect(scene, isNotNull);
        expect(scene!.sheetBinding, isNotNull);
        expect(
          scene.sheetBinding!.direction,
          PageflipBookIsolatedDirection.forward,
        );
        expect(scene.sheetBinding!.rectoPageIndex, 1);
        expect(scene.sheetBinding!.versoPageIndex, 2);
        expect(scene.sheetBinding!.bottomPageIndex, 2);
        expect(scene.coveredCurrentPageIndex, 1);
        expect(scene.turningFrontPageIndex, 1);
        expect(scene.turningBackPageIndex, 2);
        expect(scene.nextUnderPageIndex, 2);
        expect(scene.drawsCoveredCurrentPage, isFalse);
        expect(scene.touchState, isNotNull);
        expect(scene.foldAxisState, isNotNull);
        expect(scene.pose, isNotNull);
        expect(scene.pose!.direction, PageflipBookIsolatedDirection.forward);
        expect(scene.touchState!.workingPagePoint.dx, lessThan(0));
        expect(scene.foldAxisState!.progress, greaterThan(0.5));
        expect(scene.pose!.flatLimitX, lessThanOrEqualTo(0));
      },
    );

    test(
      'animation plan carries touch trajectory instead of synthetic progress',
      () {
        final controller = PageflipBookIsolatedController(
          pageCount: 4,
          initialPage: 1,
        );
        const stageSize = Size(900, 1200);
        const pageSize = Size(420, 584);
        controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

        expect(controller.start(const Offset(560, 600)), isTrue);
        controller.fold(const Offset(620, 620));
        final abortPlan = controller.stopMove();
        expect(abortPlan, isNotNull);
        expect(abortPlan!.commitsTurn, isFalse);
        controller.completeAnimation(abortPlan);
        expect(controller.currentPageIndex, 1);

        final commitPlan = controller.flip(
          PageflipBookIsolatedDirection.forward,
        );
        expect(commitPlan, isNotNull);
        expect(commitPlan!.commitsTurn, isTrue);
        expect(
          commitPlan.frames.first.touchState.workingPagePoint.dx,
          greaterThan(0),
        );
        expect(
          commitPlan.frames.last.touchState.workingPagePoint.dx,
          lessThan(0),
        );
        final midFrame = commitPlan.frames[commitPlan.frames.length ~/ 2];
        controller.applyAnimationFrame(midFrame);
        final midScene = controller.sceneForStage(stageSize);
        expect(midScene, isNotNull);
        expect(
          midScene!.touchState!.workingPagePoint.dx,
          closeTo(midFrame.touchState.workingPagePoint.dx, 0.0001),
        );
        expect(midScene.pose!.progress, closeTo(midFrame.progress, 0.0001));
        controller.completeAnimation(commitPlan);
        expect(controller.currentPageIndex, 2);
      },
    );
  });
}
