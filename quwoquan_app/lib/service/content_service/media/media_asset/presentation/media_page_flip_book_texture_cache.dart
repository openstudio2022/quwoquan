part of 'media_page_flip_book.dart';

@immutable
class _MediaPageTextureKey {
  const _MediaPageTextureKey(this.pageIndex, this.face);

  final int pageIndex;
  final MediaPageFlipSurfaceFace face;

  @override
  bool operator ==(Object other) {
    return other is _MediaPageTextureKey &&
        other.pageIndex == pageIndex &&
        other.face == face;
  }

  @override
  int get hashCode => Object.hash(pageIndex, face);
}

@immutable
class _MediaPageTextureRef {
  const _MediaPageTextureRef({required this.pageIndex, required this.face});

  final int pageIndex;
  final MediaPageFlipSurfaceFace face;
}

@immutable
class _MediaPageTextureBinding {
  const _MediaPageTextureBinding({
    required this.direction,
    required this.recto,
    required this.verso,
    required this.bottom,
  });

  final StPageFlipDirection direction;
  final _MediaPageTextureRef recto;
  final _MediaPageTextureRef verso;
  final _MediaPageTextureRef bottom;

  List<int> get prioritizedPageIndices {
    final indices = <int>[];
    void addUnique(int index) {
      if (!indices.contains(index)) {
        indices.add(index);
      }
    }

    addUnique(recto.pageIndex);
    addUnique(verso.pageIndex);
    addUnique(bottom.pageIndex);
    return indices;
  }

  Set<int> get requiredPageIndices => <int>{
    recto.pageIndex,
    verso.pageIndex,
    bottom.pageIndex,
  };
}

extension _MediaPageFlipBookStateTextureCache on _MediaPageFlipBookState {
  Widget _buildCaptureLayer(
    BuildContext context,
    Size pageSize,
    Size stageSize,
  ) {
    final pages = _pendingCaptureIndices.take(3).toList(growable: false);
    if (pages.isEmpty) {
      return const SizedBox.shrink();
    }
    return Transform.translate(
      offset: Offset(
        stageSize.width + pageSize.width + AppSpacing.buttonHeight,
        0,
      ),
      child: _StableMediaPageCaptureLayer(
        capturePages: pages,
        pageSize: pageSize,
        boundaryKeys: _captureBoundaryKeys,
        buildPage: (index) => widget.pageBuilder(context, index),
      ),
    );
  }

  _MediaPageTextureBinding? _textureBindingForScene(StPageFlipScene scene) {
    final direction = scene.direction;
    if (direction == null || scene.flippingPageIndex == null) {
      return null;
    }
    if (direction == StPageFlipDirection.forward) {
      final targetPageIndex = scene.bottomPageIndex;
      if (targetPageIndex == null) {
        return null;
      }
      return _MediaPageTextureBinding(
        direction: direction,
        recto: _MediaPageTextureRef(
          pageIndex: scene.currentPageIndex,
          face: MediaPageFlipSurfaceFace.front,
        ),
        verso: _MediaPageTextureRef(
          pageIndex: scene.currentPageIndex,
          face: MediaPageFlipSurfaceFace.back,
        ),
        bottom: _MediaPageTextureRef(
          pageIndex: targetPageIndex,
          face: MediaPageFlipSurfaceFace.front,
        ),
      );
    }
    return _MediaPageTextureBinding(
      direction: direction,
      recto: _MediaPageTextureRef(
        pageIndex: scene.flippingPageIndex!,
        face: MediaPageFlipSurfaceFace.front,
      ),
      verso: _MediaPageTextureRef(
        pageIndex: scene.flippingPageIndex!,
        face: MediaPageFlipSurfaceFace.back,
      ),
      bottom: _MediaPageTextureRef(
        pageIndex: scene.currentPageIndex,
        face: MediaPageFlipSurfaceFace.front,
      ),
    );
  }

  bool _shouldCaptureTexturesForScene(StPageFlipScene scene) {
    return scene.renderFrame != null || _activePlan != null || _dragActive;
  }

