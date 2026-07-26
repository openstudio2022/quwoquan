part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckDiagnosticReporting
    on _ArticleReadOnlyBookDeckState {
  void _scheduleSceneReport(StPageFlipScene scene) {
    if (_deck.onSceneChanged == null) {
      return;
    }
    final signature = _sceneSignature(scene);
    if (signature == _lastReportedSceneSignature) {
      return;
    }
    _pendingReportedScene = scene;
    if (_sceneReportScheduled) {
      return;
    }
    _sceneReportScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _sceneReportScheduled = false;
      final nextScene = _pendingReportedScene;
      _pendingReportedScene = null;
      if (!_isMounted || nextScene == null) {
        return;
      }
      final nextSignature = _sceneSignature(nextScene);
      if (nextSignature == _lastReportedSceneSignature) {
        return;
      }
      _lastReportedSceneSignature = nextSignature;
      _deck.onSceneChanged?.call(nextScene);
    });
  }

  void _scheduleDebugStateReport(ArticleReadOnlyBookDebugState state) {
    if (_deck.onDebugStateChanged == null) {
      return;
    }
    if (state.signature == _lastReportedDebugSignature) {
      return;
    }
    _pendingReportedDebugState = state;
    if (_debugReportScheduled) {
      return;
    }
    _debugReportScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _debugReportScheduled = false;
      final nextState = _pendingReportedDebugState;
      _pendingReportedDebugState = null;
      if (!_isMounted || nextState == null) {
        return;
      }
      if (nextState.signature == _lastReportedDebugSignature) {
        return;
      }
      _lastReportedDebugSignature = nextState.signature;
      _deck.onDebugStateChanged?.call(nextState);
    });
  }

  double? _resolveDiagnosticGuideX({
    required Rect pageRect,
    required StPageFlipScene scene,
  }) {
    final renderFrame = scene.renderFrame;
    final backwardLeafFrame = renderFrame?.backwardLeafFrame;
    if (backwardLeafFrame != null) {
      return pageRect.left + pageRect.width * backwardLeafFrame.seamXNormalized;
    }
    if (renderFrame != null) {
      if (scene.direction == StPageFlipDirection.back) {
        return _resolveBackwardSeamGuideX(
          pageRect: pageRect,
          renderFrame: renderFrame,
          calculation: scene.calculation,
        );
      }
      return pageRect.left + renderFrame.timeline.basePivot;
    }
    final calculation = scene.calculation;
    if (calculation != null) {
      if (scene.direction == StPageFlipDirection.back) {
        return _resolveBackwardSeamGuideX(
          pageRect: pageRect,
          renderFrame: null,
          calculation: calculation,
        );
      }
      final position = calculation.getPosition();
      final normalizedX = scene.direction == StPageFlipDirection.back
          ? pageRect.width - position.dx.clamp(0.0, pageRect.width)
          : position.dx.clamp(0.0, pageRect.width);
      return pageRect.left + normalizedX;
    }
    return null;
  }

  BackwardVersoFailureReason _resolveBackwardVersoFailureReason({
    required StPageFlipDirection? direction,
    required ArticlePageTextureBinding? requestedBinding,
    required ArticlePageTextureSnapshot? activeVersoSnapshot,
    required List<Offset> backwardBackLocalPolygon,
    required List<Offset> sheetMaterialLocalPolygon,
    required Size pageSize,
    required BackwardVersoPixelProbe probe,
  }) {
    if (direction != StPageFlipDirection.back) {
      return BackwardVersoFailureReason.none;
    }
    if (requestedBinding?.versoPageIndex != null &&
        activeVersoSnapshot == null) {
      return BackwardVersoFailureReason.snapshotUnavailable;
    }
    if (activeVersoSnapshot != null &&
        activeVersoSnapshot.semanticSurfaceKind !=
            ArticlePageSurfaceKind.back.name) {
      return BackwardVersoFailureReason.snapshotWrongSource;
    }
    if (backwardBackLocalPolygon.length < 3) {
      return BackwardVersoFailureReason.versoPolygonEmpty;
    }
    if (buildBackwardLeafVersoMaterialUvMesh(
          pageSize: pageSize,
          materialLocalPolygon: sheetMaterialLocalPolygon,
        ) ==
        null) {
      return BackwardVersoFailureReason.meshDegenerate;
    }
    if (probe.isEmpty) {
      return BackwardVersoFailureReason.samplePointOutsideBand;
    }
    return BackwardVersoFailureReason.none;
  }

  BackwardGeometryFailureReason _resolveBackwardGeometryFailureReason({
    required StPageFlipDirection? direction,
    required ArticlePageTextureBinding? requestedBinding,
    required ArticlePageTextureSnapshot? activeVersoSnapshot,
    required _BackwardDiagnosticGeometry? backwardDiagnosticGeometry,
    required List<Offset> backwardBackLocalPolygon,
    required Rect? backwardBackBounds,
    required Rect? backwardFrontBounds,
    required Rect? backwardCurrentResidualBounds,
    required (Offset, Offset)? backwardFoldLine,
    required (Offset, Offset)? backwardPageEdgeLine,
    required ArticlePageBackwardLeafFrame? backwardLeafFrame,
    required Rect pageRect,
    required Size pageSize,
    required BackwardVersoPixelProbe probe,
  }) {
    if (direction != StPageFlipDirection.back) {
      return BackwardGeometryFailureReason.none;
    }
    if (requestedBinding?.versoPageIndex != null &&
        activeVersoSnapshot == null) {
      return BackwardGeometryFailureReason.snapshotUnavailable;
    }
    final clipBounds = backwardDiagnosticGeometry?.sheetLocalBounds;
    if (clipBounds == null || clipBounds.width <= 1 || clipBounds.height <= 1) {
      return BackwardGeometryFailureReason.clipAreaDegenerate;
    }
    final edgeParallelToFold =
        backwardFoldLine == null || backwardPageEdgeLine == null
        ? false
        : linesAreParallel(backwardFoldLine, backwardPageEdgeLine);
    if (edgeParallelToFold &&
        (backwardBackBounds == null ||
            backwardBackBounds.width <= math.max(8.0, pageRect.width * 0.02) ||
            backwardBackLocalPolygon.length < 3)) {
      return BackwardGeometryFailureReason.foldFreeEdgeParallelButCollapsed;
    }
    if (backwardBackLocalPolygon.length < 3) {
      return BackwardGeometryFailureReason.versoPolygonEmpty;
    }
    if (buildBackwardLeafVersoMaterialUvMesh(
          pageSize: pageSize,
          materialLocalPolygon:
              backwardDiagnosticGeometry?.sheetMaterialLocalPolygon ??
              const <Offset>[],
        ) ==
        null) {
      return BackwardGeometryFailureReason.meshDegenerate;
    }
    if (backwardBackBounds == null ||
        backwardBackBounds.right <= pageRect.left ||
        backwardBackBounds.left >= pageRect.right) {
      return BackwardGeometryFailureReason.bandOutsideVisiblePage;
    }
    if (backwardCurrentResidualBounds == null ||
        backwardCurrentResidualBounds.isEmpty ||
        backwardCurrentResidualBounds.width <= 1) {
      return BackwardGeometryFailureReason.currentResidualLost;
    }
    if (probe.isEmpty) {
      return BackwardGeometryFailureReason.samplePointOutsideBand;
    }
    return BackwardGeometryFailureReason.none;
  }

  ArticleReadOnlyBookDebugState _buildDiagnosticDebugState({
    required StPageFlipScene scene,
    required Rect pageRect,
    required ArticleReadOnlyBookRenderBranch renderBranch,
  }) {
    final direction = _sceneRenderDirection(scene);
    final renderFrame = scene.renderFrame;
    final backwardDiagnosticGeometry = _resolveBackwardDiagnosticGeometry(
      scene,
    );
    final backwardPageRect = _backwardPageRect(scene);
    final diagnosticBottomArea =
        renderFrame?.bottomClipArea ?? scene.calculation?.getBottomClipArea();
    final diagnosticFlippingArea =
        renderFrame?.flippingClipArea ??
        scene.calculation?.getFlippingClipArea();
    final requestedBinding = _textureBindingForScene(scene);
    final backwardBinding = _backwardSurfaceBindingForScene(scene);
    final backwardLeafFrame = _resolveBackwardLeafFrame(scene);
    final backwardDynamicOwnedPageSet = _resolveBackwardDynamicOwnedPageSet(
      scene,
    );
    final dynamicBottomBounds = _resolveDynamicLayerBounds(
      area: diagnosticBottomArea,
      anchor:
          renderFrame?.bottomAnchor ??
          scene.calculation?.getBottomPagePosition(),
      angle: 0,
      direction: direction,
      bounds: scene.layout.bounds,
      isFlippingPage: false,
    );
    final dynamicFlippingBounds =
        direction == StPageFlipDirection.back &&
            backwardDiagnosticGeometry != null
        ? backwardDiagnosticGeometry.sheetViewportBounds
        : _resolveDynamicLayerBounds(
            area: diagnosticFlippingArea,
            anchor:
                renderFrame?.flippingAnchor ??
                scene.calculation?.getActiveCorner(),
            angle: renderFrame?.angle ?? scene.calculation?.getAngle() ?? 0,
            direction: direction,
            bounds: scene.layout.bounds,
            isFlippingPage: true,
          );
    final dynamicFlippingGeometry =
        direction == StPageFlipDirection.back &&
            backwardDiagnosticGeometry != null
        ? null
        : _resolveDynamicLayerGeometry(
            area: diagnosticFlippingArea,
            anchor:
                renderFrame?.flippingAnchor ??
                scene.calculation?.getActiveCorner(),
            angle: renderFrame?.angle ?? scene.calculation?.getAngle() ?? 0,
            direction: direction,
            bounds: scene.layout.bounds,
            isFlippingPage: true,
          );
    final backwardFoldLine = backwardDiagnosticGeometry?.foldLineViewport;
    final backwardPageEdgeLine =
        backwardDiagnosticGeometry?.freeEdgeLineViewport;
    final backwardFoldSurfaceEdgeLine =
        backwardDiagnosticGeometry?.freeEdgeLineViewport;
    final backwardSurfaceAngle =
        renderFrame?.angle ?? scene.calculation?.getAngle();
    final backwardSurfaceShowsBack =
        direction == StPageFlipDirection.back && backwardSurfaceAngle != null
        ? backwardSurfaceAngle.abs() <= math.pi / 2
        : false;
    final backwardFoldDirection =
        direction == StPageFlipDirection.back && backwardSurfaceAngle != null
        ? (backwardSurfaceAngle >= 0 ? 'leftward' : 'rightward')
        : null;

    final backwardMovingPaintBounds =
        dynamicFlippingBounds ??
        dynamicFlippingGeometry?.clipViewportBounds ??
        dynamicFlippingGeometry?.surfaceViewportRect;
    final backwardFoldSurfaceBounds = _intersectNonEmptyRects(
      backwardMovingPaintBounds,
      pageRect,
    );

    final backBoundsViewport =
        backwardDiagnosticGeometry?.previousBackViewportBounds ??
        (backwardSurfaceShowsBack ? backwardFoldSurfaceBounds : null);
    final backwardBackFoldBounds = backBoundsViewport;
    final frontBoundsViewport =
        backwardDiagnosticGeometry?.previousFrontViewportBounds;
    final backwardFrontFoldVisible = frontBoundsViewport != null;
    final backwardFrontFoldBounds = backwardFrontFoldVisible
        ? frontBoundsViewport
        : null;
    final backwardFoldFrontBounds = backwardFrontFoldBounds;
    final backwardBackBounds = backwardBackFoldBounds;
    final backwardFrontBounds = backwardFoldFrontBounds;
    final backwardCurrentResidualBounds =
        backwardDiagnosticGeometry?.currentResidualViewportBounds ??
        backwardPageRect;
    final backwardMainline = direction == StPageFlipDirection.back
        ? 'paperFoldBackMainline'
        : null;
    final backwardFlippingSheetCount =
        direction == StPageFlipDirection.back &&
            renderBranch == ArticleReadOnlyBookRenderBranch.paperFoldDynamic &&
            scene.flippingPageIndex != null
        ? 1
        : null;
    final backwardLeafSheetId =
        direction == StPageFlipDirection.back && scene.flippingPageIndex != null
        ? 'mainlineLeaf:${scene.flippingPageIndex}'
        : null;
    final backwardFrontSheetId = backwardFrontFoldVisible
        ? 'laidFront:${scene.flippingPageIndex}'
        : null;
    final backwardBackSheetId = direction == StPageFlipDirection.back
        ? backwardLeafSheetId
        : null;
    final backwardCurrentLayerPresent = direction == StPageFlipDirection.back
        ? true
        : null;
    final backwardMultiSliceViolation = direction == StPageFlipDirection.back
        ? backwardFlippingSheetCount != 1
        : null;
    List<Offset> rectToPolygon(Rect? rect) {
      if (rect == null || rect.isEmpty) {
        return const <Offset>[];
      }
      return <Offset>[
        rect.topLeft,
        rect.topRight,
        rect.bottomRight,
        rect.bottomLeft,
      ];
    }

    final backwardLocalClipPolygon =
        backwardDiagnosticGeometry?.sheetLocalPolygon ??
        dynamicFlippingGeometry?.localClipPolygon ??
        const <Offset>[];
    final backwardBackLocalPolygon =
        backwardDiagnosticGeometry?.previousBackLocalPolygon ??
        backwardLocalClipPolygon;
    final backwardFrontLocalPolygon =
        backwardDiagnosticGeometry?.previousFrontLocalPolygon ??
        const <Offset>[];
    final backwardCurrentResidualPolygon =
        backwardDiagnosticGeometry?.currentResidualViewportPolygon ??
        rectToPolygon(backwardCurrentResidualBounds);
    BackwardPaintSourceDiagnostic sourceDiagnostic({
      required String label,
      required int zOrder,
      required int? pageIndex,
      required ArticlePageSurfaceKind surfaceKind,
      String status = 'visible',
      required Rect? viewportBounds,
      required List<Offset> viewportPolygon,
    }) {
      return BackwardPaintSourceDiagnostic(
        label: label,
        zOrder: zOrder,
        pageIndex: pageIndex,
        surfaceKind: surfaceKind.name,
        status: status,
        viewportBounds: viewportBounds,
        polygonSignature: articleDiagnosticPolygonSignature(viewportPolygon),
        viewportPolygon: List<Offset>.unmodifiable(viewportPolygon),
      );
    }

    final visibleFrontViewportPolygon =
        backwardDiagnosticGeometry?.previousFrontViewportPolygon ??
        const <Offset>[];
    final visibleFrontViewportBounds = polygonBounds(
      visibleFrontViewportPolygon,
    );
    final visibleBackViewportPolygon =
        backwardDiagnosticGeometry?.previousBackViewportPolygon ??
        const <Offset>[];
    final visibleBackViewportBounds = polygonBounds(visibleBackViewportPolygon);
    final paintedUnionViewportPolygon =
        backwardDiagnosticGeometry?.paintedUnionViewportPolygon ??
        const <Offset>[];
    final paintedUnionViewportBounds = polygonBounds(
      paintedUnionViewportPolygon,
    );

    final backwardPaintSources = direction == StPageFlipDirection.back
        ? <BackwardPaintSourceDiagnostic>[
            sourceDiagnostic(
              label: 'staticCurrentFront',
              zOrder: 1,
              pageIndex: scene.currentPageIndex,
              surfaceKind: ArticlePageSurfaceKind.front,
              viewportBounds: pageRect,
              viewportPolygon: rectToPolygon(pageRect),
            ),
            if (visibleFrontViewportBounds != null)
              sourceDiagnostic(
                label: 'previousFrontReplacement',
                zOrder: 2,
                pageIndex: scene.flippingPageIndex,
                surfaceKind: ArticlePageSurfaceKind.front,
                status: 'pageSpaceReplacement',
                viewportBounds: visibleFrontViewportBounds,
                viewportPolygon: visibleFrontViewportPolygon,
              ),
            if (dynamicBottomBounds != null)
              sourceDiagnostic(
                label: 'bottomCurrentFront',
                zOrder: 3,
                pageIndex: scene.bottomPageIndex,
                surfaceKind: ArticlePageSurfaceKind.bottom,
                viewportBounds: dynamicBottomBounds,
                viewportPolygon: backwardCurrentResidualPolygon,
              ),
            if (paintedUnionViewportBounds != null)
              sourceDiagnostic(
                label: 'sheetPaintedUnion',
                zOrder: 5,
                pageIndex: scene.flippingPageIndex,
                surfaceKind: ArticlePageSurfaceKind.back,
                status: 'coverage',
                viewportBounds: paintedUnionViewportBounds,
                viewportPolygon: paintedUnionViewportPolygon,
              ),
            if (visibleBackViewportBounds != null)
              sourceDiagnostic(
                label: 'sheetVersoBack',
                zOrder: 6,
                pageIndex: scene.flippingPageIndex,
                surfaceKind: ArticlePageSurfaceKind.back,
                status: 'visible',
                viewportBounds: visibleBackViewportBounds,
                viewportPolygon: visibleBackViewportPolygon,
              ),
            if (backwardFoldLine != null)
              sourceDiagnostic(
                label: 'foldOverlay',
                zOrder: 7,
                pageIndex: scene.flippingPageIndex,
                surfaceKind: ArticlePageSurfaceKind.back,
                viewportBounds: Rect.fromPoints(
                  backwardFoldLine.$1,
                  backwardFoldLine.$2,
                ).inflate(2),
                viewportPolygon: <Offset>[
                  backwardFoldLine.$1,
                  backwardFoldLine.$2,
                ],
              ),
          ]
        : const <BackwardPaintSourceDiagnostic>[];
    final backwardPageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final activeVersoSnapshot = requestedBinding?.versoPageIndex == null
        ? null
        : _peekBackPageTextureSnapshotForIndex(
            requestedBinding!.versoPageIndex,
            expectedSize: backwardPageSize,
          );
    final backwardVersoProbe = resolveBackwardVersoPixelProbe(
      pageSize: backwardPageSize,
      polygon: backwardBackLocalPolygon,
      materialLocalPolygon:
          backwardDiagnosticGeometry?.sheetMaterialLocalPolygon ??
          const <Offset>[],
    );
    final backwardVersoProbeViewportPoints = backwardDiagnosticGeometry == null
        ? const <Offset>[]
        : backwardVersoProbe.localPoints
              .map(
                (point) => transformSoftLayerLocalPoint(
                  point: point,
                  geometry: backwardDiagnosticGeometry.softGeometry,
                ),
              )
              .toList(growable: false);
    final backwardFrontBackOverlap = direction == StPageFlipDirection.back
        ? _intersectNonEmptyRects(backwardFrontBounds, backwardBackBounds)
        : null;
    final backwardFrontBackOverlapWidth = backwardFrontBackOverlap?.width;
    final backwardVisibleBackProbePoints = direction == StPageFlipDirection.back
        ? backwardVersoProbeViewportPoints
              .where((point) {
                final backPolygon =
                    backwardDiagnosticGeometry?.previousBackViewportPolygon ??
                    const <Offset>[];
                if (!_polygonContainsPoint(
                  polygon: backPolygon,
                  point: point,
                )) {
                  return false;
                }
                return true;
              })
              .toList(growable: false)
        : const <Offset>[];
    final backwardBackVisibleUncoveredWidth = backwardBackBounds == null
        ? null
        : backwardVisibleBackProbePoints.isEmpty
        ? 0.0
        : polygonBounds(backwardVisibleBackProbePoints)?.width ??
              backwardBackBounds.width;
    final backwardBackVisibleProbeCount = backwardBackBounds == null
        ? null
        : backwardVisibleBackProbePoints.length;
    final isBackwardDynamic =
        direction == StPageFlipDirection.back &&
        renderBranch == ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    final activeRectoPageIndex = isBackwardDynamic
        ? requestedBinding?.rectoPageIndex
        : null;
    final activeBottomPageIndex = isBackwardDynamic
        ? requestedBinding?.bottomPageIndex
        : null;
    final activeVersoPageIndex =
        activeVersoSnapshot == null || !isBackwardDynamic
        ? null
        : requestedBinding?.versoPageIndex;
    final sessionHasBundle = isBackwardDynamic && activeVersoSnapshot != null;
    final renderSceneReady = isBackwardDynamic && sessionHasBundle;
    final backwardVersoDisplayState = direction != StPageFlipDirection.back
        ? null
        : requestedBinding?.versoPageIndex == null
        ? 'notRequested'
        : backwardBackBounds == null || backwardBackBounds.isEmpty
        ? activeVersoSnapshot == null
              ? 'waitingForSnapshot'
              : 'semanticSnapshotHidden'
        : activeVersoSnapshot == null
        ? 'paperFallback'
        : 'semanticSnapshot';
    final backwardPaintSourcesWithRuntimeStatus =
        direction == StPageFlipDirection.back
        ? backwardPaintSources
              .map((source) {
                if (source.label != 'sheetVersoBack') {
                  return source;
                }
                return BackwardPaintSourceDiagnostic(
                  label: source.label,
                  zOrder: source.zOrder,
                  pageIndex: source.pageIndex,
                  surfaceKind: source.surfaceKind,
                  status: backwardVersoDisplayState ?? source.status,
                  viewportBounds: source.viewportBounds,
                  polygonSignature: source.polygonSignature,
                  viewportPolygon: source.viewportPolygon,
                );
              })
              .toList(growable: false)
        : backwardPaintSources;
    final backwardVersoFailureReason = _resolveBackwardVersoFailureReason(
      direction: direction,
      requestedBinding: requestedBinding,
      activeVersoSnapshot: activeVersoSnapshot,
      backwardBackLocalPolygon: backwardBackLocalPolygon,
      sheetMaterialLocalPolygon:
          backwardDiagnosticGeometry?.sheetMaterialLocalPolygon ??
          const <Offset>[],
      pageSize: backwardPageSize,
      probe: backwardVersoProbe,
    );
    final backwardGeometryFailureReason = _resolveBackwardGeometryFailureReason(
      direction: direction,
      requestedBinding: requestedBinding,
      activeVersoSnapshot: activeVersoSnapshot,
      backwardDiagnosticGeometry: backwardDiagnosticGeometry,
      backwardBackLocalPolygon: backwardBackLocalPolygon,
      backwardBackBounds: backwardBackBounds,
      backwardFrontBounds: backwardFrontBounds,
      backwardCurrentResidualBounds: backwardCurrentResidualBounds,
      backwardFoldLine: backwardFoldLine,
      backwardPageEdgeLine: backwardPageEdgeLine,
      backwardLeafFrame: backwardLeafFrame,
      pageRect: pageRect,
      pageSize: backwardPageSize,
      probe: backwardVersoProbe,
    );
    double? normalizedLineX(Offset top, Offset bottom) {
      if (pageRect.width <= 0) {
        return null;
      }
      return ((((top.dx + bottom.dx) / 2) - pageRect.left) / pageRect.width)
          .clamp(0.0, 1.0)
          .toDouble();
    }

    return ArticleReadOnlyBookDebugState(
      currentPageIndex: scene.currentPageIndex,
      turningPageIndex: scene.flippingPageIndex,
      underlayPageIndex: scene.bottomPageIndex,
      coveredPageIndex: scene.currentPageIndex,
      leftPageIndex: scene.visibleSpread.leftPageIndex,
      rightPageIndex: scene.visibleSpread.rightPageIndex,
      renderBranch: renderBranch,
      renderDirection: _sceneRenderDirection(scene),
      renderSceneReady: renderSceneReady,
      sessionHasBundle: sessionHasBundle,
      requestedRectoPageIndex: requestedBinding?.rectoPageIndex,
      requestedVersoPageIndex: requestedBinding?.versoPageIndex,
      requestedBottomPageIndex: requestedBinding?.bottomPageIndex,
      activeRectoPageIndex: activeRectoPageIndex,
      activeVersoPageIndex: activeVersoPageIndex,
      activeBottomPageIndex: activeBottomPageIndex,
      activeVersoSurfaceKind: activeVersoSnapshot?.semanticSurfaceKind,
      backwardVersoDisplayState: backwardVersoDisplayState,
      backwardVersoFailureReason: backwardVersoFailureReason,
      backwardGeometryFailureReason: backwardGeometryFailureReason,
      backwardVersoProbeLocalPoints: backwardVersoProbe.localPoints,
      backwardVersoProbeTexturePoints: backwardVersoProbe.texturePoints,
      backwardVersoProbeViewportPoints: backwardVersoProbeViewportPoints,
      backwardBackLocalPolygonRaw: backwardBackLocalPolygon,
      backwardCoveredPageIndex: backwardBinding?.coveredPageIndex,
      backwardLeafRectoPageIndex: backwardBinding?.leafRectoPageIndex,
      backwardLeafVersoPageIndex: backwardBinding?.leafVersoPageIndex,
      availableSnapshotIndices: _pageTextureSnapshots.keys.toList()..sort(),
      pendingCaptureIndices: _pendingTextureCaptureIndices.toList(
        growable: false,
      ),
      bottomClipBounds: dynamicBottomBounds,
      flippingClipBounds: dynamicFlippingBounds,
      frontBounds: direction == StPageFlipDirection.back
          ? backwardFrontBounds
          : null,
      backBounds: direction == StPageFlipDirection.back
          ? backwardBackBounds
          : null,
      flippingAnchor:
          renderFrame?.flippingAnchor ?? scene.calculation?.getActiveCorner(),
      bottomAnchor:
          renderFrame?.bottomAnchor ??
          scene.calculation?.getBottomPagePosition(),
      backwardCorner: _resolveBackwardCornerLabel(scene),
      backwardHinge: _resolveBackwardHinge(
        scene: scene,
        pageSize: pageRect.size,
      ),
      backwardSpineTop: _resolveBackwardSpineTop(scene),
      backwardSpineBottom: _resolveBackwardSpineBottom(
        scene: scene,
        pageSize: pageRect.size,
      ),
      backwardSeamX: _resolveBackwardSeamX(scene),
      backwardFoldX: backwardFoldLine == null
          ? null
          : ((backwardFoldLine.$1.dx + backwardFoldLine.$2.dx) / 2) -
                pageRect.left,
      backwardPageEdgeX: backwardPageEdgeLine == null
          ? null
          : ((backwardPageEdgeLine.$1.dx + backwardPageEdgeLine.$2.dx) / 2) -
                pageRect.left,
      backwardFoldSurfaceEdgeX: backwardFoldSurfaceEdgeLine == null
          ? null
          : ((backwardFoldSurfaceEdgeLine.$1.dx +
                        backwardFoldSurfaceEdgeLine.$2.dx) /
                    2) -
                pageRect.left,
      backwardFoldLineTop: backwardFoldLine?.$1,
      backwardFoldLineBottom: backwardFoldLine?.$2,
      backwardPageEdgeLineTop: backwardPageEdgeLine?.$1,
      backwardPageEdgeLineBottom: backwardPageEdgeLine?.$2,
      backwardFoldSurfaceEdgeLineTop: backwardFoldSurfaceEdgeLine?.$1,
      backwardFoldSurfaceEdgeLineBottom: backwardFoldSurfaceEdgeLine?.$2,
      backwardCoveredWidth: backwardFoldLine == null
          ? backwardLeafFrame?.coveredWidthNormalized
          : normalizedLineX(backwardFoldLine.$1, backwardFoldLine.$2),
      backwardRectoCoverage: backwardLeafFrame?.rectoCoverageNormalized,
      backwardVersoWidth: backwardLeafFrame?.versoRevealWidthNormalized,
      backwardRectoWidth: backwardLeafFrame?.totalRectoVisibleWidthNormalized,
      backwardBottomStart: backwardLeafFrame?.bottomRevealStartNormalized,
      backwardPhase: _resolveBackwardPhaseLabel(scene),
      backwardReplayFrontLayerCount: direction == StPageFlipDirection.back
          ? (backwardFrontFoldVisible ? 1 : 0)
          : _resolveBackwardReplayFrontLayerCount(scene),
      backwardReplayBackSurfaceStrategy:
          _resolveBackwardReplayBackSurfaceStrategy(scene),
      backwardBottomLayerPageIndex: direction == StPageFlipDirection.back
          ? scene.bottomPageIndex
          : null,
      backwardFlippingLayerPageIndex: direction == StPageFlipDirection.back
          ? scene.flippingPageIndex
          : null,
      backwardDynamicOwnedPages: _sortedPageIndices(
        backwardDynamicOwnedPageSet,
      ),
      backwardStaticSuppressedPages: _resolveBackwardStaticSuppressedPages(
        scene: scene,
        dynamicOwnedPages: backwardDynamicOwnedPageSet,
      ),
      backwardReplaySlices: direction == StPageFlipDirection.back
          ? 'route=paperFoldBackwardMainline/mainline=paperFoldBackMainline/flipping=singleTurningSheet/frontEnabled=$backwardFrontFoldVisible/currentLayerPresent=${backwardCurrentLayerPresent ?? false}/multiSliceViolation=${backwardMultiSliceViolation ?? true}'
          : _resolveBackwardReplaySliceLabel(
              backwardLeafFrame,
              scene,
              pageRect: pageRect,
              frontPaintBounds: backwardFrontBounds,
              backPaintBounds: backwardBackBounds,
              surfaceAngle: backwardSurfaceAngle,
              flippingSheetCount: backwardFlippingSheetCount ?? 0,
              frontSheetId: backwardFrontSheetId,
              backSheetId: backwardBackSheetId,
              currentLayerPresent: backwardCurrentLayerPresent ?? false,
              multiSliceViolation: backwardMultiSliceViolation ?? true,
            ),
      backwardCompositeMode: _hasBackwardPaperFoldFrame(scene)
          ? 'paperFoldBackwardMainline'
          : null,
      backwardFrontPaintBounds: backwardFrontBounds,
      backwardBackPaintBounds: backwardBackBounds,
      backwardLaidFrontPaintBounds: backwardFrontBounds,
      backwardFoldSurfacePaintBounds: backwardFoldSurfaceBounds,
      backwardCurrentResidualBounds: backwardCurrentResidualBounds,
      backwardMainline: backwardMainline,
      backwardFlippingSheetCount: backwardFlippingSheetCount,
      backwardFrontSheetId: backwardFrontSheetId,
      backwardBackSheetId: backwardBackSheetId,
      backwardCurrentLayerPresent: backwardCurrentLayerPresent,
      backwardMultiSliceViolation: backwardMultiSliceViolation,
      backwardPaintedVersoWidth: backwardLeafFrame?.versoRevealWidthNormalized,
      backwardBackPixelSurfaceStrategy: _hasBackwardPaperFoldFrame(scene)
          ? 'paperFoldBackMainlineSurface'
          : null,
      backwardVersoTextureUvStrategy: _hasBackwardPaperFoldFrame(scene)
          ? 'materialLockedUv'
          : null,
      backwardFrontBackOverlapWidth: backwardFrontBackOverlapWidth,
      backwardBackVisibleUncoveredWidth: backwardBackVisibleUncoveredWidth,
      backwardBackVisibleProbeCount: backwardBackVisibleProbeCount,
      backwardPaintSources: backwardPaintSourcesWithRuntimeStatus,
      backwardSurfaceOrigin: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.softGeometry.surfaceOrigin
          : null,
      backwardSurfaceViewportRect: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.softGeometry.surfaceViewportRect
          : null,
      backwardPivotLocal: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.softGeometry.pivotLocal
          : null,
      backwardPivotViewport: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry == null
                ? null
                : transformSoftLayerLocalPoint(
                    point: backwardDiagnosticGeometry.softGeometry.pivotLocal,
                    geometry: backwardDiagnosticGeometry.softGeometry,
                  )
          : null,
      backwardClipLocalBounds: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.sheetLocalBounds
          : null,
      backwardClipViewportBounds: direction == StPageFlipDirection.back
          ? backwardDiagnosticGeometry?.sheetViewportBounds
          : null,
      backwardFrontCoverageRatio: backwardLeafFrame?.rectoCoverageNormalized,
      backwardLeftSpineLocked:
          direction == StPageFlipDirection.back &&
              backwardDiagnosticGeometry?.sheetLocalBounds != null
          ? (backwardDiagnosticGeometry!.sheetLocalBounds!.left).abs() <= 1.0
          : (backwardPageEdgeLine == null
                ? null
                : (normalizedLineX(
                            backwardPageEdgeLine.$1,
                            backwardPageEdgeLine.$2,
                          ) ??
                          0) <=
                      0.005),
      backwardSimulatorVisualPhase: _resolveBackwardSimulatorVisualPhase(
        backwardLeafFrame,
      ),
      backwardEdgeEnteredPage: direction == StPageFlipDirection.back
          ? backBoundsViewport != null
          : null,
      backwardOverlayClippedToPaper: direction == StPageFlipDirection.back
          ? !_deck.debugPureBackwardGeometry && backBoundsViewport != null
          : null,
      backwardBackVertexCount: backwardBackLocalPolygon.length >= 3
          ? backwardBackLocalPolygon.length
          : null,
      backwardFrontVertexCount: backwardFrontLocalPolygon.length >= 3
          ? backwardFrontLocalPolygon.length
          : null,
      backwardEdgeParallelToFold:
          backwardFoldLine == null || backwardPageEdgeLine == null
          ? null
          : linesAreParallel(backwardFoldLine, backwardPageEdgeLine),
      backwardBackPolygonPoints: backwardBackLocalPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardBackLocalPolygon)
          : null,
      backwardFrontPolygonPoints: backwardFrontLocalPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardFrontLocalPolygon)
          : null,
      backwardSheetPolygonPoints: backwardLocalClipPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardLocalClipPolygon)
          : null,
      backwardBottomClipPolygonPoints:
          diagnosticBottomArea != null && diagnosticBottomArea.length >= 3
          ? articleDiagnosticPolygonSignature(diagnosticBottomArea)
          : null,
      backwardCurrentPolygonPoints: backwardCurrentResidualPolygon.length >= 3
          ? articleDiagnosticPolygonSignature(backwardCurrentResidualPolygon)
          : null,
      backwardFoldDirection: backwardFoldDirection,
      guideX: _resolveDiagnosticGuideX(pageRect: pageRect, scene: scene),
    );
  }
}
