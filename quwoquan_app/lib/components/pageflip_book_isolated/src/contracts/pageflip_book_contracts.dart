import 'package:flutter/widgets.dart';

enum PageflipBookIsolatedDirection { forward, backward }

extension PageflipBookIsolatedDirectionX on PageflipBookIsolatedDirection {
  bool get isForward => this == PageflipBookIsolatedDirection.forward;
}

enum PageflipBookIsolatedCorner { top, bottom }

typedef PageflipBookIsolatedPageBuilder =
    Widget Function(BuildContext context, int pageIndex, Size pageSize);

@immutable
class PageflipBookIsolatedSheetBinding {
  const PageflipBookIsolatedSheetBinding({
    required this.direction,
    required this.rectoPageIndex,
    required this.versoPageIndex,
    required this.bottomPageIndex,
  });

  final PageflipBookIsolatedDirection direction;
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

  Set<int> get requiredPageIndices => Set<int>.unmodifiable(<int>{
    rectoPageIndex,
    versoPageIndex,
    bottomPageIndex,
  });

  bool matches(PageflipBookIsolatedSheetBinding other) {
    return direction == other.direction &&
        rectoPageIndex == other.rectoPageIndex &&
        versoPageIndex == other.versoPageIndex &&
        bottomPageIndex == other.bottomPageIndex;
  }
}

abstract final class PageflipBookIsolatedTestKeys {
  static const stage = ValueKey<String>('pageflip_book_isolated.stage');
  static const meshLayer = ValueKey<String>(
    'pageflip_book_isolated.mesh_layer',
  );
  static const hotzoneLeft = ValueKey<String>(
    'pageflip_book_isolated.hotzone_left',
  );
  static const hotzoneRight = ValueKey<String>(
    'pageflip_book_isolated.hotzone_right',
  );
  static const staticPage = ValueKey<String>(
    'pageflip_book_isolated.static_page',
  );
  static const meshRenderer = ValueKey<String>(
    'pageflip_book_isolated.mesh_renderer',
  );
}
