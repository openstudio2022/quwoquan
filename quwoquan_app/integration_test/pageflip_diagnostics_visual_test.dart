import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/pageflip/controller.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';
import 'package:quwoquan_app/ui/content/widgets/article_paged_canvas.dart';

void main() {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets(
    'Pageflip diagnostics backward visual replay is spine anchored on simulator',
    (tester) async {
      const surfaceSize = Size(900, 1200);
      await tester.binding.setSurfaceSize(surfaceSize);
      addTearDown(() => tester.binding.setSurfaceSize(null));

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
      await forwardGesture.moveBy(const Offset(-320, -36));
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

      final backwardGesture = await tester.startGesture(
        tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
      );

      var debugCursor = debugStates.length;
      await backwardGesture.moveBy(const Offset(120, -12));
      for (var i = 0; i < 4; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final early = await _captureBackwardVisualFrame(
        boundaryKey: boundaryKey,
        debugStates: debugStates,
        startIndex: debugCursor,
        requireBack: true,
        label: 'early',
      );

      debugCursor = debugStates.length;
      // 推进到中段，验证同一个 flippingClipArea 持续驱动背面区域。
      await backwardGesture.moveBy(const Offset(320, -24));
      for (var i = 0; i < 8; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final middle = await _captureBackwardVisualFrame(
        boundaryKey: boundaryKey,
        debugStates: debugStates,
        startIndex: debugCursor,
        requireBack: true,
        label: 'middle',
      );

      debugCursor = debugStates.length;
      await backwardGesture.moveBy(const Offset(160, -24));
      for (var i = 0; i < 6; i += 1) {
        await tester.pump(const Duration(milliseconds: 16));
      }
      final late = await _captureBackwardVisualFrame(
        boundaryKey: boundaryKey,
        debugStates: debugStates,
        startIndex: debugCursor,
        requireBack: false,
        label: 'late',
      );

      await backwardGesture.up();
      await tester.pumpAndSettle();

      debugPrint('[pageflip][visual-test] $early');
      debugPrint('[pageflip][visual-test] $middle');
      debugPrint('[pageflip][visual-test] $late');

      // 后翻采用镜像前翻同构路径：current/background 来自 bottomClipArea，
      // 上一页背面来自 flippingClipArea，页面角色在所有阶段保持稳定。
      expect(early.bottomLayerPageIndex, equals(3));
      expect(early.flippingLayerPageIndex, equals(2));
      expect(middle.bottomLayerPageIndex, equals(3));
      expect(middle.flippingLayerPageIndex, equals(2));
      expect(late.bottomLayerPageIndex, equals(3));
      expect(late.flippingLayerPageIndex, equals(2));

      // previousFront 不再作为独立静态拓扑层铺开；它只能在同一个
      // genericDynamic flipping surface 内由 E 线左侧逐步出现。
      expect(early.frontVisible, isFalse);
      expect(middle.frontVisible, isTrue);
      expect(late.frontVisible, isTrue);
      expect(early.backContainsPreviousFront, isFalse);
      expect(early.currentVisible, isTrue);
      expect(middle.currentVisible, isTrue);
      expect(late.currentVisible, isTrue);

      // 翻折面（page X-1 被掀起）随手势进入更大的旋转角度：各阶段
      // 必须有可见的 flipping/back bounds；具体像素会受纸张阴影和纹理叠加影响。
      expect(early.backVisible, isTrue);
      expect(early.visibleBackWidth, greaterThan(20));
      expect(early.surfaceTopAligned, isTrue);
      expect(early.pivotAtSurfaceBottom, isTrue);
      expect(early.backTextureCoversRows, isTrue);
      expect(middle.backVisible, isTrue);
      expect(middle.visibleBackWidth, greaterThan(20));
      expect(middle.surfaceTopAligned, isTrue);
      expect(middle.pivotAtSurfaceBottom, isTrue);
      expect(middle.backTextureCoversRows, isTrue);
      expect(middle.foldLineNonVertical, isTrue);
      expect(middle.pageEdgeLineNonVertical, isTrue);
      expect(late.backVisible, isTrue);
      expect(late.visibleBackWidth, greaterThan(20));
      expect(late.surfaceTopAligned, isTrue);
      expect(late.pivotAtSurfaceBottom, isTrue);
      expect(late.backTextureCoversRows, isTrue);
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
}) async {
  final phaseStates = debugStates.skip(startIndex).toList(growable: false);
  final debugState = requireBack
      ? phaseStates.lastWhere(
          (state) =>
              state.renderDirection == StPageFlipDirection.back &&
              state.backwardCompositeMode == 'mirroredForwardDynamic' &&
              state.backwardBackPaintBounds != null,
        )
      : phaseStates.lastWhere(
          (state) =>
              state.renderDirection == StPageFlipDirection.back &&
              state.backwardCompositeMode == 'mirroredForwardDynamic',
        );
  final image = await _captureBoundaryImage(boundaryKey);
  final bytes = await _rawRgbaBytes(image);
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
  final backSample = visibleBackWidth <= 1
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

  final frontVisible =
      (frontBounds != null &&
          _rectContainsProbeColor(
            image: image,
            bytes: bytes,
            rect: frontBounds,
            color: _ProbeColor.previousFront,
          )) ||
      (dynamicFlipBounds != null &&
          _rectContainsProbeColor(
            image: image,
            bytes: bytes,
            rect: dynamicFlipBounds,
            color: _ProbeColor.previousFront,
          ));
  final visibleBackRect = Rect.fromLTRB(
    visibleBackLeft,
    resolvedBackBounds?.top ?? 0,
    visibleBackRight,
    resolvedBackBounds?.bottom ?? 0,
  );
  final backContainsPreviousFront =
      visibleBackWidth > 1 &&
      _rectContainsProbeColor(
        image: image,
        bytes: bytes,
        rect: visibleBackRect,
        color: _ProbeColor.previousFront,
      );
  final backContainsPreviousBack =
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
  final backTextureCoversRows =
      visibleBackWidth > 1 &&
      _rectContainsProbeColorRows(
        image: image,
        bytes: bytes,
        rect: visibleBackRect,
        color: _ProbeColor.previousBack,
        yFractions: const <double>[0.18, 0.5, 0.82],
      );
  // 当前页背景来自 bottomClipArea；视觉探针仍扫描整页以避免只验证诊断
  // bounds 而漏掉真实像素。
  final fullPageRect = Rect.fromLTWH(
    0,
    0,
    image.width.toDouble(),
    image.height.toDouble(),
  );
  final currentVisible = _rectContainsProbeColor(
    image: image,
    bytes: bytes,
    rect: fullPageRect,
    color: _ProbeColor.current,
  );
  final currentSample = _colorAtBytes(
    image.width,
    image.height,
    bytes,
    fullPageRect.center,
  );
  final pageLeft = frontBounds?.left ?? (resolvedBackBounds?.left ?? 0);
  final backStartsAtPageEdge =
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
  debugPrint(
    '[pageflip][visual-debug] label=$label '
    'branch=${debugState.renderBranch.name} '
    'flip=${_rectLabel(debugState.flippingClipBounds)} '
    'phase=${debugState.backwardPhase} '
    'slices=${debugState.backwardReplaySlices} '
    'frontCover=${debugState.backwardFrontCoverageRatio} '
    'foldX=${debugState.backwardFoldX} '
    'edgeX=${debugState.backwardPageEdgeX} '
    'bottomLayer=${debugState.backwardBottomLayerPageIndex} '
    'flippingLayer=${debugState.backwardFlippingLayerPageIndex} '
    'surface=${_rectLabel(debugState.backwardSurfaceViewportRect)} '
    'pivot=${debugState.backwardPivotViewport} '
    'clipLocal=${_rectLabel(debugState.backwardClipLocalBounds)} '
    'clipViewport=${_rectLabel(debugState.backwardClipViewportBounds)} '
    'verso=${debugState.backwardVersoWidth} '
    'paintVerso=${debugState.backwardPaintedVersoWidth}',
  );
  final surfaceRect = debugState.backwardSurfaceViewportRect;
  final pivotViewport = debugState.backwardPivotViewport;
  return _BackwardVisualFrame(
    label: label,
    frontVisible: frontVisible,
    backVisible: visibleBackWidth > 1,
    currentVisible: currentVisible,
    visibleBackWidth: visibleBackWidth,
    backStartsAtPageEdge: backStartsAtPageEdge,
    frontWithinFold:
        frontBounds == null ||
        debugState.guideX == null ||
        frontBounds.right <= debugState.guideX! + 1.0,
    backContainsPreviousFront: backContainsPreviousFront,
    backContainsPreviousBack: backContainsPreviousBack,
    backTextureCoversRows: backTextureCoversRows,
    surfaceTopAligned:
        surfaceRect != null &&
        pivotViewport != null &&
        (surfaceRect.top - (pivotViewport.dy - surfaceRect.height)).abs() <=
            1.0,
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
    leftSpineLocked: debugState.backwardLeftSpineLocked ?? false,
    bottomLayerPageIndex: debugState.backwardBottomLayerPageIndex,
    flippingLayerPageIndex: debugState.backwardFlippingLayerPageIndex,
    visualPhase: debugState.backwardSimulatorVisualPhase ?? '',
    backSample: backSample == null ? '-' : _rgbLabel(backSample),
    currentSample: _rgbLabel(currentSample),
    geometry:
        'image=${image.width}x${image.height} front=${_rectLabel(frontBounds)} back=${_rectLabel(backBounds)} surface=${_rectLabel(surfaceRect)} pivot=$pivotViewport sample=${visibleBackLeft.toStringAsFixed(1)}-${visibleBackRight.toStringAsFixed(1)}',
  );
}

double rectCenterY(Rect rect) => rect.center.dy;

bool _lineNonVertical(Offset? top, Offset? bottom) {
  if (top == null || bottom == null) {
    return false;
  }
  return (top.dx - bottom.dx).abs() > 1;
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

enum _ProbeColor { previousFront, previousBack, current, other }

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
    required this.visibleBackWidth,
    required this.backStartsAtPageEdge,
    required this.frontWithinFold,
    required this.backContainsPreviousFront,
    required this.backContainsPreviousBack,
    required this.backTextureCoversRows,
    required this.surfaceTopAligned,
    required this.pivotAtSurfaceBottom,
    required this.foldLineNonVertical,
    required this.pageEdgeLineNonVertical,
    required this.leftSpineLocked,
    required this.bottomLayerPageIndex,
    required this.flippingLayerPageIndex,
    required this.visualPhase,
    required this.backSample,
    required this.currentSample,
    required this.geometry,
  });

  final String label;
  final bool frontVisible;
  final bool backVisible;
  final bool currentVisible;
  final double visibleBackWidth;
  final bool backStartsAtPageEdge;
  final bool frontWithinFold;
  final bool backContainsPreviousFront;
  final bool backContainsPreviousBack;
  final bool backTextureCoversRows;
  final bool surfaceTopAligned;
  final bool pivotAtSurfaceBottom;
  final bool foldLineNonVertical;
  final bool pageEdgeLineNonVertical;
  final bool leftSpineLocked;
  final int? bottomLayerPageIndex;
  final int? flippingLayerPageIndex;
  final String visualPhase;
  final String backSample;
  final String currentSample;
  final String geometry;

  @override
  String toString() {
    return 'phase=$label front=$frontVisible back=$backVisible '
        'current=$currentVisible backWidth=${visibleBackWidth.toStringAsFixed(1)} '
        'backAtPageEdge=$backStartsAtPageEdge frontWithinFold=$frontWithinFold '
        'backHasFront=$backContainsPreviousFront '
        'backHasBack=$backContainsPreviousBack '
        'backRows=$backTextureCoversRows '
        'surfaceTop=$surfaceTopAligned pivotBottom=$pivotAtSurfaceBottom '
        'foldTilted=$foldLineNonVertical edgeTilted=$pageEdgeLineNonVertical '
        'spine=$leftSpineLocked '
        'bottomLayer=$bottomLayerPageIndex flippingLayer=$flippingLayerPageIndex '
        'visual=$visualPhase backSample=$backSample currentSample=$currentSample $geometry';
  }
}

String _rectLabel(Rect? rect) {
  if (rect == null) {
    return '-';
  }
  return '${rect.left.toStringAsFixed(1)},${rect.right.toStringAsFixed(1)}';
}
