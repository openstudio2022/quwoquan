import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/components/pageflip_book/pageflip_book.dart';

void main() {
  final binding = PageflipBookSurfaceRoleBinding(
    roles: <PageflipBookSurfaceRole, int>{
      PageflipBookSurfaceRole.coveredCurrent: 2,
      PageflipBookSurfaceRole.turningFront: 1,
      PageflipBookSurfaceRole.turningBack: 1,
    },
  );

  PageflipBookTextureSessionContract buildSession({
    bool preferHighFidelity = true,
    bool hasResolvedBundle = true,
    bool hasMatchingBinding = true,
  }) {
    return PageflipBookTextureSessionContract(
      binding: binding,
      preferHighFidelity: preferHighFidelity,
      hasResolvedBundle: hasResolvedBundle,
      hasMatchingBinding: hasMatchingBinding,
    );
  }

  group('resolvePageflipBookRenderDecision', () {
    test('uses mesh for standard HF path when textures are ready', () {
      final decision = resolvePageflipBookRenderDecision(
        hasDirection: true,
        hasCorner: true,
        supportsAdvancedPageCurl: true,
        usesBackwardLeafContract: false,
        backwardLeafMeshEnabled: false,
        backwardLeafMeshPhaseReady: false,
        hasTextureBinding: true,
        textureSession: buildSession(),
      );

      expect(decision.pipeline, PageflipBookRenderPipeline.mesh);
      expect(decision.reason, isNull);
    });

    test('falls back to legacy when advanced curl is unavailable', () {
      final decision = resolvePageflipBookRenderDecision(
        hasDirection: true,
        hasCorner: true,
        supportsAdvancedPageCurl: false,
        usesBackwardLeafContract: false,
        backwardLeafMeshEnabled: false,
        backwardLeafMeshPhaseReady: false,
        hasTextureBinding: true,
        textureSession: buildSession(),
      );

      expect(decision.pipeline, PageflipBookRenderPipeline.legacy);
      expect(
        decision.reason,
        PageflipBookRenderDecisionReason.advancedPageCurlUnavailable,
      );
    });

    test('falls back to legacy when texture binding mismatches session', () {
      final decision = resolvePageflipBookRenderDecision(
        hasDirection: true,
        hasCorner: true,
        supportsAdvancedPageCurl: true,
        usesBackwardLeafContract: false,
        backwardLeafMeshEnabled: false,
        backwardLeafMeshPhaseReady: false,
        hasTextureBinding: true,
        textureSession: buildSession(hasMatchingBinding: false),
      );

      expect(decision.pipeline, PageflipBookRenderPipeline.legacy);
      expect(
        decision.reason,
        PageflipBookRenderDecisionReason.textureBindingMismatch,
      );
    });

    test('keeps backward leaf on soft path until guarded mesh is ready', () {
      final decision = resolvePageflipBookRenderDecision(
        hasDirection: true,
        hasCorner: true,
        supportsAdvancedPageCurl: true,
        usesBackwardLeafContract: true,
        backwardLeafMeshEnabled: true,
        backwardLeafMeshPhaseReady: false,
        hasTextureBinding: true,
        textureSession: buildSession(),
      );

      expect(decision.pipeline, PageflipBookRenderPipeline.soft);
      expect(
        decision.reason,
        PageflipBookRenderDecisionReason.backwardLeafMeshDeferred,
      );
    });

    test('uses mesh for backward leaf once guarded HF path is ready', () {
      final decision = resolvePageflipBookRenderDecision(
        hasDirection: true,
        hasCorner: true,
        supportsAdvancedPageCurl: true,
        usesBackwardLeafContract: true,
        backwardLeafMeshEnabled: true,
        backwardLeafMeshPhaseReady: true,
        hasTextureBinding: true,
        textureSession: buildSession(),
      );

      expect(decision.pipeline, PageflipBookRenderPipeline.mesh);
      expect(decision.reason, isNull);
    });

    test('falls back to soft when backward leaf textures are unavailable', () {
      final decision = resolvePageflipBookRenderDecision(
        hasDirection: true,
        hasCorner: true,
        supportsAdvancedPageCurl: true,
        usesBackwardLeafContract: true,
        backwardLeafMeshEnabled: true,
        backwardLeafMeshPhaseReady: true,
        hasTextureBinding: true,
        textureSession: buildSession(hasResolvedBundle: false),
      );

      expect(decision.pipeline, PageflipBookRenderPipeline.soft);
      expect(
        decision.reason,
        PageflipBookRenderDecisionReason.missingResolvedTextureBundle,
      );
    });
  });
}
