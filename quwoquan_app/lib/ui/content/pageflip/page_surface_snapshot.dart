import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ArticlePageTextureSnapshot {
  const ArticlePageTextureSnapshot({
    required this.image,
    required this.logicalSize,
    required this.pixelRatio,
  });

  final ui.Image image;
  final Size logicalSize;
  final double pixelRatio;

  double get pixelWidthPerLogical {
    if (logicalSize.width <= 0) {
      return 1;
    }
    return image.width / logicalSize.width;
  }

  double get pixelHeightPerLogical {
    if (logicalSize.height <= 0) {
      return 1;
    }
    return image.height / logicalSize.height;
  }

  void dispose() {
    image.dispose();
  }
}

@immutable
class ArticlePageTextureBundle {
  const ArticlePageTextureBundle({
    required this.recto,
    required this.verso,
    required this.bottom,
  });

  final ArticlePageTextureSnapshot recto;
  final ArticlePageTextureSnapshot verso;
  final ArticlePageTextureSnapshot bottom;
}

@immutable
class ArticlePageTextureBinding {
  const ArticlePageTextureBinding({
    required this.direction,
    required this.rectoPageIndex,
    required this.versoPageIndex,
    required this.bottomPageIndex,
  });

  final StPageFlipDirection direction;
  final int rectoPageIndex;
  final int versoPageIndex;
  final int bottomPageIndex;

  List<int> get prioritizedPageIndices {
    final indices = <int>[];
    void addUnique(int index) {
      if (!indices.contains(index)) {
        indices.add(index);
      }
    }

    addUnique(rectoPageIndex);
    addUnique(versoPageIndex);
    addUnique(bottomPageIndex);
    return indices;
  }

  Set<int> get requiredPageIndices => <int>{
    rectoPageIndex,
    versoPageIndex,
    bottomPageIndex,
  };

  bool matches(ArticlePageTextureBinding other) {
    return direction == other.direction &&
        rectoPageIndex == other.rectoPageIndex &&
        versoPageIndex == other.versoPageIndex &&
        bottomPageIndex == other.bottomPageIndex;
  }
}

@immutable
class ArticlePageTextureSession {
  const ArticlePageTextureSession({
    required this.binding,
    required this.preferHighFidelity,
    this.bundle,
  });

  final ArticlePageTextureBinding binding;
  final bool preferHighFidelity;
  final ArticlePageTextureBundle? bundle;

  ArticlePageTextureSession copyWith({
    ArticlePageTextureBinding? binding,
    bool? preferHighFidelity,
    ArticlePageTextureBundle? bundle,
    bool keepExistingBundle = true,
  }) {
    return ArticlePageTextureSession(
      binding: binding ?? this.binding,
      preferHighFidelity: preferHighFidelity ?? this.preferHighFidelity,
      bundle: bundle ?? (keepExistingBundle ? this.bundle : null),
    );
  }
}

ArticlePageTextureSession? resolveArticlePageTextureSession({
  required ArticlePageTextureSession? existing,
  required ArticlePageTextureBinding? binding,
  required ArticlePageTextureBundle? resolvedBundle,
  required bool supportsHighFidelity,
  required bool freezeBinding,
}) {
  if (binding == null) {
    return freezeBinding ? existing : null;
  }

  if (existing == null) {
    final preferHighFidelity = supportsHighFidelity && resolvedBundle != null;
    return ArticlePageTextureSession(
      binding: binding,
      preferHighFidelity: preferHighFidelity,
      bundle: resolvedBundle,
    );
  }

  final sameBinding = existing.binding.matches(binding);
  if (!sameBinding && freezeBinding) {
    final preservedBundle = existing.bundle;
    return ArticlePageTextureSession(
      binding: existing.binding,
      preferHighFidelity: existing.preferHighFidelity,
      bundle: preservedBundle,
    );
  }

  if (!sameBinding) {
    final preferHighFidelity = supportsHighFidelity && resolvedBundle != null;
    return ArticlePageTextureSession(
      binding: binding,
      preferHighFidelity: preferHighFidelity,
      bundle: resolvedBundle,
    );
  }

  final stickyBundle = resolvedBundle ?? existing.bundle;
  final preferHighFidelity =
      existing.preferHighFidelity ||
      (supportsHighFidelity && stickyBundle != null);
  return ArticlePageTextureSession(
    binding: existing.binding,
    preferHighFidelity: preferHighFidelity,
    bundle: stickyBundle,
  );
}

ArticlePageTextureBinding? resolveArticlePageTextureBinding({
  required StPageFlipDirection? direction,
  required int? flippingPageIndex,
  required int? bottomPageIndex,
  required int currentPageIndex,
}) {
  if (direction == null || flippingPageIndex == null) {
    return null;
  }
  if (direction == StPageFlipDirection.forward) {
    if (bottomPageIndex == null) {
      return null;
    }
    return ArticlePageTextureBinding(
      direction: direction,
      rectoPageIndex: flippingPageIndex,
      versoPageIndex: bottomPageIndex,
      bottomPageIndex: bottomPageIndex,
    );
  }
  return ArticlePageTextureBinding(
    direction: direction,
    rectoPageIndex: flippingPageIndex,
    versoPageIndex: currentPageIndex,
    bottomPageIndex: currentPageIndex,
  );
}
