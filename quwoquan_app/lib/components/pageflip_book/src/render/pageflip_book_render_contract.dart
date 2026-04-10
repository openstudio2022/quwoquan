import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/src/snapshot/pageflip_book_snapshot_contract.dart';

enum PageflipBookRenderPipeline { legacy, soft, mesh }

enum PageflipBookRenderDecisionReason {
  missingSceneDirection,
  missingSceneCorner,
  advancedPageCurlUnavailable,
  missingTextureBinding,
  missingTextureSession,
  textureBindingMismatch,
  missingResolvedTextureBundle,
  highFidelityNotPreferred,
  backwardLeafMeshDeferred,
  backwardLeafMeshUnavailable,
}

@immutable
class PageflipBookRenderDecision {
  const PageflipBookRenderDecision({
    required this.pipeline,
    this.reason,
  });

  final PageflipBookRenderPipeline pipeline;
  final PageflipBookRenderDecisionReason? reason;

  bool get usesMesh => pipeline == PageflipBookRenderPipeline.mesh;

  bool get usesSoft => pipeline == PageflipBookRenderPipeline.soft;

  bool get usesLegacy => pipeline == PageflipBookRenderPipeline.legacy;
}

PageflipBookRenderDecision resolvePageflipBookRenderDecision({
  required bool hasDirection,
  required bool hasCorner,
  required bool supportsAdvancedPageCurl,
  required bool usesBackwardLeafContract,
  required bool backwardLeafMeshEnabled,
  required bool backwardLeafMeshPhaseReady,
  required bool hasTextureBinding,
  required PageflipBookTextureSessionContract? textureSession,
}) {
  if (!hasDirection) {
    return const PageflipBookRenderDecision(
      pipeline: PageflipBookRenderPipeline.legacy,
      reason: PageflipBookRenderDecisionReason.missingSceneDirection,
    );
  }
  if (!hasCorner) {
    return const PageflipBookRenderDecision(
      pipeline: PageflipBookRenderPipeline.legacy,
      reason: PageflipBookRenderDecisionReason.missingSceneCorner,
    );
  }

  PageflipBookRenderDecision withFallback(
    PageflipBookRenderPipeline pipeline,
    PageflipBookRenderDecisionReason reason,
  ) {
    return PageflipBookRenderDecision(pipeline: pipeline, reason: reason);
  }

  final fallbackPipeline = usesBackwardLeafContract
      ? PageflipBookRenderPipeline.soft
      : PageflipBookRenderPipeline.legacy;

  if (!supportsAdvancedPageCurl) {
    return withFallback(
      fallbackPipeline,
      PageflipBookRenderDecisionReason.advancedPageCurlUnavailable,
    );
  }
  if (!hasTextureBinding) {
    return withFallback(
      fallbackPipeline,
      PageflipBookRenderDecisionReason.missingTextureBinding,
    );
  }
  if (textureSession == null) {
    return withFallback(
      fallbackPipeline,
      PageflipBookRenderDecisionReason.missingTextureSession,
    );
  }
  if (!textureSession.hasMatchingBinding) {
    return withFallback(
      fallbackPipeline,
      PageflipBookRenderDecisionReason.textureBindingMismatch,
    );
  }
  if (!textureSession.hasResolvedBundle) {
    return withFallback(
      fallbackPipeline,
      PageflipBookRenderDecisionReason.missingResolvedTextureBundle,
    );
  }
  if (!textureSession.preferHighFidelity) {
    return withFallback(
      fallbackPipeline,
      PageflipBookRenderDecisionReason.highFidelityNotPreferred,
    );
  }

  if (usesBackwardLeafContract) {
    if (!backwardLeafMeshEnabled) {
      return withFallback(
        PageflipBookRenderPipeline.soft,
        PageflipBookRenderDecisionReason.backwardLeafMeshUnavailable,
      );
    }
    if (!backwardLeafMeshPhaseReady) {
      return withFallback(
        PageflipBookRenderPipeline.soft,
        PageflipBookRenderDecisionReason.backwardLeafMeshDeferred,
      );
    }
  }

  return const PageflipBookRenderDecision(
    pipeline: PageflipBookRenderPipeline.mesh,
  );
}
