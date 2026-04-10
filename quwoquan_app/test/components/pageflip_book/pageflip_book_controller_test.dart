import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';

void main() {
  group('PageflipBookController', () {
    test('display mode stays decoupled from orientation', () {
      const controller = PageflipBookController(
        config: PageflipBookConfig(
          pageCount: 8,
          portraitDisplayMode: PageflipBookDisplayMode.spread,
          landscapeDisplayMode: PageflipBookDisplayMode.single,
        ),
      );

      expect(
        controller.resolveDisplayMode(const Size(390, 844)),
        PageflipBookDisplayMode.spread,
      );
      expect(
        controller.resolveDisplayMode(const Size(844, 390)),
        PageflipBookDisplayMode.single,
      );
    });

    test('spread window respects cover and facing pages', () {
      const controller = PageflipBookController(
        config: PageflipBookConfig(
          pageCount: 6,
          showCover: true,
        ),
      );

      final coverWindow = controller.resolveWindow(
        currentPageIndex: 0,
        viewportSize: const Size(1024, 768),
      );
      expect(coverWindow.leftPageIndex, isNull);
      expect(coverWindow.rightPageIndex, 0);

      final middleWindow = controller.resolveWindow(
        currentPageIndex: 3,
        viewportSize: const Size(1024, 768),
      );
      expect(middleWindow.leftPageIndex, 3);
      expect(middleWindow.rightPageIndex, 4);
    });

    test('spread window keeps requested current page visible after regrouping', () {
      const controller = PageflipBookController(
        config: PageflipBookConfig(
          pageCount: 6,
          showCover: true,
        ),
      );

      final rightLeafWindow = controller.resolveWindow(
        currentPageIndex: 4,
        viewportSize: const Size(1024, 768),
      );

      expect(rightLeafWindow.currentPageIndex, 4);
      expect(rightLeafWindow.leftPageIndex, 3);
      expect(rightLeafWindow.rightPageIndex, 4);
      expect(rightLeafWindow.visiblePageIndices, <int>[3, 4]);
    });

    test('scene publishes canonical sheet binding for single-page backward contract', () {
      const controller = PageflipBookController(
        config: PageflipBookConfig(pageCount: 5),
      );

      final scene = controller.resolveScene(
        currentPageIndex: 2,
        viewportSize: const Size(390, 844),
        direction: PageflipBookDirection.backward,
        turningPageIndex: 1,
        coveredPageIndex: 2,
        underPageIndex: 2,
      );
      final binding = scene.surfaceBinding;
      final sheetBinding = scene.sheetBinding;

      expect(binding, isNotNull);
      expect(sheetBinding, isNotNull);
      expect(binding!.pageIndexFor(PageflipBookSurfaceRole.coveredCurrent), 2);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.turningFront), 1);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.turningBack), 2);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.nextUnder), 2);
      expect(sheetBinding!.rectoPageIndex, 1);
      expect(sheetBinding.versoPageIndex, 2);
      expect(sheetBinding.bottomPageIndex, 2);
    });

    test('texture session keeps unique prioritized page order', () {
      final binding = PageflipBookSurfaceRoleBinding(
        roles: <PageflipBookSurfaceRole, int>{
          PageflipBookSurfaceRole.coveredCurrent: 2,
          PageflipBookSurfaceRole.turningFront: 1,
          PageflipBookSurfaceRole.turningBack: 1,
          PageflipBookSurfaceRole.nextUnder: 3,
        },
      );
      final sheetBinding = PageflipBookSheetBinding(
        direction: PageflipBookDirection.backward,
        rectoPageIndex: 1,
        versoPageIndex: 2,
        bottomPageIndex: 3,
      );
      final session = PageflipBookTextureSessionContract(
        binding: binding,
        sheetBinding: sheetBinding,
        preferHighFidelity: true,
      );

      expect(session.prioritizedPageIndices, <int>[1, 2, 3]);
      expect(session.requiredPageIndices, <int>{1, 2, 3});
      expect(session.hasCanonicalSheetBinding, isTrue);
    });

    test('scene can express spread backward sheet binding with explicit covered page', () {
      const controller = PageflipBookController(
        config: PageflipBookConfig(
          pageCount: 6,
          showCover: true,
        ),
      );

      final scene = controller.resolveScene(
        currentPageIndex: 4,
        viewportSize: const Size(1024, 768),
        direction: PageflipBookDirection.backward,
        turningPageIndex: 2,
        coveredPageIndex: 4,
        underPageIndex: 4,
      );
      final binding = scene.surfaceBinding;
      final sheetBinding = scene.sheetBinding;

      expect(binding, isNotNull);
      expect(sheetBinding, isNotNull);
      expect(binding!.pageIndexFor(PageflipBookSurfaceRole.staticLeft), 3);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.staticRight), 4);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.coveredCurrent), 4);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.turningFront), 2);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.turningBack), 4);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.nextUnder), 4);
      expect(sheetBinding!.rectoPageIndex, 2);
      expect(sheetBinding.versoPageIndex, 4);
      expect(sheetBinding.bottomPageIndex, 4);
    });
  });
}
