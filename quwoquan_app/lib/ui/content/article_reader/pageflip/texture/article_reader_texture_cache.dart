import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/page_surface_snapshot.dart';

@immutable
class ArticleReaderTextureWindow {
  const ArticleReaderTextureWindow({
    required this.binding,
    required this.availableSnapshotIndices,
    required this.pendingSnapshotIndices,
  });

  final ArticlePageTextureBinding? binding;
  final List<int> availableSnapshotIndices;
  final List<int> pendingSnapshotIndices;

  bool get hasResolvedBinding => binding != null;
}
