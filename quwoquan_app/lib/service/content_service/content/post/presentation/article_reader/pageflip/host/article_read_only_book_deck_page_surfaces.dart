part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckPageSurfaces
    on _ArticleReadOnlyBookDeckState {
  Rect _pageRectForStage(Size stageSize) {
    final availableWidth = math.max(
      1.0,
      stageSize.width - _deck.pagePadding.horizontal,
    );
    final availableHeight = math.max(
      1.0,
      stageSize.height - _deck.pagePadding.vertical,
    );
    if (_usesImmersivePresentation) {
      return Rect.fromLTWH(
        _deck.pagePadding.left,
        _deck.pagePadding.top,
        availableWidth,
        availableHeight,
      );
    }
    final pageWidth = math.min(
      availableWidth,
      availableHeight * _deck.metrics.aspectRatio,
    );
    final pageHeight = pageWidth / _deck.metrics.aspectRatio;
    final left = (stageSize.width - pageWidth) / 2;
    final minTop = _deck.pagePadding.top;
    final maxTop = math.max(
      minTop,
      stageSize.height - _deck.pagePadding.bottom - pageHeight,
    );
    final preferredTop = _usesImmersivePresentation
        ? minTop
        : (stageSize.height - pageHeight) / 2;
    final top = preferredTop.clamp(minTop, maxTop).toDouble();
    return Rect.fromLTWH(left, top, pageWidth, pageHeight);
  }

  Widget _buildPageSurfaceWidget(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    final debugSurface = _deck.debugPageSurfaceBuilder?.call(
      context,
      index,
      pageSize,
    );
    if (debugSurface != null) {
      return SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: debugSurface,
      );
    }
    final page = _deck.pages[index];
    return ArticlePageShell(
      key: ValueKey<String>('article-reader-page-surface-$index'),
      template: _deck.template,
      fontPreset: _deck.fontPreset,
      pageIndex: index,
      totalPages: _deck.pages.length,
      aspectRatio: _deck.metrics.aspectRatio,
      outerPadding: _deck.metrics.outerPadding,
      contentPadding: _deck.metrics.contentPadding,
      headerReservedHeight: _deck.metrics.headerReservedHeight,
      footerReservedHeight: _deck.metrics.footerReservedHeight,
      variant: _usesImmersivePresentation
          ? ArticlePageShellVariant.immersiveEdgeToEdge
          : ArticlePageShellVariant.readerSheet,
      showIndicator: false,
      headerLabel: _deck.headerLabel,
      footerLabel: _deck.showFooterPageLabel
          ? '${index + 1}/${_deck.pages.length}'
          : null,
      paperTexture: _deck.paperTexture,
      child: ArticlePageReadOnlyView(
        page: page,
        template: _deck.template,
        fontPreset: _deck.fontPreset,
        metrics: _deck.metrics,
        paperTexture: _deck.paperTexture,
        onEntityTap: _deck.onEntityTap,
        onImageTap: _deck.onImageTap,
      ),
    );
  }

  Widget _buildReaderPage(BuildContext context, int index, Size pageSize) {
    return SizedBox(
      width: pageSize.width,
      height: pageSize.height,
      child: RepaintBoundary(
        child: _buildPageSurfaceWidget(context, index, pageSize),
      ),
    );
  }

  Widget _buildMirroredReaderPage(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    return Transform.flip(
      flipX: true,
      child: SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: _buildPageSurfaceWidget(context, index, pageSize),
      ),
    );
  }

  Widget _buildPageTextureCaptureSurface(
    BuildContext context,
    int index,
    Size pageSize,
  ) {
    // BACK verso must capture the semantic back surface, not the front page
    // _deck. Otherwise the UV painter receives a recto snapshot and the fold
    // band looks like the page front.
    return _buildCachedPageSurface(
      context,
      index,
      pageSize,
      kind: ArticlePageSurfaceKind.back,
    );
  }

  Widget _buildPageTextureCaptureLayer(Size pageSize) {
    final pendingPages = _pendingTextureCaptureIndices
        .take(3)
        .toList(growable: false);
    if (pendingPages.isEmpty) {
      return const SizedBox.shrink();
    }
    return IgnorePointer(
      child: ExcludeSemantics(
        child: ArticleReaderStableTextureCaptureLayer(
          capturePages: pendingPages,
          pageSize: pageSize,
          boundaryKeys: _textureCaptureBoundaryKeys,
          buildPage: (pageIndex) =>
              _buildPageTextureCaptureSurface(context, pageIndex, pageSize),
          useOffscreenPaint: true,
        ),
      ),
    );
  }

  void _schedulePageTextureCapture() {
    if (_textureCaptureScheduled ||
        _textureCaptureInFlight ||
        _pendingTextureCaptureIndices.isEmpty ||
        !_isMounted ||
        _cachedSurfaceSize == null) {
      return;
    }
    _textureCaptureScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _textureCaptureScheduled = false;
      _textureCaptureInFlight = true;
      unawaited(_capturePendingPageTextures());
    });
  }

  double _textureCapturePixelRatio(BuildContext context) {
    final view = View.maybeOf(context);
    final pixelRatio =
        view?.devicePixelRatio ??
        MediaQuery.maybeOf(context)?.devicePixelRatio ??
        1.0;
    return pixelRatio.clamp(1.0, double.infinity).toDouble();
  }

  Future<void> _capturePendingPageTextures() async {
    if (!_isMounted || _pendingTextureCaptureIndices.isEmpty) {
      _textureCaptureInFlight = false;
      return;
    }
    final pendingNow = _pendingTextureCaptureIndices
        .take(3)
        .toList(growable: false);
    var capturedAny = false;
    try {
      for (final pageIndex in pendingNow) {
        final boundaryKey = _textureCaptureBoundaryKeys[pageIndex];
        final boundaryContext = boundaryKey?.currentContext;
        if (boundaryContext == null || !boundaryContext.mounted) {
          continue;
        }
        RenderRepaintBoundary? boundary;
        try {
          final renderObject = boundaryContext.findRenderObject();
          if (renderObject is RenderRepaintBoundary) {
            boundary = renderObject;
          }
        } catch (_) {
          continue;
        }
        if (boundary == null ||
            !boundary.attached ||
            !boundary.hasSize ||
            boundary.size.isEmpty ||
            boundary.debugNeedsPaint) {
          continue;
        }
        final expectedPageSize = _cachedSurfaceSize;
        final logicalSize = boundary.size;
        final pixelRatio = _textureCapturePixelRatio(boundaryContext);
        try {
          final image = await boundary.toImage(pixelRatio: pixelRatio);
          if (!_isMounted) {
            image.dispose();
            return;
          }
          final isStaleCapture =
              expectedPageSize == null ||
              !_sameLogicalSize(expectedPageSize, logicalSize) ||
              !_sameLogicalSize(boundary.size, logicalSize) ||
              !identical(_textureCaptureBoundaryKeys[pageIndex], boundaryKey);
          if (isStaleCapture) {
            image.dispose();
            continue;
          }
          final retired = _pageTextureSnapshots.remove(pageIndex);
          if (retired != null) {
            _retiredTextureSnapshots.add(retired);
          }
          _pageTextureSnapshots[pageIndex] = ArticlePageTextureSnapshot(
            image: image,
            logicalSize: logicalSize,
            pixelRatio: pixelRatio,
            semanticSurfaceKind: ArticlePageSurfaceKind.back.name,
          );
          _pendingTextureCaptureIndices.remove(pageIndex);
          capturedAny = true;
        } catch (_) {
          // Hidden capture can miss a frame while the reader surface rebuilds.
        }
      }
    } finally {
      _textureCaptureInFlight = false;
    }
    if (capturedAny && _isMounted) {
      final hasVisibleTurnInProgress =
          _hasActivePageCurlAnimation || _pageFlipScene?.direction != null;
      if (!hasVisibleTurnInProgress) {
        _setDeckState(() {});
      }
      _disposeRetiredTextureSnapshots();
    }
    if (_pendingTextureCaptureIndices.isNotEmpty) {
      _schedulePageTextureCapture();
    }
  }

  bool _sameLogicalSize(Size a, Size b) {
    return (a.width - b.width).abs() < 0.01 &&
        (a.height - b.height).abs() < 0.01;
  }

  void _clearPageTextureSnapshots() {
    _retiredTextureSnapshots.addAll(_pageTextureSnapshots.values);
    _pageTextureSnapshots.clear();
    _pendingTextureCaptureIndices.clear();
    _textureCaptureBoundaryKeys.clear();
  }

  void _disposeRetiredTextureSnapshots() {
    for (final snapshot in _retiredTextureSnapshots) {
      snapshot.dispose();
    }
    _retiredTextureSnapshots.clear();
  }

  Widget _buildCachedPageSurface(
    BuildContext context,
    int pageIndex,
    Size pageSize, {
    required ArticlePageSurfaceKind kind,
  }) {
    final cacheKey =
        '${kind.name}:$pageIndex:${pageSize.width.toStringAsFixed(2)}:${pageSize.height.toStringAsFixed(2)}:${_deck.template.name}:${_deck.fontPreset.name}:${_deck.coverUrl.trim().isNotEmpty ? 1 : 0}:${_deck.headerLabel ?? ''}:${_deck.showFooterPageLabel ? 1 : 0}:${_deck.paperTexture?.name ?? 'none'}:${_deck.debugPageSurfaceBuilder == null ? 'normal' : 'debug'}:${_deck.debugBackPageSurfaceBuilder == null ? 'normalBack' : 'debugBack'}';
    return _pageSurfaceCache.putIfAbsent(cacheKey, () {
      switch (kind) {
        case ArticlePageSurfaceKind.front:
        case ArticlePageSurfaceKind.bottom:
          return _buildReaderPage(context, pageIndex, pageSize);
        case ArticlePageSurfaceKind.back:
          return _buildOpaqueBackPageSurface(
            context,
            pageIndex,
            pageSize,
            mirrorContent: true,
          );
      }
    });
  }

  Widget _buildOpaqueBackPageSurface(
    BuildContext context,
    int pageIndex,
    Size pageSize, {
    required bool mirrorContent,
    double contentOpacity = 0.46,
  }) {
    final debugSurface = _deck.debugBackPageSurfaceBuilder?.call(
      context,
      pageIndex,
      pageSize,
    );
    if (debugSurface != null) {
      final sizedDebugSurface = SizedBox(
        width: pageSize.width,
        height: pageSize.height,
        child: debugSurface,
      );
      return mirrorContent
          ? Transform.flip(flipX: true, child: sizedDebugSurface)
          : sizedDebugSurface;
    }
    final palette = _deck.paperTexture != null
        ? resolveArticlePaperPalette(context, _deck.paperTexture!)
        : resolveArticleTemplatePalette(context, _deck.template);
    return DecoratedBox(
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            Color.alphaBlend(
              palette.shadowColor.withValues(alpha: 0.08),
              palette.paperColor,
            ),
            palette.paperColor,
            Color.alphaBlend(
              palette.paperBorderColor.withValues(alpha: 0.18),
              palette.paperColor,
            ),
          ],
        ),
        border: Border.all(
          color: palette.paperBorderColor.withValues(alpha: 0.22),
          width: AppSpacing.hairline,
        ),
      ),
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          ColoredBox(color: palette.paperColor),
          IgnorePointer(
            child: Opacity(
              opacity: contentOpacity,
              child: mirrorContent
                  ? _buildMirroredReaderPage(context, pageIndex, pageSize)
                  : _buildReaderPage(context, pageIndex, pageSize),
            ),
          ),
          IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: <Color>[
                    palette.shadowColor.withValues(alpha: 0.10),
                    AppColors.transparent,
                    palette.shadowColor.withValues(alpha: 0.08),
                  ],
                  stops: const <double>[0.0, 0.58, 1.0],
                ),
              ),
            ),
          ),
          IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    AppColors.white.withValues(alpha: 0.04),
                    AppColors.transparent,
                    palette.shadowColor.withValues(alpha: 0.12),
                  ],
                  stops: const <double>[0.0, 0.42, 1.0],
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
