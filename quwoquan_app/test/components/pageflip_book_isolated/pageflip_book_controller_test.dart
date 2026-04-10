import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/pageflip_book.dart';

void main() {
  group('PageflipBookIsolatedController', () {
    test('backward scene resolves canonical recto verso bottom binding', () {
      final controller = PageflipBookIsolatedController(
        pageCount: 4,
        initialPage: 1,
      );
      const stageSize = Size(900, 1200);
      const pageSize = Size(420, 584);
      controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

      expect(controller.start(const Offset(320, 600)), isTrue);

      final scene = controller.sceneForStage(stageSize);
      expect(scene, isNotNull);
      expect(scene!.sheetBinding, isNotNull);
      expect(
        scene.sheetBinding!.direction,
        PageflipBookIsolatedDirection.backward,
      );
      expect(scene.sheetBinding!.rectoPageIndex, 0);
      expect(scene.sheetBinding!.versoPageIndex, 1);
      expect(scene.sheetBinding!.bottomPageIndex, 1);
    });

    test(
      'forward scene reuses the same sheet contract with mirrored indices',
      () {
        final controller = PageflipBookIsolatedController(
          pageCount: 4,
          initialPage: 1,
        );
        const stageSize = Size(900, 1200);
        const pageSize = Size(420, 584);
        controller.updateViewport(stageSize: stageSize, pageSize: pageSize);

        expect(controller.start(const Offset(560, 600)), isTrue);

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
      },
    );
  });
}
