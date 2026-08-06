part of 'media_page_flip_book.dart';

extension _MediaPageFlipBookStateSoftSurface on _MediaPageFlipBookState {
  List<Widget> _buildDynamicLayers(StPageFlipScene scene) {
    final renderFrame = scene.renderFrame;
    if (renderFrame == null) {
      return const <Widget>[];
    }
    final binding = _textureBindingForScene(scene);
    final bundle = _textureBundleForScene(scene, binding);
    if (binding == null || bundle == null) {
      return const <Widget>[];
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final direction = scene.direction ?? renderFrame.renderDirection;
    if (direction == StPageFlipDirection.forward) {
      return <Widget>[
        if (renderFrame.bottomClipArea.length >= 3)
          _buildDynamicPageLayer(
            key: const ValueKey<String>('media-pageflip-bottom-layer'),
            transformKey: const ValueKey<String>(
              'media-pageflip-bottom-transform',
            ),
            textureRef: binding.bottom,
            pageSize: pageSize,
            area: renderFrame.bottomClipArea,
            anchor: renderFrame.bottomAnchor,
            angle: 0,
            direction: StPageFlipDirection.forward,
            visualGeometryDirection: renderFrame.visualGeometryDirection,
            bounds: scene.layout.bounds,
            isFlippingPage: false,
            progress: renderFrame.progress,
            shadow: renderFrame.shadow,
          ),
        if (renderFrame.flippingClipArea.length >= 3)
          _buildDynamicPageLayer(
            key: const ValueKey<String>('media-pageflip-flipping-layer'),
            transformKey: const ValueKey<String>(
              'media-pageflip-flipping-transform',
            ),
            textureRef: binding.verso,
            rectoTextureRef: binding.recto,
            pageSize: pageSize,
            area: renderFrame.flippingClipArea,
            anchor: renderFrame.flippingAnchor,
            angle: renderFrame.angle,
            direction: StPageFlipDirection.forward,
            visualGeometryDirection: renderFrame.visualGeometryDirection,
            bounds: scene.layout.bounds,
            isFlippingPage: true,
            progress: renderFrame.progress,
          ),
      ];
    }

    return <Widget>[
      _buildBackwardPageSpaceReplacementLayer(
        pageRect: resolveBookPageRect(scene.layout, isRightPage: true),
        textureRef: binding.recto,
      ),
      if (renderFrame.bottomClipArea.length >= 3)
        _buildDynamicPageLayer(
          key: const ValueKey<String>('media-pageflip-bottom-layer'),
          transformKey: const ValueKey<String>(
            'media-pageflip-bottom-transform',
          ),
          textureRef: binding.bottom,
          pageSize: pageSize,
          area: renderFrame.bottomClipArea,
          anchor: renderFrame.bottomAnchor,
          angle: 0,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: renderFrame.visualGeometryDirection,
          bounds: scene.layout.bounds,
          isFlippingPage: false,
          progress: renderFrame.progress,
          shadow: renderFrame.shadow,
        ),
      if (renderFrame.flippingClipArea.length >= 3)
        _buildDynamicPageLayer(
          key: const ValueKey<String>('media-pageflip-flipping-layer'),
          transformKey: const ValueKey<String>(
            'media-pageflip-flipping-transform',
          ),
          textureRef: binding.verso,
          rectoTextureRef: binding.recto,
          pageSize: pageSize,
          area: renderFrame.flippingClipArea,
          anchor: renderFrame.flippingAnchor,
          angle: renderFrame.angle,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: renderFrame.visualGeometryDirection,
          bounds: scene.layout.bounds,
          isFlippingPage: true,
          progress: renderFrame.progress,
        ),
    ];
  }

  Widget _buildDynamicPageLayer({
    required Key key,
    required Key transformKey,
    required _MediaPageTextureRef textureRef,
    _MediaPageTextureRef? rectoTextureRef,
    required Size pageSize,
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
    required StPageFlipDirection visualGeometryDirection,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
    required double progress,
    StPageFlipShadowData? shadow,
  }) {
    final geometryDirection = visualGeometryDirection;
    final layerOrigin = anchor;
    final localPolygon = _localPolygonFromArea(
      area: area,
      anchor: layerOrigin,
      angle: angle,
      direction: geometryDirection,
    );
    if (localPolygon.length < 3) {
      return const SizedBox.shrink();
    }
    final position = convertBookPointToViewport(
      layerOrigin,
      bounds,
      direction: geometryDirection,
    );
    final paintBounds = isFlippingPage
        ? _softLayerPaintBounds(pageSize: pageSize, polygon: localPolygon)
        : Offset.zero & pageSize;
    final paintOrigin = paintBounds.topLeft;
    final positionedOffset =
        position + _rotatePointForCanvasTransform(paintOrigin, angle);
    final shiftedPolygon = paintOrigin == Offset.zero
        ? localPolygon
        : localPolygon
              .map((point) => point - paintOrigin)
              .toList(growable: false);
    return Positioned(
      key: key,
      left: positionedOffset.dx,
      top: positionedOffset.dy,
      width: paintBounds.width,
      height: paintBounds.height,
      child: Transform.rotate(
        key: transformKey,
        angle: angle,
        alignment: Alignment.topLeft,
        child: ClipPath(
          clipper: _MediaPagePolygonClipper(shiftedPolygon),
          child: Transform.translate(
            offset: -paintOrigin,
            child: SizedBox(
              width: pageSize.width,
              height: pageSize.height,
              child: Stack(
                fit: StackFit.expand,
                children: <Widget>[
                  if (isFlippingPage && rectoTextureRef != null)
                    _buildFlippingSheetSurface(
                      rectoRef: rectoTextureRef,
                      versoRef: textureRef,
                      direction: direction,
                      visualAngle: angle,
                    )
                  else
                    _buildTextureSurface(textureRef),
                  _buildDynamicSurfaceOverlay(
                    direction: direction,
                    isBackFace: isFlippingPage && rectoTextureRef != null
                        ? _shouldShowFlippingBackside(
                            direction: direction,
                            visualAngle: angle,
                          )
                        : textureRef.face == MediaPageFlipSurfaceFace.back,
                    isFlippingPage: isFlippingPage,
                    progress: progress,
                    pageSize: pageSize,
                    shadow: shadow,
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildFlippingSheetSurface({
    required _MediaPageTextureRef rectoRef,
    required _MediaPageTextureRef versoRef,
    required StPageFlipDirection direction,
    required double visualAngle,
  }) {
    final showBackside = _shouldShowFlippingBackside(
      direction: direction,
      visualAngle: visualAngle,
    );
    final faceRef = showBackside ? versoRef : rectoRef;
    return KeyedSubtree(
      key: ValueKey<String>(
        'media-pageflip-moving-face-${faceRef.pageIndex}-${faceRef.face.name}',
      ),
      child: _buildTextureSurface(faceRef),
    );
  }

  bool _shouldShowFlippingBackside({
    required StPageFlipDirection direction,
    required double visualAngle,
  }) {
    if (direction == StPageFlipDirection.forward) {
      return true;
    }
    return visualAngle.abs() <= math.pi / 2;
  }

  Widget _buildBackwardPageSpaceReplacementLayer({
    required Rect pageRect,
    required _MediaPageTextureRef textureRef,
  }) {
    return Positioned.fromRect(
      key: const ValueKey<String>(
        'media-pageflip-backward-previous-front-replacement',
      ),
      rect: pageRect,
      child: _buildTextureSurface(textureRef),
    );
  }

  Widget _buildTextureSurface(_MediaPageTextureRef ref) {
    final key = _MediaPageTextureKey(ref.pageIndex, ref.face);
    var snapshot = _pageSnapshots[key];
    if (snapshot == null &&
        widget.textureSnapshotBuilder == null &&
        ref.face == MediaPageFlipSurfaceFace.back) {
      snapshot =
          _pageSnapshots[_MediaPageTextureKey(
            ref.pageIndex,
            MediaPageFlipSurfaceFace.front,
          )];
    }
    if (snapshot == null) {
      return ColoredBox(color: widget.stageColor);
    }
    return KeyedSubtree(
      key: ValueKey<String>(
        'media-pageflip-surface-${ref.pageIndex}-${ref.face.name}',
      ),
      child: RawImage(
        image: snapshot.image,
        fit: BoxFit.fill,
        filterQuality: FilterQuality.medium,
      ),
    );
  }

  Widget _buildDynamicSurfaceOverlay({
    required StPageFlipDirection direction,
    required bool isBackFace,
    required bool isFlippingPage,
    required double progress,
    required Size pageSize,
    StPageFlipShadowData? shadow,
  }) {
    if (!isFlippingPage) {
      if (shadow == null || shadow.opacity <= 0.001 || pageSize.width <= 0) {
        return const SizedBox.expand();
      }
      final widthFactor =
          (math.max(shadow.width, pageSize.width * 0.12) / pageSize.width)
              .clamp(0.12, 0.72)
              .toDouble();
      return IgnorePointer(
        child: Align(
          alignment: Alignment.centerLeft,
          child: FractionallySizedBox(
            widthFactor: widthFactor,
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: <Color>[
                    AppColors.black.withValues(alpha: shadow.opacity * 0.26),
                    AppColors.black.withValues(alpha: shadow.opacity * 0.10),
                    AppColors.transparent,
                  ],
                  stops: const <double>[0.0, 0.32, 1.0],
                ),
              ),
            ),
          ),
        ),
      );
    }
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    final lift = Curves.easeOutCubic.transform(settledProgress);
    final edgeAlignment = direction == StPageFlipDirection.forward
        ? Alignment.centerRight
        : Alignment.centerLeft;
    final oppositeEdge = direction == StPageFlipDirection.forward
        ? Alignment.centerLeft
        : Alignment.centerRight;
    final edgeShadow = AppColors.black.withValues(
      alpha: (isBackFace ? 0.065 : 0.10) + lift * (isBackFace ? 0.025 : 0.05),
    );
    final paperHighlight = AppColors.white.withValues(
      alpha: (isBackFace ? 0.07 : 0.10) + lift * 0.025,
    );
    return IgnorePointer(
      child: Stack(
        fit: StackFit.expand,
        children: <Widget>[
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: edgeAlignment,
                end: oppositeEdge,
                colors: <Color>[
                  edgeShadow,
                  AppColors.black.withValues(
                    alpha: isFlippingPage ? 0.05 : 0.03,
                  ),
                  AppColors.transparent,
                ],
                stops: const <double>[0.0, 0.32, 1.0],
              ),
            ),
          ),
          DecoratedBox(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                begin: Alignment.topCenter,
                end: Alignment.bottomCenter,
                colors: <Color>[
                  paperHighlight,
                  AppColors.transparent,
                  AppColors.black.withValues(
                    alpha:
                        (isBackFace ? 0.025 : 0.12) +
                        lift * (isBackFace ? 0.02 : 0.035),
                  ),
                ],
                stops: const <double>[0.0, 0.5, 1.0],
              ),
            ),
          ),
        ],
      ),
    );
  }

  List<Offset> _localPolygonFromArea({
    required List<Offset> area,
    required Offset anchor,
    required double angle,
    required StPageFlipDirection direction,
  }) {
    return area
        .map((point) {
          final translated = direction == StPageFlipDirection.back
              ? Offset(anchor.dx - point.dx, point.dy - anchor.dy)
              : Offset(point.dx - anchor.dx, point.dy - anchor.dy);
          return rotatePoint(translated, Offset.zero, angle);
        })
        .toList(growable: false);
  }

  Rect _softLayerPaintBounds({
    required Size pageSize,
    required List<Offset> polygon,
  }) {
    final bounds = _polygonBounds(polygon);
    if (bounds == null) {
      return Offset.zero & pageSize;
    }
    return Rect.fromLTRB(
      math.min(0.0, bounds.left),
      math.min(0.0, bounds.top),
      math.max(pageSize.width, bounds.right),
      math.max(pageSize.height, bounds.bottom),
    );
  }

  Rect? _polygonBounds(List<Offset> polygon) {
    if (polygon.isEmpty) {
      return null;
    }
    var left = polygon.first.dx;
    var top = polygon.first.dy;
    var right = left;
    var bottom = top;
    for (final point in polygon.skip(1)) {
      left = math.min(left, point.dx);
      top = math.min(top, point.dy);
      right = math.max(right, point.dx);
      bottom = math.max(bottom, point.dy);
    }
    return Rect.fromLTRB(left, top, right, bottom);
  }

  Offset _rotatePointForCanvasTransform(Offset point, double angle) {
    final sinAngle = math.sin(angle);
    final cosAngle = math.cos(angle);
    return Offset(
      point.dx * cosAngle - point.dy * sinAngle,
      point.dx * sinAngle + point.dy * cosAngle,
    );
  }
}

class _MediaPagePolygonClipper extends CustomClipper<Path> {
  const _MediaPagePolygonClipper(this.points);

  final List<Offset> points;

  @override
  Path getClip(Size size) {
    final path = Path();
    if (points.isEmpty) {
      return path;
    }
    path.moveTo(points.first.dx, points.first.dy);
    for (final point in points.skip(1)) {
      path.lineTo(point.dx, point.dy);
    }
    path.close();
    return path;
  }

  @override
  bool shouldReclip(covariant _MediaPagePolygonClipper oldClipper) {
    if (identical(points, oldClipper.points)) {
      return false;
    }
    if (points.length != oldClipper.points.length) {
      return true;
    }
    for (var index = 0; index < points.length; index += 1) {
      if (points[index] != oldClipper.points[index]) {
        return true;
      }
    }
    return false;
  }
}
