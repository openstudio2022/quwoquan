part of 'article_read_only_book_deck.dart';

extension _ArticleReadOnlyBookDeckDynamicLayers
    on _ArticleReadOnlyBookDeckState {
  ArticleReadOnlyBookRenderBranch _buildForwardDynamicLayers({
    required BuildContext context,
    required StPageFlipScene scene,
    required Size pageSize,
    required StPageFlipDirection direction,
    required List<Widget> layers,
  }) {
    final calculation = scene.calculation;
    final renderFrame = scene.renderFrame;
    final bottomArea =
        renderFrame?.bottomClipArea ?? calculation?.getBottomClipArea();
    final bottomAnchor =
        renderFrame?.bottomAnchor ?? calculation?.getBottomPagePosition();
    if (bottomArea != null &&
        bottomAnchor != null &&
        scene.bottomPageIndex != null) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.bottomPageIndex!,
          pageSize: pageSize,
          area: bottomArea,
          anchor: bottomAnchor,
          angle: 0,
          scene: scene,
          direction: direction,
          isFlippingPage: false,
        ),
      );
    }

    final flippingArea =
        renderFrame?.flippingClipArea ?? calculation?.getFlippingClipArea();
    final flippingAnchor =
        renderFrame?.flippingAnchor ?? calculation?.getActiveCorner();
    final flippingAngle = renderFrame?.angle ?? calculation?.getAngle();
    if (flippingArea != null &&
        flippingAnchor != null &&
        flippingAngle != null &&
        scene.flippingPageIndex != null) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.flippingPageIndex!,
          pageSize: pageSize,
          area: flippingArea,
          anchor: flippingAnchor,
          angle: flippingAngle,
          scene: scene,
          direction: direction,
          isFlippingPage: true,
        ),
      );
    }
    return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
  }

  ArticleReadOnlyBookRenderBranch _buildBackwardDynamicLayers({
    required BuildContext context,
    required StPageFlipScene scene,
    required Size pageSize,
    required List<Widget> layers,
  }) {
    final frame = scene.renderFrame;
    if (!_hasBackwardPaperFoldFrame(scene) || frame == null) {
      return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    }
    if (scene.flippingPageIndex == null) {
      return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
    }
    final textureBinding = _textureBindingForScene(scene);

    if (scene.bottomPageIndex != null && frame.bottomClipArea.length >= 3) {
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: scene.bottomPageIndex!,
          pageSize: pageSize,
          area: frame.bottomClipArea,
          anchor: frame.bottomAnchor,
          angle: 0,
          scene: scene,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: frame.visualGeometryDirection,
          isFlippingPage: false,
        ),
      );
    }

    if (frame.flippingClipArea.length >= 3) {
      final flippingPageIndex =
          textureBinding?.rectoPageIndex ?? scene.flippingPageIndex!;
      layers.add(
        _buildDynamicPageLayer(
          context: context,
          pageIndex: flippingPageIndex,
          pageSize: pageSize,
          area: frame.flippingClipArea,
          anchor: frame.flippingAnchor,
          angle: frame.angle,
          scene: scene,
          direction: StPageFlipDirection.back,
          visualGeometryDirection: frame.visualGeometryDirection,
          isFlippingPage: true,
          backFacePageIndex: textureBinding?.versoPageIndex,
          backwardLeafFrame: frame.backwardLeafFrame,
          backwardFoldLine: frame.backwardProjectedFrame?.foldLine,
          backwardFreeEdgeLine:
              frame.backwardProjectedFrame?.projectedRightEdgeLine,
        ),
      );
    }

    if (_deck.debugPureBackwardGeometry) {
      layers.add(_buildBackwardGeometryGuideLayer(scene));
    }
    return ArticleReadOnlyBookRenderBranch.paperFoldDynamic;
  }

  Widget _buildBackwardGeometryGuideLayer(StPageFlipScene scene) {
    final geometry = _resolveBackwardDiagnosticGeometry(scene);
    final foldLine = geometry?.foldLineViewport;
    if (foldLine == null) {
      return const SizedBox.shrink();
    }
    return Positioned.fill(
      child: IgnorePointer(
        child: CustomPaint(
          painter: _BackwardGeometryGuidePainter(
            foldLine: foldLine,
            freeEdgeLine: geometry?.freeEdgeLineViewport,
          ),
        ),
      ),
    );
  }

  String _cornerNameFromPageFlip(
    StPageFlipCorner corner,
    StPageFlipDirection direction,
  ) {
    if (corner == StPageFlipCorner.top) {
      return direction == StPageFlipDirection.forward
          ? 'top_right'
          : 'top_left';
    }
    return direction == StPageFlipDirection.forward
        ? 'bottom_right'
        : 'bottom_left';
  }
}
