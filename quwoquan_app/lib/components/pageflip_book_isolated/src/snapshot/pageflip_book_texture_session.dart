import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book_isolated/src/contracts/pageflip_book_contracts.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class PageflipBookIsolatedTextureSession {
  const PageflipBookIsolatedTextureSession({
    required this.binding,
    this.bundle,
  });

  final PageflipBookIsolatedSheetBinding binding;
  final ArticlePageTextureBundle? bundle;

  bool get isReadyForMesh => bundle != null;

  PageflipBookIsolatedTextureSession copyWith({
    PageflipBookIsolatedSheetBinding? binding,
    ArticlePageTextureBundle? bundle,
    bool keepExistingBundle = true,
  }) {
    return PageflipBookIsolatedTextureSession(
      binding: binding ?? this.binding,
      bundle: bundle ?? (keepExistingBundle ? this.bundle : null),
    );
  }
}

PageflipBookIsolatedTextureSession resolvePageflipBookIsolatedTextureSession({
  required PageflipBookIsolatedTextureSession? existing,
  required PageflipBookIsolatedSheetBinding binding,
  required ArticlePageTextureBundle? resolvedBundle,
  required bool freezeBinding,
}) {
  if (existing == null) {
    return PageflipBookIsolatedTextureSession(
      binding: binding,
      bundle: resolvedBundle,
    );
  }
  if (!existing.binding.matches(binding) && freezeBinding) {
    return existing;
  }
  if (!existing.binding.matches(binding)) {
    return PageflipBookIsolatedTextureSession(
      binding: binding,
      bundle: resolvedBundle,
    );
  }
  return existing.copyWith(bundle: resolvedBundle);
}