  ArticlePageTextureBundle? _textureBundleForScene(
    StPageFlipScene scene,
    _MediaPageTextureBinding? binding,
  ) {
    if (binding == null) {
      return null;
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final recto = _validSnapshotForRef(binding.recto, expectedSize: pageSize);
    final verso = _validSnapshotForRef(binding.verso, expectedSize: pageSize);
    final bottom = _validSnapshotForRef(binding.bottom, expectedSize: pageSize);
    if (recto == null || verso == null || bottom == null) {
      return null;
    }
    return ArticlePageTextureBundle(recto: recto, verso: verso, bottom: bottom);
  }

  ArticlePageTextureSnapshot? _validSnapshotForRef(
    _MediaPageTextureRef ref, {
    required Size expectedSize,
  }) {
    final key = _MediaPageTextureKey(ref.pageIndex, ref.face);
    var snapshot = _pageSnapshots[key];
    if (widget.textureSnapshotBuilder == null &&
        ref.face == MediaPageFlipSurfaceFace.back) {
      snapshot ??=
          _pageSnapshots[_MediaPageTextureKey(
            ref.pageIndex,
            MediaPageFlipSurfaceFace.front,
          )];
    }
    if (widget.textureSnapshotBuilder == null &&
        !_isPageTextureReady(ref.pageIndex)) {
      _queueTextureIndices(<int>[ref.pageIndex], prioritize: true);
      return null;
    }
    if (snapshot == null) {
      _queueTextureIndices(<int>[ref.pageIndex], prioritize: true);
      return null;
    }
    if (snapshot.matchesLogicalSize(expectedSize)) {
      return snapshot;
    }
    _retireSnapshotForKey(key);
    _queueTextureIndices(<int>[ref.pageIndex], prioritize: true);
    return null;
  }

  bool _isPageTextureReady(int index) {
    if (widget.textureSnapshotBuilder != null) {
      return true;
    }
    final predicate = widget.isPageTextureReady;
    return predicate == null || predicate(index);
  }

  void _refreshDirectTextureSnapshots() {
    if (_dragActive || _activePlan != null) {
      _deferredDirectTextureRefresh = true;
      return;
    }
    _deferredDirectTextureRefresh = false;
    _clearAllSnapshots();
    _queueStaticTextureSnapshots();
  }

  void _applyDeferredDirectTextureRefreshIfIdle() {
    if (!_deferredDirectTextureRefresh ||
        widget.textureSnapshotBuilder == null ||
        _dragActive ||
        _activePlan != null) {
      return;
    }
    _refreshDirectTextureSnapshots();
  }

  void _queueSceneTextureWindow(
    StPageFlipScene scene,
    _MediaPageTextureBinding? binding,
  ) {
    _queueTextureIndices(
      binding?.prioritizedPageIndices ??
          <int>[
            scene.currentPageIndex,
            scene.currentPageIndex + 1,
            scene.currentPageIndex - 1,
          ],
    );
  }

  void _queueStaticTextureSnapshots() {
    _queueTextureIndices(<int>[
      _currentPage,
      _currentPage - 1,
      _currentPage + 1,
    ]);
  }

  void _queueTextureIndices(Iterable<int> indices, {bool prioritize = false}) {
    var added = false;
    final ordered = indices.toList(growable: false);
    final iterable = prioritize ? ordered.reversed : ordered;
    for (final index in iterable) {
      if (index < 0 || index >= widget.pageCount) {
        continue;
      }
      if (_hasSnapshotForIndex(index)) {
        continue;
      }
      final alreadyPending = _pendingCaptureIndices.contains(index);
      if (alreadyPending && !prioritize) {
        continue;
      }
      _pendingCaptureIndices.remove(index);
      if (prioritize) {
        _pendingCaptureIndices.addFirst(index);
      } else {
        _pendingCaptureIndices.addLast(index);
      }
      if (widget.textureSnapshotBuilder == null) {
        _captureBoundaryKeys.putIfAbsent(
          index,
          () => GlobalKey(debugLabel: 'media_pageflip_capture_$index'),
        );
      }
      added = true;
    }
    if (added) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) {
          _rebuild();
        }
      });
      _scheduleCapture();
    }
  }

  bool _hasSnapshotForIndex(int index) {
    final front = _pageSnapshots.containsKey(
      _MediaPageTextureKey(index, MediaPageFlipSurfaceFace.front),
    );
    if (widget.textureSnapshotBuilder == null) {
      return front;
    }
    return front &&
        _pageSnapshots.containsKey(
          _MediaPageTextureKey(index, MediaPageFlipSurfaceFace.back),
        );
  }

  void _retireSnapshotForKey(_MediaPageTextureKey key) {
    final retired = _pageSnapshots.remove(key);
    if (retired != null) {
      _retiredSnapshots.add(retired);
    }
  }

  void _storeTexturePair(int index, MediaPageFlipTexturePair pair) {
    final frontKey = _MediaPageTextureKey(
      index,
      MediaPageFlipSurfaceFace.front,
    );
    final backKey = _MediaPageTextureKey(index, MediaPageFlipSurfaceFace.back);
    _retireSnapshotForKey(frontKey);
    _retireSnapshotForKey(backKey);
    _pageSnapshots[frontKey] = pair.front;
    _pageSnapshots[backKey] = pair.back;
  }

  void _scheduleCapture() {
    if (_captureScheduled ||
        _captureInFlight ||
        _pendingCaptureIndices.isEmpty ||
        !mounted ||
        _lastPageSize == null) {
      return;
    }
    _captureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _captureScheduled = false;
      _captureInFlight = true;
      unawaited(_capturePendingTextures());
    });
  }

  double _capturePixelRatio(BuildContext context) {
    final view = View.maybeOf(context);
    final ratio =
        view?.devicePixelRatio ??
        MediaQuery.maybeOf(context)?.devicePixelRatio ??
        1.0;
    return ratio.clamp(1.0, double.infinity).toDouble();
  }

  Future<void> _capturePendingTextures() async {
    if (!mounted || _pendingCaptureIndices.isEmpty) {
      _captureInFlight = false;
      return;
    }
    final pendingNow = _pendingCaptureIndices.take(3).toList(growable: false);
    var capturedAny = false;
    final directTextureBuilder = widget.textureSnapshotBuilder;
    if (directTextureBuilder != null) {
      final expectedGeneration = _viewportCaptureGeneration;
      final expectedPageSize = _lastPageSize;
      if (expectedPageSize == null) {
        _captureInFlight = false;
        return;
      }
      final pixelRatio = _capturePixelRatio(context);
      try {
        for (final index in pendingNow) {
          final pair = await directTextureBuilder(
            context,
            index,
            expectedPageSize,
            pixelRatio,
          );
          if (!mounted || pair == null) {
            pair?.dispose();
            _pendingCaptureIndices.remove(index);
            if (!mounted) {
              return;
            }
            continue;
          }
          final stale =
              expectedGeneration != _viewportCaptureGeneration ||
              !pair.matchesLogicalSize(expectedPageSize);
          if (stale) {
            pair.dispose();
            _pendingCaptureIndices.remove(index);
          } else {
            _storeTexturePair(index, pair);
            _pendingCaptureIndices.remove(index);
            capturedAny = true;
          }
        }
      } catch (_) {
        // Direct media texture construction may fail while the image is still
        // warming; release it so the next ready/gesture signal can requeue
        // without spinning a frame-by-frame retry loop.
        for (final index in pendingNow) {
          _pendingCaptureIndices.remove(index);
        }
      } finally {
        _captureInFlight = false;
      }
      if (capturedAny && mounted) {
        _rebuild();
      }
      if (mounted && _pendingCaptureIndices.isNotEmpty) {
        _scheduleCapture();
      }
      return;
    }
    try {
      for (final index in pendingNow) {
        if (!mounted) {
          break;
        }
        if (!_isPageTextureReady(index)) {
          continue;
        }
        final boundaryKey = _captureBoundaryKeys[index];
        final boundaryContext = boundaryKey?.currentContext;
        if (boundaryContext == null || !boundaryContext.mounted) {
          continue;
        }
        final renderObject = boundaryContext.findRenderObject();
        if (renderObject is! RenderRepaintBoundary ||
            !renderObject.attached ||
            !renderObject.hasSize ||
            renderObject.size.isEmpty ||
            renderObject.debugNeedsPaint) {
          continue;
        }
        final expectedGeneration = _viewportCaptureGeneration;
        final expectedPageSize = _lastPageSize;
        final logicalSize = renderObject.size;
        final pixelRatio = _capturePixelRatio(boundaryContext);
        try {
          final image = await renderObject.toImage(pixelRatio: pixelRatio);
          if (!mounted) {
            image.dispose();
            return;
          }
          final stale =
              expectedPageSize == null ||
              expectedGeneration != _viewportCaptureGeneration ||
              !_sizeEquals(expectedPageSize, logicalSize) ||
              !_sizeEquals(renderObject.size, logicalSize) ||
              !identical(_captureBoundaryKeys[index], boundaryKey);
          if (stale) {
            image.dispose();
            continue;
          }
          final frontKey = _MediaPageTextureKey(
            index,
            MediaPageFlipSurfaceFace.front,
          );
          _retireSnapshotForKey(frontKey);
          _pageSnapshots[frontKey] = ArticlePageTextureSnapshot(
            image: image,
            logicalSize: logicalSize,
            pixelRatio: pixelRatio,
          );
          _pendingCaptureIndices.remove(index);
          capturedAny = true;
        } catch (_) {
          // Capture may transiently fail while the hidden surface is repainting.
        }
      }
    } finally {
      _captureInFlight = false;
    }
    if (capturedAny && mounted) {
      _rebuild();
    }
    if (mounted &&
        _pendingCaptureIndices.isNotEmpty &&
        _pendingCaptureIndices.any(_isPageTextureReady)) {
      _scheduleCapture();
    }
  }

  void _clearAllSnapshots() {
    _retiredSnapshots.addAll(_pageSnapshots.values);
    _pageSnapshots.clear();
    _pendingCaptureIndices.clear();
    _captureBoundaryKeys.clear();
  }

  void _disposeRetiredSnapshots() {
    for (final snapshot in _retiredSnapshots) {
      snapshot.dispose();
    }
    _retiredSnapshots.clear();
  }

  bool _sizeEquals(Size? a, Size b) {
    if (a == null) {
      return false;
    }
    return (a.width - b.width).abs() < 0.01 &&
        (a.height - b.height).abs() < 0.01;
  }
}

