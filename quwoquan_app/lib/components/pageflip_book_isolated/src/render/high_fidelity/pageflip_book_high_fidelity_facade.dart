import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/scene/pageflip_book_scene.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/snapshot/pageflip_book_texture_session.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class PageflipBookIsolatedHighFidelityState {
  const PageflipBookIsolatedHighFidelityState({
    required this.textureSession,
    required this.bundle,
    required this.shaderEffectsEnabled,
  });

  final PageflipBookIsolatedTextureSession? textureSession;
  final ArticlePageTextureBundle? bundle;
  final bool shaderEffectsEnabled;

  bool get usesMesh => textureSession?.isReadyForMesh ?? false;

  List<int> get prioritizedPageIndices {
    return textureSession?.binding.prioritizedPageIndices ?? const <int>[];
  }
}

class PageflipBookIsolatedHighFidelityFacade {
  const PageflipBookIsolatedHighFidelityFacade();

  PageflipBookIsolatedHighFidelityState resolve({
    required PageflipBookIsolatedScene scene,
    required Map<int, ArticlePageTextureSnapshot> snapshots,
    required PageflipBookIsolatedTextureSession? existingSession,
    required bool supportsAdvancedPageCurl,
    required bool freezeBinding,
  }) {
    final binding = scene.sheetBinding;
    if (binding == null) {
      return PageflipBookIsolatedHighFidelityState(
        textureSession: freezeBinding ? existingSession : null,
        bundle: freezeBinding ? existingSession?.bundle : null,
        shaderEffectsEnabled: supportsAdvancedPageCurl,
      );
    }
    final resolvedBundle = _bundleForBinding(
      binding,
      snapshots,
      fallback: _fallbackBundleForBinding(existingSession, binding),
    );
    final textureSession = resolvePageflipBookIsolatedTextureSession(
      existing: existingSession,
      binding: binding,
      resolvedBundle: resolvedBundle,
      freezeBinding: freezeBinding,
    );
    return PageflipBookIsolatedHighFidelityState(
      textureSession: textureSession,
      bundle: textureSession?.bundle,
      shaderEffectsEnabled: supportsAdvancedPageCurl,
    );
  }

  ArticlePageTextureBundle? _fallbackBundleForBinding(
    PageflipBookIsolatedTextureSession? session,
    PageflipBookIsolatedSheetBinding? binding,
  ) {
    if (session == null || binding == null) {
      return null;
    }
    return session.binding.matches(binding) ? session.bundle : null;
  }

  ArticlePageTextureBundle? _bundleForBinding(
    PageflipBookIsolatedSheetBinding? binding,
    Map<int, ArticlePageTextureSnapshot> snapshots, {
    ArticlePageTextureBundle? fallback,
  }) {
    if (binding == null) {
      return null;
    }
    final recto = snapshots[binding.rectoPageIndex];
    final verso = snapshots[binding.versoPageIndex];
    final bottom = snapshots[binding.bottomPageIndex];
    if (recto == null || verso == null || bottom == null) {
      return fallback;
    }
    return ArticlePageTextureBundle(recto: recto, verso: verso, bottom: bottom);
  }
}
