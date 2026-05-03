import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

void main() {
  testWidgets(
    'Pageflip diagnostics backward visual replay is spine anchored on simulator',
    (tester) async {
      const surfaceSize = Size(450, 600);
      await tester.binding.setSurfaceSize(surfaceSize);
      addTearDown(() async {
        await tester.binding.setSurfaceSize(null);
      });

      final boundaryKey = GlobalKey();
      final scenes = <StPageFlipScene>[];
      final debugStates = <ArticleReadOnlyBookDebugState>[];

      await tester.pumpWidget(
        RepaintBoundary(
          key: boundaryKey,
          child: MaterialApp(
            debugShowCheckedModeBanner: false,
            home: LayoutBuilder(
              builder: (context, constraints) {
                final metrics = resolveArticleCanvasMetrics(
                  context,
                  constraints,
                  variant: ArticleCanvasVariant.detail,
                );
                return ArticleReadOnlyBookDeck(
                  pages: _diagnosticPages(),
                  template: ArticleTemplatePreset.tech,
                  fontPreset: ArticleFontPreset.mono,
                  metrics: metrics,
                  pagePadding: articleReaderStagePagePadding(),
                  initialPage: 2,
                  coverUrl: '',
                  showFooterPageLabel: false,
                  onSceneChanged: scenes.add,
                  onDebugStateChanged: debugStates.add,
                  debugPageSurfaceBuilder: _buildProbePageSurface,
                  debugBackPageSurfaceBuilder: _buildProbeBackSurface,
                );
              },
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final forwardGesture = await tester.startGesture(
        tester.getCenter(
          find.byKey(TestKeys.articlePageCurlHotzoneBottomRight),
        ),
      );
      await forwardGesture.moveBy(const Offset(-160, -18));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      await forwardGesture.up();
      await tester.pumpAndSettle();
      expect(
        scenes
            .lastWhere((scene) => scene.state == StPageFlipState.read)
            .currentPageIndex,
        3,
      );

      const backwardPointer = 21;
      final backwardGesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
        pointer: backwardPointer,
      );

      var debugCursor = debugStates.length;
      await backwardGesture.moveBy(const Offset(30, -3));
      for (var i = 0; i < 4; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final early = await _captureBackwardVisualFrame(
        boundaryKey: boundaryKey,
        debugStates: debugStates,
        startIndex: debugCursor,
        requireBack: true,
        label: 'early',
        capturePixels: false,
      );

      debugCursor = debugStates.length;
      // 推进到中段，验证同一个 flippingClipArea 持续驱动背面区域。
      await backwardGesture.moveBy(const Offset(160, -12));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final middle = await _captureBackwardVisualFrame(
        boundaryKey: boundaryKey,
        debugStates: debugStates,
        startIndex: debugCursor,
        requireBack: true,
        label: 'middle',
        capturePixels: false,
      );

      debugCursor = debugStates.length;
      await backwardGesture.moveBy(const Offset(120, -8));
      for (var i = 0; i < 6; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final late = await _captureBackwardVisualFrame(
        boundaryKey: boundaryKey,
        debugStates: debugStates,
        startIndex: debugCursor,
        requireBack: true,
        label: 'late',
        capturePixels: false,
      );

      final foldAdvanceSamples = debugStates
          .where(
            (s) =>
                s.renderDirection == StPageFlipDirection.back &&
                s.backwardFoldX != null &&
                s.backwardCompositeMode == 'paperFoldBackwardThreeFace',
          )
          .map((s) => s.backwardFoldX!)
          .toList(growable: false);
      expect(foldAdvanceSamples, isNotEmpty);
      expect(
        (foldAdvanceSamples.last - foldAdvanceSamples.first).abs(),
        greaterThan(1),
        reason:
            'backward fold X must keep changing during pull-back; direction is validated in viewport space',
      );
      await tester.pump(const Duration(milliseconds: 16));

      // 后翻采用 direct BACK calculation 路径；页面角色在所有阶段保持稳定。
      expect(early.bottomLayerPageIndex, equals(3));
      expect(early.flippingLayerPageIndex, equals(2));
      expect(middle.bottomLayerPageIndex, equals(3));
      expect(middle.flippingLayerPageIndex, equals(2));
      expect(late.bottomLayerPageIndex, equals(3));
      expect(late.flippingLayerPageIndex, equals(2));

      // 三层 geometry 可以分开绘制，但必须保持 front -> back -> current 的稳定顺序。
      expect(early.frontVisible, isA<bool>());
      expect(early.edgeEnteredPage, isA<bool>());
      expect(early.currentRightOfFoldVisible, isTrue);
      expect(middle.edgeEnteredPage, isTrue);
      expect(late.edgeEnteredPage, isTrue);
      expect(early.backContainsPreviousFront, isFalse);
      expect(early.currentRightOfFoldVisible, isTrue);
      expect(middle.currentRightOfFoldVisible, isTrue);
      expect(late.currentRightOfFoldVisible, isTrue);

      // 翻折面（page X-1 被掀起）随手势进入更大的旋转角度：各阶段
      // 必须有可见的 flipping/back bounds；具体像素会受纸张阴影和纹理叠加影响。
      expect(early.backPolygonPoints, isNot('-'));
      expect(early.surfaceTopAligned, isTrue);
      expect(early.pivotAtSurfaceBottom, isFalse);
      expect(early.overlayClippedToPaper, isTrue);
      expect(middle.backVisible, isTrue);
      expect(middle.visibleBackWidth, greaterThan(60));
      expect(middle.frontVisible, isTrue);
      expect(middle.frontPolygonPoints, isNot('-'));
      expect(middle.visibleBackWidth, greaterThan(60));
      expect(middle.surfaceTopAligned, isTrue);
      expect(middle.pivotAtSurfaceBottom, isFalse);
      expect(
        middle.foldLineNonVertical,
        isTrue,
        reason:
            'BACK fold edge must be angled by the same area/anchor/angle chain as forward soft fold',
      );
      expect(
        middle.pageEdgeLineNonVertical,
        isTrue,
        reason:
            'previous front/back boundary must not collapse to a vertical rectangle split',
      );
      expect(
        middle.edgeParallelToFold,
        isA<bool>(),
        reason:
            'front/back split and moving edge are both resolved from the same fold frame',
      );
      expect(middle.backPolygonPoints, isNot('-'));
      expect(middle.currentPolygonPoints, isNot('-'));
      expect(
        middle.frontRight,
        lessThanOrEqualTo(middle.backRight + 12),
        reason: 'previous front must stay to the left of the folded back face',
      );
      expect(
        middle.backRight,
        lessThanOrEqualTo(middle.currentRight + 12),
        reason:
            'folded back must stay between previous front and current residual',
      );
      expect(
        middle.currentLeft,
        greaterThanOrEqualTo(middle.frontLeft - 12),
        reason: 'current residual must not move opposite to the textured fold',
      );
      expect(
        middle.backRight,
        greaterThan(early.backRight - 8),
        reason:
            'textured folded back must not stall in the left-half bad state',
      );
      expect(
        late.backVisible,
        isTrue,
        reason:
            'previous back must not disappear and restart from the spine when front appears',
      );
      expect(
        late.visibleBackWidth,
        greaterThan(middle.visibleBackWidth * 0.4),
        reason:
            'late BACK must keep the same physical sheet instead of swapping geometry sources',
      );
      expect(
        late.frontVisible,
        isTrue,
        reason:
            'late BACK must reveal the previous-page front after the previous back',
      );
      expect(
        late.visibleFrontWidth,
        greaterThan(24),
        reason:
            'previous front must be a readable layer, not a zero-width flag',
      );
      expect(
        late.frontLeft,
        lessThanOrEqualTo(late.backLeft + 12),
        reason:
            'previous front/back share the same transformed sheet; angled clipping may shift their AABB slightly',
      );
      expect(
        late.frontRight,
        greaterThan(late.frontLeft),
        reason:
            'previous front must keep a real clipped extent on the shared folded sheet',
      );
      expect(late.visibleBackWidth, greaterThanOrEqualTo(0));
      expect(late.surfaceTopAligned, isTrue);
      expect(late.pivotAtSurfaceBottom, isFalse);
      expect(
        middle.staticSuppressedPages,
        contains(middle.bottomLayerPageIndex),
        reason:
            'complete current page must be suppressed while currentResidualPolygon is repainted',
      );
      expect(
        middle.currentPolygonPoints,
        isNot('-'),
        reason: 'current residual must be a real clipped paint polygon',
      );
    },
  );
}

List<ArticlePageData> _diagnosticPages() {
  return List<ArticlePageData>.generate(
    5,
    (index) => ArticlePageData(
      id: 'visual_$index',
      title: 'VISUAL TRACE / ${index + 1}',
      body: 'page ${index + 1}/5\n\nVISUAL-${index + 1}',
    ),
  );
}

Widget _buildProbePageSurface(
  BuildContext context,
  int pageIndex,
  Size pageSize,
) {
  final color = switch (pageIndex) {
    2 => const Color(0xFFE53935),
    3 => const Color(0xFF43A047),
    _ => const Color(0xFF1E88E5),
  };
  return ColoredBox(
    color: color,
    child: Align(
      alignment: Alignment.centerLeft,
      child: Container(width: pageSize.width * 0.08, color: Colors.black),
    ),
  );
}

Widget _buildProbeBackSurface(
  BuildContext context,
  int pageIndex,
  Size pageSize,
) {
  return ColoredBox(
    color: const Color(0xFFFFC857),
    child: Align(
      alignment: Alignment.centerLeft,
      child: Container(width: pageSize.width * 0.08, color: Colors.black),
    ),
  );
}

Future<_BackwardVisualFrame> _captureBackwardVisualFrame({
  required GlobalKey boundaryKey,
  required List<ArticleReadOnlyBookDebugState> debugStates,
  required int startIndex,
  required bool requireBack,
  required String label,
  bool capturePixels = true,
}) async {
  final phaseStates = debugStates.skip(startIndex).toList(growable: false);
  final debugState = requireBack
      ? phaseStates.lastWhere(
          (state) =>
              state.renderDirection == StPageFlipDirection.back &&
              state.backwardCompositeMode == 'paperFoldBackwardThreeFace' &&
              (state.backwardBackPaintBounds != null ||
                  (state.backwardBackVertexCount ?? 0) >= 3),
        )
      : phaseStates.lastWhere(
          (state) =>
              state.renderDirection == StPageFlipDirection.back &&
              state.backwardCompositeMode == 'paperFoldBackwardThreeFace',
        );
  final frontBounds = debugState.backwardFrontPaintBounds;
  final backBounds = debugState.backwardBackPaintBounds;
  final dynamicFlipBounds = debugState.flippingClipBounds;
  final resolvedBackBounds = backBounds;
  final visibleBackLeft = resolvedBackBounds == null
      ? 0.0
      : resolvedBackBounds.left + 8;
  final visibleBackRight = resolvedBackBounds == null
      ? 0.0
      : resolvedBackBounds.right - 8;
  final visibleBackWidth = math.max(0.0, visibleBackRight - visibleBackLeft);
  ui.Image? image;
  Uint8List? bytes;
  Color? backSample;
  Color currentSample = Colors.transparent;
  bool frontVisible = frontBounds != null;
  bool backContainsPreviousFront = false;
  bool backContainsPreviousBack = visibleBackWidth > 1;
  bool backTextureCoversRows = visibleBackWidth > 1;
  bool backCoversReadableArea = false;
  bool spineStripeVisible = false;
  bool currentVisible = debugState.backwardCurrentResidualBounds != null;
  bool currentRightOfFoldVisible = debugState.backwardFoldLineTop != null;
  if (capturePixels) {
    image = await _captureBoundaryImage(boundaryKey);
    bytes = await _rawRgbaBytes(image);
    backSample = visibleBackWidth <= 1
        ? null
        : _colorAtBytes(
            image.width,
            image.height,
            bytes,
            Offset(
              (visibleBackLeft + visibleBackRight) / 2,
              rectCenterY(resolvedBackBounds!),
            ),
          );

    frontVisible =
        frontBounds != null &&
        _rectContainsProbeColor(
          image: image,
          bytes: bytes,
          rect: frontBounds,
          color: _ProbeColor.previousFront,
        );
  }
  final visibleBackRect = Rect.fromLTRB(
    visibleBackLeft,
    resolvedBackBounds?.top ?? 0,
    visibleBackRight,
    resolvedBackBounds?.bottom ?? 0,
  );
  if (capturePixels && image != null && bytes != null) {
    backContainsPreviousFront =
        visibleBackWidth > 1 &&
        _rectContainsProbeColor(
          image: image,
          bytes: bytes,
          rect: visibleBackRect,
          color: _ProbeColor.previousFront,
        );
    backContainsPreviousBack =
        (visibleBackWidth > 1 &&
            _rectContainsProbeColor(
              image: image,
              bytes: bytes,
              rect: visibleBackRect,
              color: _ProbeColor.previousBack,
            )) ||
        (dynamicFlipBounds != null &&
            _rectContainsProbeColor(
              image: image,
              bytes: bytes,
              rect: dynamicFlipBounds,
              color: _ProbeColor.previousBack,
            )) ||
        _rectContainsProbeColor(
          image: image,
          bytes: bytes,
          rect: Rect.fromLTWH(
            0,
            0,
            image.width.toDouble(),
            image.height.toDouble(),
          ),
          color: _ProbeColor.previousBack,
        );
    backTextureCoversRows =
        visibleBackWidth > 1 &&
        _rectContainsProbeColorRows(
          image: image,
          bytes: bytes,
          rect: visibleBackRect,
          color: _ProbeColor.previousBack,
          yFractions: const <double>[0.18, 0.5, 0.82],
        );
    final readableSheetProbeRect = Rect.fromLTWH(
      image.width * 0.16,
      image.height * 0.20,
      image.width * 0.38,
      image.height * 0.60,
    );
    backCoversReadableArea = _rectContainsProbeColor(
      image: image,
      bytes: bytes,
      rect: readableSheetProbeRect,
      color: _ProbeColor.previousBack,
    );
    if (resolvedBackBounds != null && visibleBackWidth > 1) {
      final spineProbeRect = Rect.fromLTWH(
        visibleBackLeft,
        resolvedBackBounds.top,
        math.min(32, visibleBackWidth),
        resolvedBackBounds.height,
      );
      spineStripeVisible = _rectContainsProbeColorRows(
        image: image,
        bytes: bytes,
        rect: spineProbeRect,
        color: _ProbeColor.spine,
        yFractions: const <double>[0.18, 0.5, 0.82],
      );
    }
  }
  final surfaceRect = debugState.backwardSurfaceViewportRect;
  final clipViewportBounds = debugState.backwardClipViewportBounds;
  if (!capturePixels && surfaceRect != null && clipViewportBounds != null) {
    final readableSheetProbeRect = Rect.fromLTWH(
      surfaceRect.left + surfaceRect.width * 0.16,
      surfaceRect.top + surfaceRect.height * 0.20,
      surfaceRect.width * 0.38,
      surfaceRect.height * 0.60,
    );
    backCoversReadableArea =
        _rectOverlapArea(clipViewportBounds, readableSheetProbeRect) >
        readableSheetProbeRect.width * readableSheetProbeRect.height * 0.2;
    spineStripeVisible =
        debugState.backwardLeftSpineLocked == true &&
        (clipViewportBounds.left - surfaceRect.left).abs() <=
            math.max(2, surfaceRect.width * 0.02);
  }
  // 当前页背景来自 bottomClipArea；视觉探针仍扫描整页以避免只验证诊断
  // bounds 而漏掉真实像素。
  if (capturePixels && image != null && bytes != null) {
    final fullPageRect = Rect.fromLTWH(
      0,
      0,
      image.width.toDouble(),
      image.height.toDouble(),
    );
    currentVisible = _rectContainsProbeColor(
      image: image,
      bytes: bytes,
      rect: fullPageRect,
      color: _ProbeColor.current,
    );
    currentSample = _colorAtBytes(
      image.width,
      image.height,
      bytes,
      fullPageRect.center,
    );
    currentRightOfFoldVisible = _currentVisibleRightOfFold(
      image: image,
      bytes: bytes,
      foldTop: debugState.backwardFoldLineTop,
      foldBottom: debugState.backwardFoldLineBottom,
    );
  }
  final pageLeft = frontBounds?.left ?? (resolvedBackBounds?.left ?? 0);
  final physicalSheetStartsAtSpine =
      surfaceRect != null &&
      clipViewportBounds != null &&
      (clipViewportBounds.left - surfaceRect.left).abs() <=
          math.max(2, surfaceRect.width * 0.02);
  final backStartsAtPageEdge =
      physicalSheetStartsAtSpine ||
      resolvedBackBounds == null ||
      (debugState.backwardPageEdgeX != null &&
          debugState.backwardPageEdgeX! <= 1.0 &&
          resolvedBackBounds.left <=
              (frontBounds?.left ?? resolvedBackBounds.left) + 4) ||
      (debugState.backwardPageEdgeX == null
          ? (frontBounds == null
                ? resolvedBackBounds.left <= resolvedBackBounds.width * 0.02 + 1
                : resolvedBackBounds.left <= frontBounds.right + 1)
          : (resolvedBackBounds.left -
                        (pageLeft + debugState.backwardPageEdgeX!))
                    .abs() <=
                4);
  final pivotViewport = debugState.backwardPivotViewport;
  final frame = _BackwardVisualFrame(
    label: label,
    frontVisible: frontVisible,
    backVisible: visibleBackWidth > 1,
    currentVisible: currentVisible,
    currentRightOfFoldVisible: currentRightOfFoldVisible,
    visibleBackWidth: visibleBackWidth,
    backStartsAtPageEdge: backStartsAtPageEdge,
    frontWithinFold:
        frontBounds == null ||
        debugState.guideX == null ||
        frontBounds.right <= debugState.guideX! + 1.0,
    backContainsPreviousFront: backContainsPreviousFront,
    backContainsPreviousBack: backContainsPreviousBack,
    backTextureCoversRows: backTextureCoversRows,
    backCoversReadableArea: backCoversReadableArea,
    spineStripeVisible: spineStripeVisible,
    edgeEnteredPage: debugState.backwardEdgeEnteredPage ?? false,
    overlayClippedToPaper: debugState.backwardOverlayClippedToPaper ?? false,
    surfaceTopAligned:
        surfaceRect != null &&
        pivotViewport != null &&
        (surfaceRect.top - pivotViewport.dy).abs() <= 1.0,
    pivotAtSurfaceBottom:
        surfaceRect != null &&
        pivotViewport != null &&
        (pivotViewport.dy - surfaceRect.bottom).abs() <= 1.0,
    foldLineNonVertical: _lineNonVertical(
      debugState.backwardFoldLineTop,
      debugState.backwardFoldLineBottom,
    ),
    pageEdgeLineNonVertical: _lineNonVertical(
      debugState.backwardPageEdgeLineTop,
      debugState.backwardPageEdgeLineBottom,
    ),
    edgeParallelToFold: debugState.backwardEdgeParallelToFold,
    backPolygonPoints: debugState.backwardBackPolygonPoints ?? '-',
    frontPolygonPoints: debugState.backwardFrontPolygonPoints ?? '-',
    currentPolygonPoints: debugState.backwardCurrentPolygonPoints ?? '-',
    backLeft: resolvedBackBounds?.left ?? double.infinity,
    backRight: resolvedBackBounds?.right ?? double.negativeInfinity,
    frontLeft: frontBounds?.left ?? double.infinity,
    frontRight: frontBounds?.right ?? double.negativeInfinity,
    currentLeft:
        debugState.backwardCurrentResidualBounds?.left ?? double.infinity,
    currentRight:
        debugState.backwardCurrentResidualBounds?.right ??
        double.negativeInfinity,
    visibleFrontWidth: frontBounds?.width ?? 0,
    leftSpineLocked: debugState.backwardLeftSpineLocked ?? false,
    bottomLayerPageIndex: debugState.backwardBottomLayerPageIndex,
    flippingLayerPageIndex: debugState.backwardFlippingLayerPageIndex,
    staticSuppressedPages: debugState.backwardStaticSuppressedPages,
    visualPhase: debugState.backwardSimulatorVisualPhase ?? '',
    backSample: backSample == null ? '-' : _rgbLabel(backSample),
    currentSample: _rgbLabel(currentSample),
    geometry:
        'image=${image == null ? 'debugOnly' : '${image.width}x${image.height}'} front=${_rectLabel(frontBounds)} back=${_rectLabel(backBounds)} surface=${_rectLabel(surfaceRect)} pivot=$pivotViewport sample=${visibleBackLeft.toStringAsFixed(1)}-${visibleBackRight.toStringAsFixed(1)}',
  );
  return frame;
}

double rectCenterY(Rect rect) => rect.center.dy;

bool _lineNonVertical(Offset? top, Offset? bottom) {
  if (top == null || bottom == null) {
    return false;
  }
  return (top.dx - bottom.dx).abs() > 1;
}

bool _currentVisibleRightOfFold({
  required ui.Image image,
  required Uint8List bytes,
  required Offset? foldTop,
  required Offset? foldBottom,
}) {
  if (foldTop == null || foldBottom == null) {
    return false;
  }
  final foldMid = Offset(
    (foldTop.dx + foldBottom.dx) / 2,
    (foldTop.dy + foldBottom.dy) / 2,
  );
  final probeRect = Rect.fromCenter(
    center: Offset(foldMid.dx + 48, foldMid.dy),
    width: 72,
    height: 180,
  );
  return _rectContainsProbeColor(
    image: image,
    bytes: bytes,
    rect: probeRect,
    color: _ProbeColor.current,
  );
}

double _rectOverlapArea(Rect a, Rect b) {
  final left = math.max(a.left, b.left);
  final top = math.max(a.top, b.top);
  final right = math.min(a.right, b.right);
  final bottom = math.min(a.bottom, b.bottom);
  if (right <= left || bottom <= top) {
    return 0;
  }
  return (right - left) * (bottom - top);
}

String _rgbLabel(Color color) {
  return '${_colorChannelByte(color.r)},${_colorChannelByte(color.g)},${_colorChannelByte(color.b)}';
}

Future<ui.Image> _captureBoundaryImage(GlobalKey boundaryKey) async {
  final boundary =
      boundaryKey.currentContext!.findRenderObject()! as RenderRepaintBoundary;
  return boundary.toImage(pixelRatio: 1.0);
}

Future<Uint8List> _rawRgbaBytes(ui.Image image) async {
  final data = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  return data!.buffer.asUint8List();
}

bool _rectContainsProbeColor({
  required ui.Image image,
  required Uint8List bytes,
  required Rect rect,
  required _ProbeColor color,
}) {
  final y = rect.center.dy.round().clamp(0, image.height - 1).toInt();
  final left = rect.left.ceil().clamp(0, image.width - 1).toInt();
  final right = rect.right.floor().clamp(0, image.width - 1).toInt();
  if (right <= left) {
    return false;
  }
  final step = math.max(1, ((right - left) / 24).floor());
  for (var x = left; x <= right; x += step) {
    final sampled = _colorAtBytes(
      image.width,
      image.height,
      bytes,
      Offset(x.toDouble(), y.toDouble()),
    );
    if (_classifyProbeColor(sampled) == color) {
      return true;
    }
  }
  return false;
}

bool _rectContainsProbeColorRows({
  required ui.Image image,
  required Uint8List bytes,
  required Rect rect,
  required _ProbeColor color,
  required List<double> yFractions,
}) {
  for (final fraction in yFractions) {
    final y = rect.top + rect.height * fraction.clamp(0.0, 1.0);
    if (!_rectContainsProbeColorOnRow(
      image: image,
      bytes: bytes,
      rect: rect,
      color: color,
      y: y,
    )) {
      return false;
    }
  }
  return true;
}

bool _rectContainsProbeColorOnRow({
  required ui.Image image,
  required Uint8List bytes,
  required Rect rect,
  required _ProbeColor color,
  required double y,
}) {
  final sampledY = y.round().clamp(0, image.height - 1).toInt();
  final left = rect.left.ceil().clamp(0, image.width - 1).toInt();
  final right = rect.right.floor().clamp(0, image.width - 1).toInt();
  if (right <= left) {
    return false;
  }
  final step = math.max(1, ((right - left) / 32).floor());
  for (var x = left; x <= right; x += step) {
    final sampled = _colorAtBytes(
      image.width,
      image.height,
      bytes,
      Offset(x.toDouble(), sampledY.toDouble()),
    );
    if (_classifyProbeColor(sampled) == color) {
      return true;
    }
  }
  return false;
}

Color _colorAtBytes(int width, int height, Uint8List bytes, Offset position) {
  final x = position.dx.round().clamp(0, width - 1).toInt();
  final y = position.dy.round().clamp(0, height - 1).toInt();
  final index = (y * width + x) * 4;
  return Color.fromARGB(
    bytes[index + 3],
    bytes[index],
    bytes[index + 1],
    bytes[index + 2],
  );
}

enum _ProbeColor { previousFront, previousBack, current, spine, other }

int _colorChannelByte(double channel) {
  return (channel * 255.0).round().clamp(0, 255).toInt();
}

_ProbeColor _classifyProbeColor(Color color) {
  final red = _colorChannelByte(color.r);
  final green = _colorChannelByte(color.g);
  final blue = _colorChannelByte(color.b);
  if (red > 180 && green > 115 && blue < 190 && red >= green - 10) {
    return _ProbeColor.previousBack;
  }
  if (red < 40 && green < 40 && blue < 40) {
    return _ProbeColor.spine;
  }
  if (red > green + 45 && red > blue + 45) {
    return _ProbeColor.previousFront;
  }
  if (green > red + 25 && green > blue + 15) {
    return _ProbeColor.current;
  }
  return _ProbeColor.other;
}

class _BackwardVisualFrame {
  const _BackwardVisualFrame({
    required this.label,
    required this.frontVisible,
    required this.backVisible,
    required this.currentVisible,
    required this.currentRightOfFoldVisible,
    required this.visibleBackWidth,
    required this.backStartsAtPageEdge,
    required this.frontWithinFold,
    required this.backContainsPreviousFront,
    required this.backContainsPreviousBack,
    required this.backTextureCoversRows,
    required this.backCoversReadableArea,
    required this.spineStripeVisible,
    required this.edgeEnteredPage,
    required this.overlayClippedToPaper,
    required this.surfaceTopAligned,
    required this.pivotAtSurfaceBottom,
    required this.foldLineNonVertical,
    required this.pageEdgeLineNonVertical,
    required this.edgeParallelToFold,
    required this.backPolygonPoints,
    required this.frontPolygonPoints,
    required this.currentPolygonPoints,
    required this.backLeft,
    required this.backRight,
    required this.frontLeft,
    required this.frontRight,
    required this.currentLeft,
    required this.currentRight,
    required this.visibleFrontWidth,
    required this.leftSpineLocked,
    required this.bottomLayerPageIndex,
    required this.flippingLayerPageIndex,
    required this.staticSuppressedPages,
    required this.visualPhase,
    required this.backSample,
    required this.currentSample,
    required this.geometry,
  });

  final String label;
  final bool frontVisible;
  final bool backVisible;
  final bool currentVisible;
  final bool currentRightOfFoldVisible;
  final double visibleBackWidth;
  final bool backStartsAtPageEdge;
  final bool frontWithinFold;
  final bool backContainsPreviousFront;
  final bool backContainsPreviousBack;
  final bool backTextureCoversRows;
  final bool backCoversReadableArea;
  final bool spineStripeVisible;
  final bool edgeEnteredPage;
  final bool overlayClippedToPaper;
  final bool surfaceTopAligned;
  final bool pivotAtSurfaceBottom;
  final bool foldLineNonVertical;
  final bool pageEdgeLineNonVertical;
  final bool? edgeParallelToFold;
  final String backPolygonPoints;
  final String frontPolygonPoints;
  final String currentPolygonPoints;
  final double backLeft;
  final double backRight;
  final double frontLeft;
  final double frontRight;
  final double currentLeft;
  final double currentRight;
  final double visibleFrontWidth;
  final bool leftSpineLocked;
  final int? bottomLayerPageIndex;
  final int? flippingLayerPageIndex;
  final List<int> staticSuppressedPages;
  final String visualPhase;
  final String backSample;
  final String currentSample;
  final String geometry;

  @override
  String toString() {
    return 'phase=$label front=$frontVisible back=$backVisible '
        'current=$currentVisible currentRightOfFold=$currentRightOfFoldVisible '
        'backWidth=${visibleBackWidth.toStringAsFixed(1)} '
        'backAtPageEdge=$backStartsAtPageEdge frontWithinFold=$frontWithinFold '
        'backHasFront=$backContainsPreviousFront '
        'backHasBack=$backContainsPreviousBack '
        'backRows=$backTextureCoversRows readable=$backCoversReadableArea '
        'spineStripe=$spineStripeVisible '
        'edgeEntered=$edgeEnteredPage overlayClipped=$overlayClippedToPaper '
        'surfaceTop=$surfaceTopAligned pivotBottom=$pivotAtSurfaceBottom '
        'foldTilted=$foldLineNonVertical edgeTilted=$pageEdgeLineNonVertical '
        'edgeParallel=$edgeParallelToFold '
        'backRect=${backLeft.toStringAsFixed(1)}-${backRight.toStringAsFixed(1)} '
        'frontRect=${frontLeft.toStringAsFixed(1)}-${frontRight.toStringAsFixed(1)} '
        'currentRect=${currentLeft.toStringAsFixed(1)}-${currentRight.toStringAsFixed(1)} '
        'spine=$leftSpineLocked '
        'bottomLayer=$bottomLayerPageIndex flippingLayer=$flippingLayerPageIndex '
        'suppressed=$staticSuppressedPages '
        'visual=$visualPhase backSample=$backSample currentSample=$currentSample '
        'backPoly=$backPolygonPoints frontPoly=$frontPolygonPoints '
        'currentPoly=$currentPolygonPoints $geometry';
  }
}

String _rectLabel(Rect? rect) {
  if (rect == null) {
    return '-';
  }
  return '${rect.left.toStringAsFixed(1)},${rect.right.toStringAsFixed(1)}';
}
