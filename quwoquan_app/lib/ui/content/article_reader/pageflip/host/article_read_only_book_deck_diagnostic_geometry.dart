part of 'article_read_only_book_deck.dart';

typedef _PageLine = (Offset, Offset);

/// 后翻 diagnostic 几何 record。recto/verso 与真实 moving sheet 共用同一个
/// native soft geometry；两者只按 [ArticlePageBackwardLeafFrame] 的 sheet-local
/// 宽度区间分段。
typedef _BackwardDiagnosticGeometry = ({
  SoftPageLayerGeometry softGeometry,
  List<Offset> sheetLocalPolygon,
  List<Offset> sheetMaterialLocalPolygon,
  Rect? sheetLocalBounds,
  Rect? sheetViewportBounds,
  List<Offset> rectoLocalPolygon,
  List<Offset> rectoViewportPolygon,
  Rect? rectoViewportBounds,
  List<Offset> versoLocalPolygon,
  List<Offset> versoViewportPolygon,
  Rect? versoViewportBounds,
  List<Offset> paintedUnionLocalPolygon,
  List<Offset> paintedUnionViewportPolygon,
  Rect? paintedUnionViewportBounds,
  (Offset, Offset)? foldLineViewport,
  (Offset, Offset)? freeEdgeLineViewport,
  List<Offset> currentResidualPagePolygon,
  List<Offset> currentResidualViewportPolygon,
  Rect? currentResidualViewportBounds,
});

class _BackwardGeometryGuidePainter extends CustomPainter {
  const _BackwardGeometryGuidePainter({
    required this.foldLine,
    this.freeEdgeLine,
  });

  final (Offset, Offset) foldLine;
  final (Offset, Offset)? freeEdgeLine;

  @override
  void paint(Canvas canvas, Size size) {
    final foldPaint = Paint()
      ..color = AppColors.error
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;
    final pageEdgePaint = Paint()
      ..color = AppColors.iosSystemCyanAccent
      ..strokeWidth = 3
      ..style = PaintingStyle.stroke;
    canvas.drawLine(foldLine.$1, foldLine.$2, foldPaint);
    if (freeEdgeLine case final freeEdge?) {
      canvas.drawLine(freeEdge.$1, freeEdge.$2, pageEdgePaint);
    }
    _paintLabel(canvas, 'F', foldLine.$1 + const Offset(4, 4), foldPaint.color);
    if (freeEdgeLine case final freeEdge?) {
      _paintLabel(
        canvas,
        'R',
        freeEdge.$1 + const Offset(4, 4),
        pageEdgePaint.color,
      );
    }
  }

  void _paintLabel(Canvas canvas, String label, Offset offset, Color color) {
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(
          color: color,
          fontSize: AppTypography.lg,
          fontWeight: AppTypography.extraBold,
        ),
      ),
      textDirection: TextDirection.ltr,
    )..layout();
    painter.paint(canvas, offset);
  }

  @override
  bool shouldRepaint(covariant _BackwardGeometryGuidePainter oldDelegate) {
    return oldDelegate.foldLine != foldLine ||
        oldDelegate.freeEdgeLine != freeEdgeLine;
  }
}

