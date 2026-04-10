import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/components/pageflip_book/src/contracts/pageflip_book_contracts.dart';

enum PageflipBookSurfaceRole {
  coveredCurrent,
  turningFront,
  turningBack,
  nextUnder,
  staticLeft,
  staticRight,
}

@immutable
class PageflipBookSurfaceRoleBinding {
  const PageflipBookSurfaceRoleBinding({
    required this.roles,
  }) : assert(roles.length > 0);

  final Map<PageflipBookSurfaceRole, int> roles;

  int? pageIndexFor(PageflipBookSurfaceRole role) => roles[role];

  List<int> get prioritizedPageIndices {
    final indices = <int>[];
    for (final index in roles.values) {
      if (!indices.contains(index)) {
        indices.add(index);
      }
    }
    return List<int>.unmodifiable(indices);
  }

  Set<int> get requiredPageIndices => Set<int>.unmodifiable(roles.values.toSet());
}

@immutable
class PageflipBookSheetBinding {
  const PageflipBookSheetBinding({
    required this.direction,
    required this.rectoPageIndex,
    required this.versoPageIndex,
    required this.bottomPageIndex,
  });

  final PageflipBookDirection direction;
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
    return List<int>.unmodifiable(indices);
  }

  Set<int> get requiredPageIndices =>
      Set<int>.unmodifiable(<int>{rectoPageIndex, versoPageIndex, bottomPageIndex});
}

@immutable
class PageflipBookSceneDescriptor {
  const PageflipBookSceneDescriptor({
    required this.window,
    required this.state,
    this.direction,
    this.corner,
    this.surfaceBinding,
    this.sheetBinding,
  });

  final PageflipBookWindow window;
  final PageflipBookState state;
  final PageflipBookDirection? direction;
  final PageflipBookCorner? corner;
  final PageflipBookSurfaceRoleBinding? surfaceBinding;
  final PageflipBookSheetBinding? sheetBinding;
}
