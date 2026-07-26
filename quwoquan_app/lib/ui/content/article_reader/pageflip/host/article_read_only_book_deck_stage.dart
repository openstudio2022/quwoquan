part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckStage on _ArticleReadOnlyBookDeckState {
  Widget _buildStageBackdrop(
    BuildContext context, {
    required Rect pageRect,
    required double progress,
    required ArticlePageCurlCorner? activeCorner,
  }) {
    final palette = resolveArticleTemplatePalette(context, _deck.template);
    if (_usesImmersivePresentation) {
      final paperPalette = _deck.paperTexture != null
          ? resolveArticlePaperPalette(context, _deck.paperTexture!)
          : palette;
      return ColoredBox(color: paperPalette.paperColor);
    }
    return RepaintBoundary(
      child: CustomPaint(
        painter: ArticleReaderStagePainter(
          palette: palette,
          pageRect: pageRect,
          pageCount: _deck.pages.length,
          activeCorner: activeCorner,
          progress: progress,
        ),
      ),
    );
  }

  Widget _buildDegradedReaderStage(
    BuildContext context,
    Rect pageRect,
    Size stageSize,
  ) {
    return Listener(
      behavior: HitTestBehavior.translucent,
      onPointerDown: (event) => _handleBoundaryPanStart(event.localPosition),
      onPointerCancel: (_) => _resetBoundaryTracking(animate: true),
      child: AnimatedContainer(
        key: const ValueKey<String>('article-boundary-stage'),
        duration: _shouldAnimateBoundaryRubberBandReset
            ? _ArticleReadOnlyBookDeckState._boundaryRubberBandResetDuration
            : Duration.zero,
        curve: Curves.easeOutCubic,
        transform: Matrix4.translationValues(_boundaryRubberBandOffset, 0, 0),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            _buildStageBackdrop(
              context,
              pageRect: pageRect,
              progress: 0,
              activeCorner: null,
            ),
            NotificationListener<ScrollNotification>(
              onNotification: (notification) =>
                  _handleScrollNotification(notification, stageSize),
              child: PageView.builder(
                key: TestKeys.articleBookStylePager,
                controller: _pageController,
                itemCount: _deck.pages.length,
                onPageChanged: (index) {
                  final previousPage = _currentPage;
                  _setDeckState(() {
                    _currentPage = index;
                  });
                  _emitPageFlipCommit(fromPage: previousPage, toPage: index);
                  _deck.onPageChanged?.call(index);
                },
                itemBuilder: (context, index) {
                  return Align(
                    alignment: Alignment.topCenter,
                    child: Padding(
                      padding: EdgeInsets.only(top: pageRect.top),
                      child: _buildReaderPage(context, index, pageRect.size),
                    ),
                  );
                },
              ),
            ),
            if (!_usesImmersivePresentation)
              Positioned.fill(
                child: IgnorePointer(
                  child: CustomPaint(
                    painter: ArticleBookStylePagerHintPainter(
                      resolveArticleTemplatePalette(context, _deck.template),
                    ),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Widget _buildStaticBoundaryStage(
    BuildContext context,
    Rect pageRect,
    Size stageSize,
  ) {
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragDown: (details) =>
          _handleBoundaryPanStart(details.localPosition),
      onHorizontalDragUpdate: (details) =>
          _handleBoundaryPanUpdate(details.delta, stageSize),
      onHorizontalDragCancel: () => _resetBoundaryTracking(animate: true),
      onHorizontalDragEnd: (details) =>
          _finishBoundaryPan(details.velocity, stageSize),
      child: AnimatedContainer(
        key: const ValueKey<String>('article-boundary-stage'),
        duration: _shouldAnimateBoundaryRubberBandReset
            ? _ArticleReadOnlyBookDeckState._boundaryRubberBandResetDuration
            : Duration.zero,
        curve: Curves.easeOutCubic,
        transform: Matrix4.translationValues(_boundaryRubberBandOffset, 0, 0),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            _buildStageBackdrop(
              context,
              pageRect: pageRect,
              progress: 0,
              activeCorner: null,
            ),
            Align(
              alignment: Alignment.topCenter,
              child: Padding(
                padding: EdgeInsets.only(top: pageRect.top),
                child: _buildReaderPage(context, 0, pageRect.size),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _wrapInteractiveStageLayers(List<Widget> layers) {
    return ImmersivePointerGestureLayer(
      behavior: HitTestBehavior.translucent,
      onStart: (event) => _handleStagePointerDownPosition(event.localPosition),
      onUpdate: (event) {
        _handleStagePointerMovePosition(event.localPosition);
        if (_dragStartGlobalPosition == null &&
            _boundaryDragStartLocalPosition == null &&
            event.totalDelta.distance > 0) {
          _handleStagePanStart(event.startLocalPosition);
        }
        _handleStagePanUpdate(event.localPosition, event.delta);
      },
      onEnd: (event) {
        final hadPan =
            _dragStartGlobalPosition != null ||
            _boundaryDragStartLocalPosition != null ||
            _textureWarmupBlockedGesture;
        _handleStagePointerUpPosition(event.localPosition);
        if (hadPan) {
          _handleStagePanEnd(
            Velocity(pixelsPerSecond: Offset(event.velocityDx, 0)),
          );
        }
      },
      onCancel: (_) {
        final hadPan =
            _dragStartGlobalPosition != null ||
            _boundaryDragStartLocalPosition != null ||
            _textureWarmupBlockedGesture;
        _handleStagePointerCancelPosition();
        if (hadPan) {
          _handleStagePanCancel();
        }
      },
      child: MouseRegion(
        onHover: _handleStageMouseHover,
        onExit: _handleStageMouseExit,
        child: GestureDetector(
          behavior: HitTestBehavior.translucent,
          onTapUp: _handleStageTapUp,
          child: AnimatedContainer(
            key: const ValueKey<String>('article-boundary-stage'),
            duration: _shouldAnimateBoundaryRubberBandReset
                ? _ArticleReadOnlyBookDeckState._boundaryRubberBandResetDuration
                : Duration.zero,
            curve: Curves.easeOutCubic,
            transform: Matrix4.translationValues(
              _boundaryRubberBandOffset,
              0,
              0,
            ),
            child: Stack(fit: StackFit.expand, children: layers),
          ),
        ),
      ),
    );
  }

  Widget _buildInteractiveReaderStage(BuildContext context, Size stageSize) {
    _lastInteractiveStageSize = stageSize;
    _configurePageFlipController(stageSize);
    final scene = _pageFlipScene;
    if (scene == null) {
      return const SizedBox.shrink();
    }
    final pageSize = Size(
      scene.layout.bounds.pageWidth,
      scene.layout.bounds.height,
    );
    final bookRect = scene.layout.bounds.rect;
    final progress = _sceneProgress(scene);
    final direction = _sceneRenderDirection(scene);
    final pipelineOutput = _resolveArticleFlipPipelineOutput(
      scene,
      dynamicallyRenderedPages: const <int>{},
    );
    final paperFoldOwnedPages = direction == StPageFlipDirection.back
        ? (pipelineOutput?.staticSuppressionPages ??
              _resolveBackwardDynamicOwnedPageSet(scene))
        : const <int>{};
    final dynamicallyRenderedPages = <int>{...paperFoldOwnedPages};
    if (direction == null) {
      _queueStaticTextureSnapshots();
    }
    final layers = <Widget>[
      _buildPageTextureCaptureLayer(pageSize),
      _buildStageBackdrop(
        context,
        pageRect: bookRect,
        progress: progress,
        activeCorner: _stageCornerForScene(scene),
      ),
    ];

    final leftPageIndex = scene.visibleSpread.leftPageIndex;
    final rightPageIndex = scene.visibleSpread.rightPageIndex;
    if (leftPageIndex != null &&
        !dynamicallyRenderedPages.contains(leftPageIndex)) {
      layers.add(
        _buildStaticBookPage(
          context,
          leftPageIndex,
          resolveBookPageRect(scene.layout, isRightPage: false),
        ),
      );
    }
    if (rightPageIndex != null &&
        !dynamicallyRenderedPages.contains(rightPageIndex)) {
      layers.add(
        _buildStaticBookPage(
          context,
          rightPageIndex,
          resolveBookPageRect(scene.layout, isRightPage: true),
        ),
      );
    }

    final pageRect = resolveBookPageRect(scene.layout, isRightPage: true);
    ArticleReadOnlyBookRenderBranch renderBranch = direction == null
        ? ArticleReadOnlyBookRenderBranch.staticStage
        : ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    renderBranch = switch (direction) {
      StPageFlipDirection.back => _buildBackwardDynamicLayers(
        context: context,
        scene: scene,
        pageSize: pageSize,
        layers: layers,
      ),
      StPageFlipDirection.forward => _buildForwardDynamicLayers(
        context: context,
        scene: scene,
        pageSize: pageSize,
        direction: StPageFlipDirection.forward,
        layers: layers,
      ),
      null => ArticleReadOnlyBookRenderBranch.staticStage,
    };
    final debugState = _buildDiagnosticDebugState(
      scene: scene,
      pageRect: pageRect,
      renderBranch: renderBranch,
    );
    _scheduleSceneReport(scene);
    _scheduleDebugStateReport(debugState);

    layers.add(
      Positioned.fill(
        key: TestKeys.articlePageCurlLayer,
        child: _buildHotzoneMarkers(scene, stageSize),
      ),
    );
    return _wrapInteractiveStageLayers(layers);
  }
}
