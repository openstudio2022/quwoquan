import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book_legacy_adapter.dart';

void main() {
  group('PageflipBookLegacyAdapter', () {
    test('creates controller from a single seam helper', () {
      final controller = PageflipBookLegacyAdapter.createController(
        pageCount: 5,
        showCover: true,
        viewportSize: const Size(390, 844),
        pageWidth: 320,
        pageHeight: 500,
        initialPage: 2,
        useForwardMirroredBackwardPath: true,
      );

      expect(controller.currentPageIndex, 2);
      expect(controller.layout.orientation, StPageFlipOrientation.portrait);
      expect(controller.scene.visibleSpread.currentPageIndex, 2);
    });

    test('updates controller configuration without exposing legacy setup', () {
      final controller = PageflipBookLegacyAdapter.createController(
        pageCount: 6,
        showCover: false,
        viewportSize: const Size(390, 844),
        pageWidth: 320,
        pageHeight: 500,
        initialPage: 1,
      );

      PageflipBookLegacyAdapter.updateController(
        controller: controller,
        pageCount: 6,
        showCover: false,
        viewportSize: const Size(390, 844),
        pageWidth: 320,
        pageHeight: 500,
        currentPage: 3,
      );

      expect(controller.currentPageIndex, 3);
      expect(controller.scene.currentPageIndex, 3);
    });

    test('maps displayMode onto legacy single and spread orientations', () {
      final singleController = PageflipBookLegacyAdapter.createController(
        pageCount: 6,
        showCover: false,
        viewportSize: const Size(1200, 800),
        pageWidth: 920,
        pageHeight: 500,
        initialPage: 2,
        displayMode: PageflipBookDisplayMode.single,
      );
      final spreadController = PageflipBookLegacyAdapter.createController(
        pageCount: 6,
        showCover: false,
        viewportSize: const Size(390, 844),
        pageWidth: 185,
        pageHeight: 500,
        initialPage: 2,
        displayMode: PageflipBookDisplayMode.spread,
      );

      expect(singleController.layout.orientation, StPageFlipOrientation.portrait);
      expect(spreadController.layout.orientation, StPageFlipOrientation.landscape);
    });

    test('resolves backward bindings through adapter helpers', () {
      final controller = PageflipBookLegacyAdapter.createController(
        pageCount: 5,
        showCover: false,
        viewportSize: const Size(390, 844),
        pageWidth: 320,
        pageHeight: 500,
        initialPage: 2,
      );

      final plan = controller.flipPrev(StPageFlipCorner.bottom);
      expect(plan, isNotNull);

      final scene = controller.scene;
      final backwardBinding =
          PageflipBookLegacyAdapter.resolveBackwardSurfaceBindingForScene(scene);
      final roleBinding =
          PageflipBookLegacyAdapter.resolveSurfaceRoleBindingForScene(scene);
      final softFrame =
          PageflipBookLegacyAdapter.resolveSingleBackwardSoftFrameForScene(scene);
      final textureBinding =
          PageflipBookLegacyAdapter.resolveTextureBindingForScene(scene);

      expect(backwardBinding?.coveredPageIndex, 2);
      expect(backwardBinding?.leafPageIndex, 1);
      expect(
        roleBinding?.pageIndexFor(PageflipBookSurfaceRole.coveredCurrent),
        2,
      );
      expect(
        roleBinding?.pageIndexFor(PageflipBookSurfaceRole.turningFront),
        1,
      );
      expect(
        roleBinding?.pageIndexFor(PageflipBookSurfaceRole.turningBack),
        2,
      );
      expect(softFrame, isNotNull);
      expect(softFrame!.curlWidthNormalized, greaterThan(0));
      expect(softFrame.laidDownWidthNormalized, inInclusiveRange(0.0, 1.0));
      expect(textureBinding?.rectoPageIndex, 1);
      expect(textureBinding?.bottomPageIndex, 2);
    });

    test('spread backward binding covers current right page and stays off soft-single path', () {
      final controller = PageflipBookLegacyAdapter.createController(
        pageCount: 6,
        showCover: false,
        viewportSize: const Size(1400, 900),
        pageWidth: 680,
        pageHeight: 500,
        initialPage: 2,
        displayMode: PageflipBookDisplayMode.spread,
        useForwardMirroredBackwardPath: true,
      );

      final plan = controller.flipPrev(StPageFlipCorner.bottom);
      expect(plan, isNotNull);

      final scene = controller.scene;
      final roleBinding =
          PageflipBookLegacyAdapter.resolveSurfaceRoleBindingForScene(scene);
      final softFrame =
          PageflipBookLegacyAdapter.resolveSingleBackwardSoftFrameForScene(scene);

      expect(roleBinding, isNotNull);
      expect(roleBinding!.pageIndexFor(PageflipBookSurfaceRole.staticLeft), 2);
      expect(roleBinding.pageIndexFor(PageflipBookSurfaceRole.staticRight), 3);
      expect(roleBinding.pageIndexFor(PageflipBookSurfaceRole.coveredCurrent), 3);
      expect(roleBinding.pageIndexFor(PageflipBookSurfaceRole.turningFront), 1);
      expect(roleBinding.pageIndexFor(PageflipBookSurfaceRole.turningBack), 3);
      expect(roleBinding.pageIndexFor(PageflipBookSurfaceRole.nextUnder), 3);
      expect(softFrame, isNull);
    });

    test('spread forward binding keeps current spread static roles and target under page', () {
      final controller = PageflipBookLegacyAdapter.createController(
        pageCount: 6,
        showCover: false,
        viewportSize: const Size(1400, 900),
        pageWidth: 680,
        pageHeight: 500,
        initialPage: 0,
        displayMode: PageflipBookDisplayMode.spread,
      );

      final plan = controller.flipNext(StPageFlipCorner.bottom);
      expect(plan, isNotNull);

      final binding =
          PageflipBookLegacyAdapter.resolveSurfaceRoleBindingForScene(
            controller.scene,
          );

      expect(binding, isNotNull);
      expect(binding!.pageIndexFor(PageflipBookSurfaceRole.staticLeft), 0);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.staticRight), 1);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.coveredCurrent), 1);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.turningFront), 2);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.turningBack), 3);
      expect(binding.pageIndexFor(PageflipBookSurfaceRole.nextUnder), 3);
    });

    test('bridges legacy texture readiness into pageflip_book session contract', () {
      final roleBinding = PageflipBookSurfaceRoleBinding(
        roles: <PageflipBookSurfaceRole, int>{
          PageflipBookSurfaceRole.coveredCurrent: 2,
          PageflipBookSurfaceRole.turningFront: 1,
        },
      );

      final session = PageflipBookLegacyAdapter.resolveTextureSessionContract(
        binding: roleBinding,
        preferHighFidelity: true,
        hasResolvedBundle: true,
      );
      final deferred = PageflipBookLegacyAdapter.resolveTextureSessionContract(
        binding: roleBinding,
        preferHighFidelity: false,
        hasResolvedBundle: false,
        hasMatchingBinding: false,
      );

      expect(session, isNotNull);
      expect(session!.isReadyForHighFidelity, isTrue);
      expect(deferred, isNotNull);
      expect(deferred!.isReadyForHighFidelity, isFalse);
      expect(deferred.hasMatchingBinding, isFalse);
    });
  });
}