extension _ArticleReadOnlyBookDeckDiagnosticGeometry
    on _ArticleReadOnlyBookDeckState {
  double _sceneProgress(StPageFlipScene scene) {
    return scene.renderFrame?.progress ??
        ((scene.calculation?.getFlippingProgress() ?? 0) / 100)
            .clamp(0.0, 1.0)
            .toDouble();
  }

  /// 仅用于诊断/标签的简单阶段名。新的 backward 主线由旋转角度驱动表面切换，
  /// 这里保留三档进度桶名是为了让记录诊断面板/测试快照保持兼容。
  String _resolveBackwardSurfacePhaseName(double progress) {
    final settledProgress = progress.clamp(0.0, 1.0).toDouble();
    if (settledProgress < 0.32) {
      return 'verso';
    }
    if (settledProgress < 0.68) {
      return 'transition';
    }
    return 'recto';
  }

  String? _resolveBackwardCornerLabel(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final corner = scene.renderFrame?.corner ?? scene.corner;
    if (corner == null) {
      return null;
    }
    return _cornerNameFromPageFlip(corner, StPageFlipDirection.back);
  }

  Offset? _resolveBackwardHinge({
    required StPageFlipScene scene,
    required Size pageSize,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final corner = scene.renderFrame?.corner ?? scene.corner;
    if (corner == null) {
      return null;
    }
    return corner == StPageFlipCorner.bottom
        ? Offset(0, pageSize.height)
        : Offset.zero;
  }

  Offset? _resolveBackwardSpineTop(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final calculation = scene.calculation;
    if (calculation is StPageFlipCalculation) {
      return calculation.getBackwardSpineTop();
    }
    return Offset.zero;
  }

  Offset? _resolveBackwardSpineBottom({
    required StPageFlipScene scene,
    required Size pageSize,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final calculation = scene.calculation;
    if (calculation is StPageFlipCalculation) {
      return calculation.getBackwardSpineBottom();
    }
    return Offset(0, pageSize.height);
  }

  double? _resolveBackwardSeamX(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final renderFrame = scene.renderFrame;
    final calculation = scene.calculation;
    if (renderFrame?.flippingClipArea case final area?) {
      return area.fold<double>(
        0,
        (current, point) => math.max(current, point.dx),
      );
    }
    if (calculation is StPageFlipCalculation) {
      return calculation.backwardSeamX;
    }
    return null;
  }

  ArticlePageBackwardLeafFrame? _resolveBackwardLeafFrame(
    StPageFlipScene scene,
  ) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final renderFrameLeaf = scene.renderFrame?.backwardLeafFrame;
    if (renderFrameLeaf != null) {
      return renderFrameLeaf;
    }
    return resolveArticlePageBackwardLeafFrame(
      direction: StPageFlipDirection.back,
      progress: _sceneProgress(scene),
      reversePose: null,
    );
  }

  String _resolveBackwardCompositionPhase(ArticlePageBackwardLeafFrame frame) {
    final versoWidth = frame.versoRevealWidthNormalized;
    final rectoWidth = frame.totalRectoVisibleWidthNormalized;
    if (versoWidth > 0.02 && rectoWidth < 0.02) {
      return 'verso';
    }
    if (versoWidth > 0.01) {
      return 'transition';
    }
    return 'recto';
  }

  String? _resolveBackwardPhaseLabel(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final frame = _resolveBackwardLeafFrame(scene);
    if (frame != null) {
      return _resolveBackwardCompositionPhase(frame);
    }
    return _resolveBackwardSurfacePhaseName(_sceneProgress(scene));
  }

  int? _resolveBackwardReplayFrontLayerCount(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    return _hasBackwardPaperFoldFrame(scene) && scene.flippingPageIndex != null
        ? 1
        : 0;
  }

  String? _resolveBackwardReplayBackSurfaceStrategy(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    return scene.flippingPageIndex == null
        ? null
        : 'paperFoldBackMainlineSurface';
  }

  Set<int> _resolveBackwardDynamicOwnedPageSet(StPageFlipScene scene) {
    if (!_hasBackwardPaperFoldFrame(scene)) {
      return const <int>{};
    }
    return <int>{if (scene.flippingPageIndex != null) scene.flippingPageIndex!};
  }

  List<int> _sortedPageIndices(Iterable<int> pageIndices) {
    return (pageIndices.toSet().toList()..sort()).toList(growable: false);
  }

  List<int> _resolveBackwardStaticSuppressedPages({
    required StPageFlipScene scene,
    required Set<int> dynamicOwnedPages,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return const <int>[];
    }
    return _sortedPageIndices(<int>[
      if (scene.visibleSpread.leftPageIndex != null &&
          dynamicOwnedPages.contains(scene.visibleSpread.leftPageIndex))
        scene.visibleSpread.leftPageIndex!,
      if (scene.visibleSpread.rightPageIndex != null &&
          dynamicOwnedPages.contains(scene.visibleSpread.rightPageIndex))
        scene.visibleSpread.rightPageIndex!,
    ]);
  }

  bool _hasBackwardPaperFoldFrame(StPageFlipScene scene) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back ||
        scene.bottomPageIndex == null ||
        scene.flippingPageIndex == null) {
      return false;
    }
    final frame = scene.renderFrame;
    return frame != null &&
        frame.flippingClipArea.length >= 3 &&
        frame.bottomClipArea.length >= 3;
  }

  /// 由 backward leaf frame 直接推导诊断阶段标签。新主线下没有了基于 region
  /// 的几何派生，所以用 frame 的覆盖参数直接打档。
  String? _resolveBackwardSimulatorVisualPhase(
    ArticlePageBackwardLeafFrame? frame,
  ) {
    if (frame == null) {
      return null;
    }
    final frontCoverage = frame.rectoCoverageNormalized.clamp(0.0, 1.0);
    final visibleBack = frame.versoRevealWidthNormalized.clamp(0.0, 1.0);
    if (frontCoverage <= 0.02 && visibleBack > 0.05) {
      return 'versoDominant';
    }
    if (visibleBack > 0.08 && frontCoverage < 0.72) {
      return 'mixedReplay';
    }
    if (frontCoverage >= 0.72) {
      return 'rectoTakeover';
    }
    return 'transition';
  }

  String? _resolveBackwardReplaySliceLabel(
    ArticlePageBackwardLeafFrame? frame,
    StPageFlipScene scene, {
    required Rect pageRect,
    required Rect? frontPaintBounds,
    required Rect? backPaintBounds,
    required double? surfaceAngle,
    required int flippingSheetCount,
    required String? frontSheetId,
    required String? backSheetId,
    required bool currentLayerPresent,
    required bool multiSliceViolation,
  }) {
    if (_sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    final backStrategy = _resolveBackwardReplayBackSurfaceStrategy(scene);
    if (backStrategy == null) {
      return null;
    }
    final renderFrame = scene.renderFrame;
    final staticBottomSuppressed =
        scene.bottomPageIndex != null &&
        _resolveBackwardStaticSuppressedPages(
          scene: scene,
          dynamicOwnedPages: _resolveBackwardDynamicOwnedPageSet(scene),
        ).contains(scene.bottomPageIndex);
    final surfaceShowsFront = frontPaintBounds != null;
    final foldDirection = surfaceAngle == null
        ? 'unknown'
        : surfaceAngle >= 0
        ? 'leftward'
        : 'rightward';
    final frontFirst = frontPaintBounds != null && backPaintBounds == null;
    final phase = frontPaintBounds == null ? 'backOnly' : 'frontTakeover';
    return <String>[
      'route=paperFoldBackwardMainline',
      'mainline=paperFoldBackMainline',
      'flipping=singleTurningSheet',
      'flippingSheetCount=$flippingSheetCount',
      'frontSheetId=${frontSheetId ?? "none"}',
      'backSheetId=${backSheetId ?? "none"}',
      'frontBackSameLeaf=${frontSheetId != null && frontSheetId == backSheetId}',
      'frontLayer=rectoSliceOnMovingSheet',
      'backLayer=versoSliceOnMovingSheet',
      'currentLayerPresent=$currentLayerPresent',
      'multiSliceViolation=$multiSliceViolation',
      'frontLayers=${frontPaintBounds == null ? 0 : 1}',
      'backSurface=$backStrategy',
      'backFirst=${backPaintBounds != null && frontPaintBounds == null}',
      'frontFirst=$frontFirst',
      'sheetSource=canonicalBackMovingEdge',
      'localPoint=${articleDiagnosticOffsetSignature(renderFrame?.localPagePoint)}',
      'staticBottomSuppressed=$staticBottomSuppressed',
      'foldDirection=$foldDirection',
      'surfaceShowsFront=$surfaceShowsFront',
      'surfacePhase=$phase',
      if (frame != null) ...<String>[
        'foldF=${frame.coveredWidthNormalized.toStringAsFixed(3)}',
        'edgeE=${frame.laidDownWidthNormalized.toStringAsFixed(3)}',
        'rectoCoverage=${frame.rectoCoverageNormalized.toStringAsFixed(3)}',
        'verso=${frame.versoRevealWidthNormalized.toStringAsFixed(3)}',
      ],
    ].join('/');
  }

  SoftPageLayerGeometry? _resolveDynamicLayerGeometry({
    required List<Offset>? area,
    required Offset? anchor,
    required double angle,
    required StPageFlipDirection? direction,
    StPageFlipDirection? visualGeometryDirection,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
    double progress = 0,
  }) {
    if (area == null ||
        area.length < 3 ||
        anchor == null ||
        direction == null) {
      return null;
    }
    final geometryDirection = visualGeometryDirection ?? direction;
    final pageSize = Size(bounds.pageWidth, bounds.height);
    final surfaceOrigin = softLayerOrigin(
      anchor: anchor,
      pageSize: pageSize,
      direction: geometryDirection,
      isFlippingPage: isFlippingPage,
      lockSpineLine: false,
    );
    final positionViewport = convertBookPointToViewport(
      surfaceOrigin,
      bounds,
      direction: softLayerViewportDirection(geometryDirection),
    );
    final localClipPolygon = _localPolygonFromArea(
      area: area,
      anchor: surfaceOrigin,
      angle: angle,
      direction: geometryDirection,
    );
    final paintBounds = resolveSoftLayerPaintBounds(
      pageSize: pageSize,
      polygon: localClipPolygon,
    );
    final paintOrigin = paintBounds.topLeft;
    final viewportClipPolygon = area
        .map((point) {
          final translated = geometryDirection == StPageFlipDirection.back
              ? Offset(surfaceOrigin.dx - point.dx, point.dy - surfaceOrigin.dy)
              : Offset(
                  point.dx - surfaceOrigin.dx,
                  point.dy - surfaceOrigin.dy,
                );
          final rotated = rotatePoint(translated, Offset.zero, angle);
          return positionViewport + rotated;
        })
        .toList(growable: false);
    return SoftPageLayerGeometry(
      surfaceOrigin: surfaceOrigin,
      pivotLocal: anchor - surfaceOrigin,
      positionViewport: positionViewport,
      surfaceViewportRect: positionViewport & pageSize,
      localClipPolygon: localClipPolygon,
      viewportClipPolygon: viewportClipPolygon,
      clipLocalBounds: polygonBounds(localClipPolygon),
      clipViewportBounds: polygonBounds(viewportClipPolygon),
      transform: Matrix4.identity()
        ..translateByDouble(
          anchor.dx - surfaceOrigin.dx,
          anchor.dy - surfaceOrigin.dy,
          0,
          1,
        )
        ..rotateZ(angle)
        ..translateByDouble(
          surfaceOrigin.dx - anchor.dx,
          surfaceOrigin.dy - anchor.dy,
          0,
          1,
        ),
      contentPositionViewport:
          positionViewport + rotatePointForCanvasTransform(paintOrigin, angle),
      paintBounds: paintBounds,
      paintOrigin: paintOrigin,
    );
  }

  /// 后翻 diagnostic 几何：native BACK frame 是唯一几何容器，front/back
  /// 只在同一 moving sheet 内按 recto/verso 宽度分段。
  _BackwardDiagnosticGeometry? _resolveBackwardDiagnosticGeometry(
    StPageFlipScene scene,
  ) {
    final frame = scene.renderFrame;
    if (frame == null ||
        _sceneRenderDirection(scene) != StPageFlipDirection.back) {
      return null;
    }
    if (frame.flippingClipArea.length < 3) {
      return null;
    }
    final softGeometry = _resolveDynamicLayerGeometry(
      area: frame.flippingClipArea,
      anchor: frame.flippingAnchor,
      angle: frame.angle,
      direction: StPageFlipDirection.back,
      visualGeometryDirection: frame.visualGeometryDirection,
      bounds: scene.layout.bounds,
      isFlippingPage: true,
      progress: _sceneProgress(scene),
    );
    if (softGeometry == null) {
      return null;
    }
    final sheetLocalPolygon = softGeometry.localClipPolygon;
    final sheetViewportPolygon = softGeometry.viewportClipPolygon;
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final leafFrame =
        frame.backwardLeafFrame ?? _resolveBackwardLeafFrame(scene);
    if (leafFrame == null) {
      return null;
    }
    final angle = frame.angle;
    final visualGeometryDirection = frame.visualGeometryDirection;
    final projected = frame.backwardProjectedFrame;
    final sheetMaterialLocalPolygon = pageRectPolygon(pageSize);
    final currentResidualPagePolygon = frame.bottomClipArea.length >= 3
        ? List<Offset>.unmodifiable(frame.bottomClipArea)
        : const <Offset>[];
    final sheetContentLocalPolygon = sheetLocalPolygon
        .map((point) => point - softGeometry.paintOrigin)
        .toList(growable: false);
    final coveredWidth = (leafFrame.coveredWidthNormalized * pageSize.width)
        .clamp(0.0, pageSize.width)
        .toDouble();
    final rectoWidth =
        (leafFrame.totalRectoVisibleWidthNormalized * pageSize.width)
            .clamp(0.0, coveredWidth)
            .toDouble();
    final slices = resolveArticlePageBackwardSheetLocalSlices(
      sheetLocalPolygon: sheetContentLocalPolygon,
      coveredWidth: coveredWidth,
      rectoWidth: rectoWidth,
    );
    final rectoLocalPolygon = slices == null
        ? const <Offset>[]
        : _clipBackwardSheetLocalSlice(
            sheetLocalPolygon: sheetContentLocalPolygon,
            pageSize: pageSize,
            left: slices.rectoLeft,
            width: slices.rectoWidth,
          );
    final versoLocalPolygon = slices == null
        ? const <Offset>[]
        : _clipBackwardSheetLocalSlice(
            sheetLocalPolygon: sheetContentLocalPolygon,
            pageSize: pageSize,
            left: slices.versoLeft,
            width: slices.versoWidth,
          );
    final paintedUnionLocalPolygon = slices == null
        ? const <Offset>[]
        : sheetContentLocalPolygon;
    final pageViewportOrigin = _backwardPageRect(scene).topLeft;
    final rectoViewportPolygon = transformSoftLayerContentLocalPolygon(
      polygon: rectoLocalPolygon,
      geometry: softGeometry,
    );
    final versoViewportPolygon = transformSoftLayerContentLocalPolygon(
      polygon: versoLocalPolygon,
      geometry: softGeometry,
    );
    final paintedUnionViewportPolygon = transformSoftLayerContentLocalPolygon(
      polygon: paintedUnionLocalPolygon,
      geometry: softGeometry,
    );
    final currentResidualViewportPolygon = currentResidualPagePolygon
        .map((p) => pageViewportOrigin + p)
        .toList(growable: false);
    final positionViewport = softGeometry.positionViewport;
    Offset toViewportPoint(Offset p) {
      final translated = visualGeometryDirection == StPageFlipDirection.back
          ? Offset(
              softGeometry.surfaceOrigin.dx - p.dx,
              p.dy - softGeometry.surfaceOrigin.dy,
            )
          : Offset(
              p.dx - softGeometry.surfaceOrigin.dx,
              p.dy - softGeometry.surfaceOrigin.dy,
            );
      final rotated = rotatePointForCanvasTransform(translated, angle);
      return positionViewport + rotated;
    }

    (Offset, Offset)? toViewportLine((Offset, Offset)? line) {
      if (line == null) {
        return null;
      }
      return orderViewportLineTopToBottom((
        toViewportPoint(line.$1),
        toViewportPoint(line.$2),
      ));
    }

    return (
      softGeometry: softGeometry,
      sheetLocalPolygon: sheetLocalPolygon,
      sheetMaterialLocalPolygon: sheetMaterialLocalPolygon,
      sheetLocalBounds: polygonBounds(sheetLocalPolygon),
      sheetViewportBounds: polygonBounds(sheetViewportPolygon),
      rectoLocalPolygon: rectoLocalPolygon,
      rectoViewportPolygon: rectoViewportPolygon,
      rectoViewportBounds: polygonBounds(rectoViewportPolygon),
      versoLocalPolygon: versoLocalPolygon,
      versoViewportPolygon: versoViewportPolygon,
      versoViewportBounds: polygonBounds(versoViewportPolygon),
      paintedUnionLocalPolygon: paintedUnionLocalPolygon,
      paintedUnionViewportPolygon: paintedUnionViewportPolygon,
      paintedUnionViewportBounds: polygonBounds(paintedUnionViewportPolygon),
      foldLineViewport: toViewportLine(projected?.foldLine),
      freeEdgeLineViewport: toViewportLine(projected?.projectedRightEdgeLine),
      currentResidualPagePolygon: currentResidualPagePolygon,
      currentResidualViewportPolygon: currentResidualViewportPolygon,
      currentResidualViewportBounds: polygonBounds(
        currentResidualViewportPolygon,
      ),
    );
  }

  List<Offset> _clipBackwardSheetLocalSlice({
    required List<Offset> sheetLocalPolygon,
    required Size pageSize,
    required double left,
    required double width,
  }) {
    if (sheetLocalPolygon.length < 3 || width <= 0.001) {
      return const <Offset>[];
    }
    var clipped = List<Offset>.of(sheetLocalPolygon);
    final right = left + width;
    clipped = clipPolygonByLine(
      polygon: clipped,
      line: (Offset(left, 0), Offset(left, pageSize.height)),
      keepPositiveSide: false,
    );
    clipped = clipPolygonByLine(
      polygon: clipped,
      line: (Offset(right, 0), Offset(right, pageSize.height)),
      keepPositiveSide: true,
    );
    clipped = clipPolygonByLine(
      polygon: clipped,
      line: (Offset(0, 0), Offset(pageSize.width, 0)),
      keepPositiveSide: true,
    );
    return clipPolygonByLine(
      polygon: clipped,
      line: (
        Offset(0, pageSize.height),
        Offset(pageSize.width, pageSize.height),
      ),
      keepPositiveSide: false,
    );
  }

  Rect _backwardPageRect(StPageFlipScene scene) {
    return resolveBookPageRect(scene.layout, isRightPage: true);
  }

  List<Offset> _resolveDynamicLayerPolygon({
    required List<Offset>? area,
    required Offset? anchor,
    required double angle,
    required StPageFlipDirection? direction,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
  }) {
    return _resolveDynamicLayerGeometry(
          area: area,
          anchor: anchor,
          angle: angle,
          direction: direction,
          bounds: bounds,
          isFlippingPage: isFlippingPage,
        )?.viewportClipPolygon ??
        const <Offset>[];
  }

  Rect? _resolveDynamicLayerBounds({
    required List<Offset>? area,
    required Offset? anchor,
    required double angle,
    required StPageFlipDirection? direction,
    required StPageFlipBoundsRect bounds,
    required bool isFlippingPage,
  }) {
    final polygon = _resolveDynamicLayerPolygon(
      area: area,
      anchor: anchor,
      angle: angle,
      direction: direction,
      bounds: bounds,
      isFlippingPage: isFlippingPage,
    );
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

  double? _resolveBackwardSeamGuideX({
    required Rect pageRect,
    required StPageFlipRenderFrame? renderFrame,
    required StPageFlipCalculation? calculation,
  }) {
    if (renderFrame?.flippingClipArea case final area?) {
      final seamX = area.fold<double>(
        0,
        (current, point) => math.max(current, point.dx),
      );
      return pageRect.left + seamX;
    }
    if (calculation is StPageFlipCalculation) {
      return pageRect.left + calculation.backwardSeamX;
    }
    return null;
  }

  StPageFlipDirection? _sceneRenderDirection(StPageFlipScene scene) {
    return scene.effectiveRenderDirection ?? scene.direction;
  }

  StPageFlipShadowData? _sceneShadow(StPageFlipScene scene) {
    return scene.renderFrame?.shadow ?? scene.shadow;
  }

  ArticleFlipPipelineOutput? _resolveArticleFlipPipelineOutput(
    StPageFlipScene scene, {
    required Set<int> dynamicallyRenderedPages,
  }) {
    final renderFrame = scene.renderFrame;
    final direction = _sceneRenderDirection(scene);
    if (renderFrame == null || direction == null) {
      return null;
    }
    final modeLayout = _articleReaderModeStrategy.resolveLayout(
      scene: scene,
      dynamicallyRenderedPages: dynamicallyRenderedPages,
    );
    final textureBinding = _textureBindingForScene(scene);
    final input = ArticleFlipPipelineInput(
      scene: scene,
      renderFrame: renderFrame,
      pageSize: Size(scene.layout.bounds.pageWidth, scene.layout.bounds.height),
      modeLayout: modeLayout,
      textureBinding: textureBinding,
      textureBundle: null,
    );
    final pipeline = switch (direction) {
      StPageFlipDirection.forward => _forwardFlipPipeline,
      StPageFlipDirection.back => _backwardFlipPipeline,
    };
    final output = pipeline.resolve(input);
    // Keep the mapper on the hot path so diagnostics evolve from pipeline
    // output instead of from ad hoc renderer branches.
    _articleReaderDebugMapper.mapPipelineOutput(output: output, input: input);
    return output;
  }

  String _sceneSignature(StPageFlipScene scene) {
    final renderFrame = scene.renderFrame;
    return <Object?>[
      scene.state.name,
      scene.currentSpreadIndex,
      scene.currentPageIndex,
      scene.visibleSpread.leftPageIndex,
      scene.visibleSpread.rightPageIndex,
      scene.flippingPageIndex,
      scene.bottomPageIndex,
      scene.direction?.name,
      scene.effectiveRenderDirection?.name,
      renderFrame?.progress.toStringAsFixed(4),
      renderFrame?.corner.name,
    ].join('|');
  }
}