class _StableMediaPageCaptureLayer extends StatefulWidget {
  const _StableMediaPageCaptureLayer({
    required this.capturePages,
    required this.pageSize,
    required this.boundaryKeys,
    required this.buildPage,
  });

  final List<int> capturePages;
  final Size pageSize;
  final Map<int, GlobalKey> boundaryKeys;
  final Widget Function(int index) buildPage;

  @override
  State<_StableMediaPageCaptureLayer> createState() =>
      _StableMediaPageCaptureLayerState();
}

class _StableMediaPageCaptureLayerState
    extends State<_StableMediaPageCaptureLayer> {
  late List<int> _capturePages;
  late Map<int, Widget> _cachedWidgets;

  @override
  void initState() {
    super.initState();
    _capturePages = List<int>.of(widget.capturePages);
    _rebuildCache();
  }

  @override
  void didUpdateWidget(covariant _StableMediaPageCaptureLayer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!listEquals(widget.capturePages, _capturePages) ||
        widget.pageSize != oldWidget.pageSize) {
      _capturePages = List<int>.of(widget.capturePages);
      _rebuildCache();
    }
  }

  void _rebuildCache() {
    _cachedWidgets = <int, Widget>{
      for (final index in _capturePages) index: widget.buildPage(index),
    };
  }

  @override
  Widget build(BuildContext context) {
    final column = Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _capturePages
          .map(
            (index) => RepaintBoundary(
              key: widget.boundaryKeys[index],
              child: SizedBox(
                width: widget.pageSize.width,
                height: widget.pageSize.height,
                child: _cachedWidgets[index] ?? const SizedBox.shrink(),
              ),
            ),
          )
          .toList(growable: false),
    );
    return Align(
      alignment: Alignment.topLeft,
      child: OverflowBox(
        alignment: Alignment.topLeft,
        minWidth: widget.pageSize.width,
        maxWidth: widget.pageSize.width,
        minHeight: widget.pageSize.height,
        maxHeight: widget.pageSize.height * _capturePages.length,
        child: column,
      ),
    );
  }
}
