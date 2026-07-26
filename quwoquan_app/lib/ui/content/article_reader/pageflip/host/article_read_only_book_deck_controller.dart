part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckControllerSession
    on _ArticleReadOnlyBookDeckState {
  void _configurePageFlipController(Size stageSize) {
    if (_deck.pages.isEmpty) {
      _pageFlipController = null;
      _pageSurfaceCache.clear();
      _cachedSurfaceSize = null;
      return;
    }
    final pageSize = _resolvePageSizeForStage(stageSize);
    if (_cachedSurfaceSize != pageSize) {
      _cachedSurfaceSize = pageSize;
      _pageSurfaceCache.clear();
      _clearPageTextureSnapshots();
    }
    final layout = computeStPageFlipLayout(
      viewportSize: stageSize,
      pageWidth: pageSize.width,
      pageHeight: pageSize.height,
      usePortrait: true,
    );
    final spreadModel = StPageFlipSpreadModel(
      pageCount: _deck.pages.length,
      showCover: false,
      hardPagePolicy: StPageFlipHardPagePolicy.none,
    );
    if (_pageFlipController == null) {
      _pageFlipController = StPageFlipController(
        spreadModel: spreadModel,
        layout: layout,
        initialPage: _currentPage,
      );
      return;
    }
    _pageFlipController!.updateConfiguration(
      spreadModel: spreadModel,
      layout: layout,
      currentPage: _currentPage,
    );
  }

  ArticlePageTextureBinding? _textureBindingForScene(StPageFlipScene scene) {
    return resolveArticlePageTextureBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      bottomPageIndex: scene.bottomPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  ArticleBackwardPageSurfaceBinding? _backwardSurfaceBindingForScene(
    StPageFlipScene scene,
  ) {
    return resolveArticleBackwardPageSurfaceBinding(
      direction: scene.direction,
      flippingPageIndex: scene.flippingPageIndex,
      currentPageIndex: scene.currentPageIndex,
    );
  }

  ArticlePageTextureSnapshot? _validBackPageTextureSnapshotForIndex(
    int pageIndex, {
    required Size expectedSize,
  }) {
    if (!_allowsBackTextureForActiveSession(pageIndex)) {
      _queuePageTextureCaptureIndices(<int>[pageIndex], prioritize: true);
      return null;
    }
    final snapshot = _pageTextureSnapshots[pageIndex];
    if (snapshot == null) {
      _queuePageTextureCaptureIndices(<int>[pageIndex], prioritize: true);
      return null;
    }
    if (snapshot.matchesLogicalSize(expectedSize) &&
        snapshot.semanticSurfaceKind == ArticlePageSurfaceKind.back.name) {
      return snapshot;
    }
    final retired = _pageTextureSnapshots.remove(pageIndex);
    if (retired != null) {
      _retiredTextureSnapshots.add(retired);
    }
    _queuePageTextureCaptureIndices(<int>[pageIndex], prioritize: true);
    return null;
  }

  ArticlePageTextureSnapshot? _peekBackPageTextureSnapshotForIndex(
    int pageIndex, {
    required Size expectedSize,
  }) {
    final snapshot = _pageTextureSnapshots[pageIndex];
    if (snapshot == null) {
      return null;
    }
    if (!snapshot.matchesLogicalSize(expectedSize)) {
      return null;
    }
    return snapshot.semanticSurfaceKind == ArticlePageSurfaceKind.back.name
        ? snapshot
        : null;
  }

  void _queueStaticTextureSnapshots() {
    _queuePageTextureCaptureIndices(<int>[
      _currentPage,
      _currentPage - 1,
      _currentPage + 1,
    ]);
  }

  int? _backTexturePageIndexForDirection(StPageFlipDirection direction) {
    if (direction != StPageFlipDirection.back) {
      return null;
    }
    final pageIndex = _currentPage - 1;
    if (pageIndex < 0 || pageIndex >= _deck.pages.length) {
      return null;
    }
    return pageIndex;
  }

  bool _ensureBackTextureReadyForDirection(
    StPageFlipDirection direction, {
    bool blockCurrentGesture = false,
  }) {
    final pageIndex = _backTexturePageIndexForDirection(direction);
    final pageSize = _cachedSurfaceSize;
    if (pageIndex == null || pageSize == null) {
      return true;
    }
    final snapshot = _peekBackPageTextureSnapshotForIndex(
      pageIndex,
      expectedSize: pageSize,
    );
    if (snapshot != null) {
      return true;
    }
    if (blockCurrentGesture) {
      _textureWarmupBlockedGesture = true;
    }
    final queued = _queuePageTextureCaptureIndices(<int>[
      pageIndex,
    ], prioritize: true);
    if (queued && _isMounted) {
      _setDeckState(() {});
    }
    return false;
  }

  void _startPageFlipTextureSession(StPageFlipDirection direction) {
    final pageIndex = _backTexturePageIndexForDirection(direction);
    final pageSize = _cachedSurfaceSize;
    if (pageIndex == null || pageSize == null) {
      _activeBackTexturePageIndices = null;
      return;
    }
    final snapshot = _peekBackPageTextureSnapshotForIndex(
      pageIndex,
      expectedSize: pageSize,
    );
    _activeBackTexturePageIndices = snapshot == null
        ? <int>{}
        : <int>{pageIndex};
  }

  void _clearPageFlipTextureSession() {
    _activeBackTexturePageIndices = null;
  }

  bool _allowsBackTextureForActiveSession(int pageIndex) {
    final activeBackTexturePageIndices = _activeBackTexturePageIndices;
    return activeBackTexturePageIndices == null ||
        activeBackTexturePageIndices.contains(pageIndex);
  }

  bool _queuePageTextureCaptureIndices(
    Iterable<int> pageIndices, {
    bool prioritize = false,
  }) {
    var added = false;
    for (final pageIndex in pageIndices) {
      if (pageIndex < 0 || pageIndex >= _deck.pages.length) {
        continue;
      }
      final hasValidSnapshot = _pageTextureSnapshots.containsKey(pageIndex);
      if (hasValidSnapshot && !prioritize) {
        continue;
      }
      final alreadyPending = _pendingTextureCaptureIndices.contains(pageIndex);
      if (prioritize && alreadyPending) {
        _pendingTextureCaptureIndices.remove(pageIndex);
      }
      if (!alreadyPending || prioritize) {
        if (prioritize) {
          _pendingTextureCaptureIndices.addFirst(pageIndex);
        } else {
          _pendingTextureCaptureIndices.addLast(pageIndex);
        }
        added = true;
      }
      _textureCaptureBoundaryKeys.putIfAbsent(
        pageIndex,
        () => GlobalKey(debugLabel: 'article_reader_texture_$pageIndex'),
      );
    }
    if (added) {
      _schedulePageTextureCapture();
    }
    return added;
  }
}
