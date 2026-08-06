part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckSoftLayers on _ArticleReadOnlyBookDeckState {
  Widget _buildFlippingSurfaceOverlay({
    required ArticleTemplatePalette palette,
    required StPageFlipDirection direction,
    required double progress,
    required bool showBackside,
  }) {
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    final lift = Curves.easeOutCubic.transform(settledProgress);
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerRight;
    final shadowColor = palette.shadowColor.withValues(
      alpha: (showBackside ? 0.10 : 0.12) + (lift * 0.065),
    );
    final tunnelAlpha = (showBackside ? 0.07 : 0.08) + (lift * 0.05);
    final tunnelColor = AppColors.black.withValues(
      alpha: tunnelAlpha.clamp(0.0, 1.0).toDouble(),
    );
    final highlightColor = AppColors.white.withValues(
      alpha: (showBackside ? 0.04 : 0.14) + (lift * 0.035),
    );
    final edgeTintColor = showBackside
        ? palette.shadowColor.withValues(alpha: 0.04 + lift * 0.04)
        : palette.paperBorderColor.withValues(alpha: 0.08 + lift * 0.06);
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  AppColors.white.withValues(alpha: showBackside ? 0.04 : 0.16),
                  AppColors.transparent,
                  tunnelColor,
                ],
                stops: const <double>[0.0, 0.5, 1.0],
              ),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: edgeAlignment,
                end: oppositeEdge,
                colors: <Color>[
                  shadowColor,
                  edgeTintColor,
                  AppColors.transparent,
                ],
                stops: const <double>[0.0, 0.28, 0.9],
              ),
            ),
          ),
          Align(
            alignment: edgeAlignment,
            child: FractionallySizedBox(
              widthFactor: (showBackside ? 0.16 : 0.08) + (lift * 0.04),
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: edgeAlignment,
                    end: oppositeEdge,
                    colors: <Color>[highlightColor, AppColors.transparent],
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSoftFlippingPageSurface({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipDirection direction,
    required double progress,
    double visualAngle = 0,
    int? backFacePageIndex,
    ArticlePageBackwardLeafFrame? backwardLeafFrame,
    _PageLine? backwardFoldLine,
    _PageLine? backwardFreeEdgeLine,
    List<Offset> sheetLocalPolygon = const <Offset>[],
    List<Offset> sheetContentLocalPolygon = const <Offset>[],
    List<Offset> sheetAreaPolygon = const <Offset>[],
    List<Offset> sheetMaterialLocalPolygon = const <Offset>[],
  }) {
    final palette = resolveArticleTemplatePalette(context, _deck.template);
    if (direction == StPageFlipDirection.back && backwardLeafFrame != null) {
      return _buildBackwardSplitFlippingSurface(
        context: context,
        pageIndex: pageIndex,
        backFacePageIndex: backFacePageIndex ?? pageIndex,
        pageSize: pageSize,
        backwardLeafFrame: backwardLeafFrame,
        backwardFoldLine: backwardFoldLine,
        backwardFreeEdgeLine: backwardFreeEdgeLine,
        sheetContentLocalPolygon: sheetContentLocalPolygon,
        palette: palette,
        progress: progress,
      );
    }
    final showBackside = _shouldShowSoftFlippingBackside(
      direction: direction,
      visualAngle: visualAngle,
    );
    final facePageIndex = showBackside
        ? (backFacePageIndex ?? pageIndex)
        : pageIndex;
    final faceSurface = _buildCachedPageSurface(
      context,
      facePageIndex,
      pageSize,
      kind: showBackside
          ? ArticlePageSurfaceKind.back
          : ArticlePageSurfaceKind.front,
    );
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        faceSurface,
        _buildFlippingSurfaceOverlay(
          palette: palette,
          direction: direction,
          progress: progress,
          showBackside: showBackside,
        ),
      ],
    );
  }

  bool _shouldShowSoftFlippingBackside({
    required StPageFlipDirection direction,
    required double visualAngle,
  }) {
    final angleMagnitude = visualAngle.abs();
    if (direction == StPageFlipDirection.back) {
      return angleMagnitude <= math.pi / 2;
    }
    // Forward's dynamic soft layer represents the lifted moving sheet. Once it
    // is painted, that sheet is the page backside; progress only controls where
    // the sheet is, not which texture face it owns.
    return true;
  }

  /// BACK owns both faces on one moving sheet. The outer soft-layer transform
  /// and clip are shared by this Stack; these only partition the sheet-local
  /// interval emitted by [ArticlePageBackwardLeafFrame].
  Widget _buildBackwardSplitFlippingSurface({
    required BuildContext context,
    required int pageIndex,
    required int backFacePageIndex,
    required Size pageSize,
    required ArticlePageBackwardLeafFrame backwardLeafFrame,
    required _PageLine? backwardFoldLine,
    required _PageLine? backwardFreeEdgeLine,
    required List<Offset> sheetContentLocalPolygon,
    required ArticleTemplatePalette palette,
    required double progress,
  }) {
    final faces = resolveBackwardCanonicalSheetFaces(
      BackwardCanonicalSheetInput(
        pageSize: pageSize,
        sheetLocalPolygon: sheetContentLocalPolygon,
        sheetAreaPolygon: sheetContentLocalPolygon,
        sheetLocalFoldLine: backwardFoldLine,
        sheetLocalFreeEdgeLine: backwardFreeEdgeLine,
        currentResidualPagePolygon: const <Offset>[],
        rectoCoverageNormalized: backwardLeafFrame.sheetRectoCoverageNormalized,
      ),
    );
    final rectoPolygon = faces.previousFrontRectoLocalPolygon;
    final versoPolygon = faces.previousBackVersoLocalPolygon;
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        if (polygonHasVisibleArea(rectoPolygon))
          _buildBackwardSheetFacePolygon(
            key: const ValueKey<String>(
              'article_backward_flipping_recto_slice',
            ),
            context: context,
            pageIndex: pageIndex,
            pageSize: pageSize,
            polygon: rectoPolygon,
            kind: ArticlePageSurfaceKind.front,
          ),
        if (polygonHasVisibleArea(versoPolygon))
          _buildBackwardSheetFacePolygon(
            key: const ValueKey<String>(
              'article_backward_flipping_verso_slice',
            ),
            context: context,
            pageIndex: backFacePageIndex,
            pageSize: pageSize,
            polygon: versoPolygon,
            kind: ArticlePageSurfaceKind.back,
          ),
        _buildFlippingSurfaceOverlay(
          palette: palette,
          direction: StPageFlipDirection.back,
          progress: progress,
          showBackside: polygonHasVisibleArea(versoPolygon),
        ),
      ],
    );
  }

  Widget _buildBackwardSheetFacePolygon({
    required Key key,
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> polygon,
    required ArticlePageSurfaceKind kind,
  }) {
    return Positioned.fill(
      key: key,
      child: ClipPath(
        clipper: ArticlePolygonClipper(polygon),
        child: OverflowBox(
          alignment: Alignment.topLeft,
          minWidth: pageSize.width,
          maxWidth: pageSize.width,
          minHeight: pageSize.height,
          maxHeight: pageSize.height,
          child: SizedBox(
            width: pageSize.width,
            height: pageSize.height,
            child: _buildCachedPageSurface(
              context,
              pageIndex,
              pageSize,
              kind: kind,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildBottomProjectedPageSurface({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required StPageFlipDirection direction,
    StPageFlipShadowData? shadow,
  }) {
    final palette = resolveArticleTemplatePalette(context, _deck.template);
    return Stack(
      fit: StackFit.expand,
      children: <Widget>[
        _buildCachedPageSurface(
          context,
          pageIndex,
          pageSize,
          kind: ArticlePageSurfaceKind.bottom,
        ),
        if (shadow != null)
          _buildBottomPageProjectionOverlay(
            shadow: shadow,
            direction: direction,
            pageSize: pageSize,
            palette: palette,
          ),
        IgnorePointer(
          child: DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  AppColors.white.withValues(alpha: 0.05),
                  AppColors.transparent,
                  palette.shadowColor.withValues(alpha: 0.03),
                ],
                stops: const <double>[0.0, 0.36, 1.0],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildBottomPageProjectionOverlay({
    required StPageFlipShadowData shadow,
    required StPageFlipDirection direction,
    required Size pageSize,
    required ArticleTemplatePalette palette,
  }) {
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerRight;
    final widthFactor =
        (math.max(shadow.width, pageSize.width * 0.12) / pageSize.width)
            .clamp(0.12, 0.72)
            .toDouble();
    return IgnorePointer(
      child: Transform.rotate(
        angle: shadow.angle * 0.18,
        alignment: edgeAlignment,
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            Align(
              alignment: edgeAlignment,
              child: FractionallySizedBox(
                widthFactor: widthFactor,
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: edgeAlignment,
                      end: oppositeEdge,
                      colors: <Color>[
                        AppColors.black.withValues(
                          alpha: shadow.opacity * 0.26,
                        ),
                        palette.shadowColor.withValues(
                          alpha: shadow.opacity * 0.14,
                        ),
                        AppColors.transparent,
                      ],
                      stops: const <double>[0.0, 0.32, 1.0],
                    ),
                  ),
                ),
              ),
            ),
            DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.topCenter,
                  end: Alignment.bottomCenter,
                  colors: <Color>[
                    AppColors.black.withValues(alpha: shadow.opacity * 0.03),
                    AppColors.transparent,
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  /// StPageFlip native `HTMLPage.drawSoft` local clip formula.
  ///
  /// In single-page portrait BACK, the previous page lives on the invisible
  /// left-side symmetric plane and is projected around the visible current
  /// page's left edge (the spine). Therefore BACK must use `anchor.x - p.x`;
  /// using the forward `(p.x - anchor.x)` formula flips the sheet to the wrong
  /// side or pushes it into negative viewport coordinates.
  List<Offset> _localPolygonFromArea({
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    return area
        .map((point) {
          return _localPointFromAreaPoint(
            point: point,
            anchor: anchor,
            angle: angle,
            direction: direction,
          );
        })
        .toList(growable: false);
  }

  Offset _localPointFromAreaPoint({
    required Offset point,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    final translated = direction == StPageFlipDirection.back
        ? Offset(anchor.dx - point.dx, point.dy - anchor.dy)
        : Offset(point.dx - anchor.dx, point.dy - anchor.dy);
    return rotatePoint(translated, Offset.zero, angle);
  }

  ArticlePageCurlCorner? _stageCornerForScene(StPageFlipScene scene) {
    final direction = _sceneRenderDirection(scene);
    final corner = scene.renderFrame?.corner ?? scene.corner;
    if (direction == null ||
        corner == null ||
        (scene.renderFrame == null && scene.calculation == null)) {
      return null;
    }
    return switch ((direction, corner)) {
      (StPageFlipDirection.forward, StPageFlipCorner.top) =>
        ArticlePageCurlCorner.topRight,
      (StPageFlipDirection.forward, StPageFlipCorner.bottom) =>
        ArticlePageCurlCorner.bottomRight,
      (StPageFlipDirection.back, StPageFlipCorner.top) =>
        ArticlePageCurlCorner.topLeft,
      (StPageFlipDirection.back, StPageFlipCorner.bottom) =>
        ArticlePageCurlCorner.bottomLeft,
    };
  }

  Widget _buildStaticBookPage(BuildContext context, int pageIndex, Rect rect) {
    return Positioned.fromRect(
      rect: rect,
      child: _buildCachedPageSurface(
        context,
        pageIndex,
        rect.size,
        kind: ArticlePageSurfaceKind.front,
      ),
    );
  }

  Widget _buildSoftPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
    StPageFlipDirection? visualGeometryDirection,
    required StPageFlipBoundsRect bounds,
    bool isFlippingPage = false,
    double progress = 0,
    StPageFlipShadowData? projectedShadow,
    bool lockSpineLine = false,
    double? surfaceAngle,
    int? backFacePageIndex,
    ArticlePageBackwardLeafFrame? backwardLeafFrame,
    _PageLine? backwardFoldLine,
    _PageLine? backwardFreeEdgeLine,
  }) {
    final geometryDirection = visualGeometryDirection ?? direction;
    final geometryAngle = lockSpineLine ? 0.0 : angle;
    final layerOrigin = softLayerOrigin(
      anchor: anchor,
      pageSize: pageSize,
      direction: geometryDirection,
      isFlippingPage: isFlippingPage,
      lockSpineLine: lockSpineLine,
    );
    final polygon = _localPolygonFromArea(
      area: area,
      anchor: layerOrigin,
      angle: geometryAngle,
      direction: geometryDirection,
    );
    final useBackwardMaterialSheet =
        direction == StPageFlipDirection.back &&
        isFlippingPage &&
        backwardFoldLine != null &&
        backwardFreeEdgeLine != null;
    final sheetMaterialLocalPolygon = useBackwardMaterialSheet
        ? pageRectPolygon(pageSize)
        : const <Offset>[];
    final localBackwardFoldLine = backwardFoldLine == null
        ? null
        : (
            _localPointFromAreaPoint(
              point: backwardFoldLine.$1,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
            _localPointFromAreaPoint(
              point: backwardFoldLine.$2,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
          );
    final localBackwardFreeEdgeLine = backwardFreeEdgeLine == null
        ? null
        : (
            _localPointFromAreaPoint(
              point: backwardFreeEdgeLine.$1,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
            _localPointFromAreaPoint(
              point: backwardFreeEdgeLine.$2,
              anchor: layerOrigin,
              angle: geometryAngle,
              direction: geometryDirection,
            ),
          );
    final position = convertBookPointToViewport(
      layerOrigin,
      bounds,
      direction: softLayerViewportDirection(geometryDirection),
    );
    final paintBounds = isFlippingPage
        ? resolveSoftLayerPaintBounds(pageSize: pageSize, polygon: polygon)
        : Offset.zero & pageSize;
    final paintOrigin = paintBounds.topLeft;
    final positionedOffset =
        position + rotatePointForCanvasTransform(paintOrigin, geometryAngle);
    final shiftedPolygon = paintOrigin == Offset.zero
        ? polygon
        : polygon.map((point) => point - paintOrigin).toList(growable: false);
    return Positioned(
      left: positionedOffset.dx,
      top: positionedOffset.dy,
      width: paintBounds.width,
      height: paintBounds.height,
      child: Transform.rotate(
        angle: geometryAngle,
        alignment: softLayerAlignment(
          anchor: anchor,
          pageSize: pageSize,
          direction: geometryDirection,
          isFlippingPage: isFlippingPage,
          lockSpineLine: lockSpineLine,
        ),
        child: ClipPath(
          clipper: ArticlePolygonClipper(shiftedPolygon),
          child: Transform.translate(
            offset: -paintOrigin,
            child: SizedBox(
              width: pageSize.width,
              height: pageSize.height,
              child: isFlippingPage
                  ? _buildSoftFlippingPageSurface(
                      context: context,
                      pageIndex: pageIndex,
                      pageSize: pageSize,
                      direction: direction,
                      progress: progress,
                      visualAngle: surfaceAngle ?? angle,
                      backFacePageIndex: backFacePageIndex,
                      backwardLeafFrame: backwardLeafFrame,
                      backwardFoldLine: localBackwardFoldLine,
                      backwardFreeEdgeLine: localBackwardFreeEdgeLine,
                      sheetLocalPolygon: polygon,
                      sheetContentLocalPolygon: polygon,
                      sheetAreaPolygon: useBackwardMaterialSheet
                          ? polygon
                          : area,
                      sheetMaterialLocalPolygon: sheetMaterialLocalPolygon,
                    )
                  : _buildBottomProjectedPageSurface(
                      context: context,
                      pageIndex: pageIndex,
                      pageSize: pageSize,
                      direction: direction,
                      shadow: projectedShadow,
                    ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildDynamicPageLayer({
    required BuildContext context,
    required int pageIndex,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipScene scene,
    required StPageFlipDirection direction,
    StPageFlipDirection? visualGeometryDirection,
    required bool isFlippingPage,
    bool lockSpineLine = false,
    double? surfaceAngle,
    int? backFacePageIndex,
    ArticlePageBackwardLeafFrame? backwardLeafFrame,
    _PageLine? backwardFoldLine,
    _PageLine? backwardFreeEdgeLine,
  }) {
    return _buildSoftPageLayer(
      context: context,
      pageIndex: pageIndex,
      pageSize: pageSize,
      area: area,
      anchor: anchor,
      angle: angle,
      direction: direction,
      visualGeometryDirection: visualGeometryDirection,
      bounds: scene.layout.bounds,
      isFlippingPage: isFlippingPage,
      progress: _sceneProgress(scene),
      projectedShadow: isFlippingPage ? null : _sceneShadow(scene),
      lockSpineLine: lockSpineLine,
      surfaceAngle: surfaceAngle,
      backFacePageIndex: backFacePageIndex,
      backwardLeafFrame: backwardLeafFrame,
      backwardFoldLine: backwardFoldLine,
      backwardFreeEdgeLine: backwardFreeEdgeLine,
    );
  }

  Widget _buildHotzoneMarkers(StPageFlipScene scene, Size stageSize) {
    const hotzoneExtent = 88.0;
    final rightPageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    final leftAnchorRect =
        scene.layout.orientation == StPageFlipOrientation.portrait
        ? rightPageRect
        : resolveBookPageRect(scene.layout, isRightPage: false);
    final controller = _pageFlipController;
    final leftEdgeInset =
        _deck.onOverflowPrevious != null &&
            !(controller?.canFlipDirection(StPageFlipDirection.back) ?? false)
        ? _ArticleReadOnlyBookDeckState._overflowEdgeStartInset
        : 0.0;
    final rightEdgeInset =
        _deck.onOverflowNext != null &&
            !(controller?.canFlipDirection(StPageFlipDirection.forward) ??
                false)
        ? _ArticleReadOnlyBookDeckState._overflowEdgeStartInset
        : 0.0;
    final markerOffsets = <ArticlePageCurlCorner, Offset>{
      ArticlePageCurlCorner.topLeft: Offset(
        (leftAnchorRect.left + leftEdgeInset)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        leftAnchorRect.top
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      ArticlePageCurlCorner.topRight: Offset(
        (rightPageRect.right - hotzoneExtent - rightEdgeInset)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        rightPageRect.top
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      ArticlePageCurlCorner.bottomLeft: Offset(
        (leftAnchorRect.left + leftEdgeInset)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        (leftAnchorRect.bottom - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
      ArticlePageCurlCorner.bottomRight: Offset(
        (rightPageRect.right - hotzoneExtent - rightEdgeInset)
            .clamp(0.0, math.max(0.0, stageSize.width - hotzoneExtent))
            .toDouble(),
        (rightPageRect.bottom - hotzoneExtent)
            .clamp(0.0, math.max(0.0, stageSize.height - hotzoneExtent))
            .toDouble(),
      ),
    };
    return Stack(
      children: markerOffsets.entries
          .map((entry) {
            final hotzoneRect = Rect.fromLTWH(
              entry.value.dx,
              entry.value.dy,
              hotzoneExtent,
              hotzoneExtent,
            );
            return Positioned(
              left: hotzoneRect.left,
              top: hotzoneRect.top,
              width: hotzoneRect.width,
              height: hotzoneRect.height,
              child: IgnorePointer(
                child: SizedBox.expand(key: _hotzoneKey(entry.key)),
              ),
            );
          })
          .toList(growable: false),
    );
  }
}
