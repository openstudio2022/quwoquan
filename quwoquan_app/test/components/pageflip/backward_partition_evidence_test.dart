import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:quwoquan_app/core/test_keys.dart';
import 'package:quwoquan_app/ui/content/models/article_presentation_models.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_read_only_book_deck.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/host/article_reader_stage_widgets.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/backward_sheet_partition.dart';
import 'package:quwoquan_app/ui/content/article_reader/pageflip/layers/article_reader_soft_page_geometry.dart';
import 'package:quwoquan_app/components/pageflip/controller.dart';
import 'package:quwoquan_app/components/pageflip/types.dart';

void main() {
  testWidgets('phase0 evidence: BACK horizontal and high-overlap poses', (
    tester,
  ) async {
    final horizontal = await _collectBackwardEvidence(
      tester,
      label: 'PoseA_horizontal_no_angle',
      backwardDragDelta: const Offset(360, 0),
    );
    final highOverlap = await _collectBackwardEvidence(
      tester,
      label: 'PoseB_high_overlap',
      backwardDragDelta: const Offset(360, -36),
    );

    _printEvidence(horizontal);
    _printEvidence(highOverlap);

    expect(horizontal.hasBackScene, isTrue);
    expect(highOverlap.hasBackScene, isTrue);
    expect(horizontal.partition, isNotNull);
    expect(highOverlap.partition, isNotNull);
    expect(horizontal.partition!.previousBackVersoLocalPolygon, isNotEmpty);
    expect(
      horizontal.partition!.versoFailureReason,
      BackwardCanonicalFaceFailureReason.none,
    );
    expect(highOverlap.partition!.previousBackVersoLocalPolygon, isNotEmpty);
    expect(
      highOverlap.partition!.versoFailureReason,
      BackwardCanonicalFaceFailureReason.none,
    );
  });

  testWidgets(
    'phase2 evidence: partition sweep keeps face presence continuous',
    (tester) async {
      final angledSweep = await _collectBackwardEvidenceSweep(
        tester,
        labelPrefix: 'PoseC_angled_sweep',
        dragDeltas: const <Offset>[
          Offset(180, -18),
          Offset(240, -24),
          Offset(300, -30),
          Offset(360, -36),
        ],
      );
      final horizontalSweep = await _collectBackwardEvidenceSweep(
        tester,
        labelPrefix: 'PoseD_horizontal_sweep',
        dragDeltas: const <Offset>[
          Offset(180, 0),
          Offset(240, 0),
          Offset(300, 0),
          Offset(360, 0),
        ],
      );

      _expectContinuousFacePresence(
        angledSweep,
        label: 'angled sweep',
        requireRectoEventually: false,
      );
      _expectContinuousFacePresence(
        horizontalSweep,
        label: 'horizontal sweep',
        requireRectoEventually: false,
      );
      _expectBackBoundsDoNotJump(angledSweep, label: 'angled sweep');
      _expectBackBoundsDoNotJump(horizontalSweep, label: 'horizontal sweep');

      final lateHorizontalSweep = await _collectBackwardEvidenceSweep(
        tester,
        labelPrefix: 'PoseF_late_horizontal_sweep',
        dragDeltas: const <Offset>[
          Offset(420, 0),
          Offset(480, 0),
          Offset(540, 0),
        ],
      );
      _expectContinuousFacePresence(
        lateHorizontalSweep,
        label: 'late horizontal sweep',
        requireRectoEventually: true,
      );
      _expectBackBoundsDoNotJump(
        lateHorizontalSweep,
        label: 'late horizontal sweep',
      );
    },
  );

  testWidgets(
    'phase2.2 evidence: low-angle recto stays budgeted and current-free',
    (tester) async {
      final evidence = await _collectBackwardEvidence(
        tester,
        label: 'PoseE_low_angle_budget',
        backwardDragDelta: const Offset(540, 0),
      );
      _printEvidence(evidence);

      final frame = evidence.scene?.renderFrame;
      final leafFrame = frame?.backwardLeafFrame;
      final partition = evidence.partition;
      expect(frame, isNotNull);
      expect(leafFrame, isNotNull);
      expect(partition, isNotNull);

      final rectoEdgeWidth =
          partition!.previousFrontRectoLocalPolygon.length >= 2
          ? _edgeLength(
              partition.previousFrontRectoLocalPolygon[0],
              partition.previousFrontRectoLocalPolygon[1],
            )
          : 0.0;
      final rectoCounts =
          evidence.sourceCounts['sheetRectoFront'] ??
          const <_ProbeColor, int>{};
      final rectoPixels = rectoCounts.values.fold(
        0,
        (sum, count) => sum + count,
      );
      expect(
        partition.rectoArea > 12 || rectoEdgeWidth > 12 || rectoPixels > 0,
        isTrue,
        reason:
            'low-angle recto/front must remain visible via partition area, '
            'canonical edge, or painted framebuffer evidence. '
            'partition=${_partition(partition)} rectoPixels=$rectoPixels',
      );
      if (rectoPixels > 0) {
        final currentPixels = rectoCounts[_ProbeColor.green] ?? 0;
        final previousPixels =
            (rectoCounts[_ProbeColor.red] ?? 0) +
            (rectoCounts[_ProbeColor.black] ?? 0);
        if (previousPixels > 0) {
          expect(
            currentPixels / rectoPixels,
            lessThan(0.08),
            reason:
                'sheetRectoFront framebuffer must not contain current/front. '
                'counts=${_counts(rectoCounts)}',
          );
          expect(
            previousPixels / rectoPixels,
            greaterThan(0.60),
            reason:
                'sheetRectoFront framebuffer must remain previous/front. '
                'counts=${_counts(rectoCounts)}',
          );
        }
      }
    },
  );
}

Future<_BackwardEvidence> _collectBackwardEvidence(
  WidgetTester tester, {
  required String label,
  required Offset backwardDragDelta,
}) async {
  await tester.binding.setSurfaceSize(const Size(900, 1200));
  addTearDown(() => tester.binding.setSurfaceSize(null));

  final boundaryKey = GlobalKey();
  final scenes = <StPageFlipScene>[];
  final debugStates = <ArticleReadOnlyBookDebugState>[];
  Size? capturedBackPageSize;

  await tester.pumpWidget(
    MaterialApp(
      home: RepaintBoundary(
        key: boundaryKey,
        child: LayoutBuilder(
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
              initialPage: 3,
              coverUrl: '',
              showFooterPageLabel: false,
              onSceneChanged: scenes.add,
              onDebugStateChanged: debugStates.add,
              debugPageSurfaceBuilder: _buildProbePageSurface,
              debugBackPageSurfaceBuilder: (context, pageIndex, pageSize) {
                capturedBackPageSize = pageSize;
                return _buildProbeBackPageSurface(context, pageIndex, pageSize);
              },
            );
          },
        ),
      ),
    ),
  );

  await tester.pump();
  for (var i = 0; i < 12; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final gesture = await tester.startGesture(
    tester.getCenter(find.byKey(TestKeys.articlePageCurlHotzoneBottomLeft)),
  );
  await gesture.moveBy(backwardDragDelta);
  for (var i = 0; i < 10; i += 1) {
    await tester.pump(const Duration(milliseconds: 16));
  }

  final scene = _lastBackScene(scenes);
  final state = _lastBackDebugState(debugStates);
  final frame = scene?.renderFrame;
  final pageSize = scene == null
      ? Size.zero
      : Size(scene.layout.bounds.pageWidth, scene.layout.bounds.height);
  final partition = frame == null
      ? null
      : resolveBackwardCanonicalSheetFaces(
          BackwardCanonicalSheetInput(
            pageSize: pageSize,
            sheetLocalPolygon: _toSheetLocalPolygon(
              frame.flippingClipArea,
              anchor: frame.flippingAnchor,
              angle: frame.angle,
              direction: frame.visualGeometryDirection,
            ),
            sheetAreaPolygon: frame.flippingClipArea,
            sheetLocalFoldLine: _toSheetLocalLine(
              frame.backwardProjectedFrame?.foldLine,
              anchor: frame.flippingAnchor,
              angle: frame.angle,
              direction: frame.visualGeometryDirection,
            ),
            sheetLocalFreeEdgeLine: _toSheetLocalLine(
              frame.backwardProjectedFrame?.projectedRightEdgeLine,
              anchor: frame.flippingAnchor,
              angle: frame.angle,
              direction: frame.visualGeometryDirection,
            ),
            currentResidualPagePolygon: frame.bottomClipArea,
          ),
        );

  final image = await tester.runAsync<ui.Image>(
    () => _captureBoundaryImage(boundaryKey),
  );
  final bytes = image == null
      ? null
      : await tester.runAsync<Uint8List>(() => _rawRgbaBytes(image));
  final sourceCounts = <String, Map<_ProbeColor, int>>{};
  if (image != null && bytes != null && state != null) {
    for (final source in state.backwardPaintSources) {
      final polygon = source.viewportPolygon;
      final bounds = source.viewportBounds;
      if (polygon.length >= 3) {
        sourceCounts[source.label] = _scanColorsInPolygon(
          imageWidth: image.width,
          imageHeight: image.height,
          bytes: bytes,
          polygon: polygon,
        );
      } else if (bounds != null && !bounds.isEmpty) {
        sourceCounts[source.label] = _scanColorsInPolygon(
          imageWidth: image.width,
          imageHeight: image.height,
          bytes: bytes,
          polygon: <Offset>[
            bounds.topLeft,
            bounds.topRight,
            bounds.bottomRight,
            bounds.bottomLeft,
          ],
        );
      }
    }
  }

  await gesture.up();
  await tester.pump(const Duration(milliseconds: 16));
  await tester.pumpWidget(const MaterialApp(home: SizedBox.shrink()));
  await tester.pump(const Duration(milliseconds: 16));
  image?.dispose();

  return _BackwardEvidence(
    label: label,
    dragDelta: backwardDragDelta,
    capturedBackPageSize: capturedBackPageSize,
    scene: scene,
    debugState: state,
    partition: partition,
    sourceCounts: sourceCounts,
  );
}

Future<List<_BackwardEvidence>> _collectBackwardEvidenceSweep(
  WidgetTester tester, {
  required String labelPrefix,
  required List<Offset> dragDeltas,
}) async {
  final sweep = <_BackwardEvidence>[];
  for (var index = 0; index < dragDeltas.length; index += 1) {
    final evidence = await _collectBackwardEvidence(
      tester,
      label: '$labelPrefix#$index',
      backwardDragDelta: dragDeltas[index],
    );
    _printEvidence(evidence);
    sweep.add(evidence);
  }
  return List<_BackwardEvidence>.unmodifiable(sweep);
}

void _expectContinuousFacePresence(
  List<_BackwardEvidence> sweep, {
  required String label,
  required bool requireRectoEventually,
}) {
  const minVersoArea = 500.0;
  const minRectoArea = 500.0;
  const minVisibleBackWidth = 8.0;
  var rectoActivated = false;
  for (final evidence in sweep) {
    expect(evidence.hasBackScene, isTrue, reason: '$label ${evidence.label}');
    final partition = evidence.partition;
    expect(partition, isNotNull, reason: '$label ${evidence.label}');
    expect(
      partition!.failureReason,
      BackwardCanonicalSheetFailureReason.none,
      reason: '$label ${evidence.label}',
    );
    expect(
      partition.versoFailureReason,
      BackwardCanonicalFaceFailureReason.none,
      reason: '$label ${evidence.label}',
    );
    expect(
      partition.versoArea,
      greaterThan(minVersoArea),
      reason: '$label ${evidence.label}',
    );
    expect(
      evidence.debugState?.backwardBackPaintBounds?.width ?? 0,
      greaterThan(minVisibleBackWidth),
      reason: '$label ${evidence.label}',
    );
    final hasRecto = partition.rectoArea > minRectoArea;
    rectoActivated = rectoActivated || hasRecto;
  }
  if (requireRectoEventually) {
    expect(rectoActivated, isTrue, reason: label);
  }
}

void _expectBackBoundsDoNotJump(
  List<_BackwardEvidence> sweep, {
  required String label,
}) {
  for (var index = 1; index < sweep.length; index += 1) {
    final previous = sweep[index - 1].debugState?.backwardBackPaintBounds;
    final current = sweep[index].debugState?.backwardBackPaintBounds;
    expect(previous, isNotNull, reason: '$label #${index - 1}');
    expect(current, isNotNull, reason: '$label #$index');
    expect(
      (current!.left - previous!.left).abs(),
      lessThan(180),
      reason:
          '$label #$index back left edge jumped; this matches the user-visible '
          'low-angle geometry switch.',
    );
    expect(
      (current.right - previous.right).abs(),
      lessThan(180),
      reason:
          '$label #$index back right edge jumped; this matches the user-visible '
          'low-angle geometry switch.',
    );
  }
}

void _printEvidence(_BackwardEvidence evidence) {
  final scene = evidence.scene;
  final frame = scene?.renderFrame;
  final state = evidence.debugState;
  final leaf = frame?.backwardLeafFrame;
  final projected = frame?.backwardProjectedFrame;
  debugPrint('=== BACK_PHASE0 ${evidence.label} ===');
  debugPrint(
    'drag=${_offset(evidence.dragDelta)} hasScene=${evidence.hasBackScene}',
  );
  debugPrint(
    'frame progress=${frame?.progress.toStringAsFixed(3)} '
    'angle=${frame?.angle.toStringAsFixed(3)} '
    'dir=${frame?.direction.name}/${frame?.renderDirection.name}/'
    '${frame?.visualGeometryDirection.name} routeB=${frame?.routeBSpineMirroredApplied}',
  );
  debugPrint(
    'leaf phase=${leaf?.phase.name} covered=${leaf?.coveredWidthNormalized.toStringAsFixed(3)} '
    'rectoCoverage=${leaf?.rectoCoverageNormalized.toStringAsFixed(3)} '
    'verso=${leaf?.versoRevealWidthNormalized.toStringAsFixed(3)} '
    'rectoReveal=${leaf?.rectoRevealWidthNormalized.toStringAsFixed(3)}',
  );
  debugPrint(
    'lines fold=${_line(projected?.foldLine)} free=${_line(projected?.projectedRightEdgeLine)}',
  );
  debugPrint(
    'debug fail geometry=${state?.backwardGeometryFailureReason.name} '
    'verso=${state?.backwardVersoFailureReason.name} '
    'tex=${state?.activeVersoPageIndex}/${state?.activeVersoSurfaceKind} '
    'frontBack=${state?.backwardFrontBackOverlapWidth?.toStringAsFixed(1)} '
    'backFree=${state?.backwardBackVisibleUncoveredWidth?.toStringAsFixed(1)} '
    'samples=${state?.backwardBackVisibleProbeCount}',
  );
  debugPrint(
    'debug vertices front=${state?.backwardFrontVertexCount} '
    'back=${state?.backwardBackVertexCount} '
    'rawBack=${state?.backwardBackLocalPolygonRaw.length} '
    'probeLocal=${state?.backwardVersoProbeLocalPoints.length} '
    'probeViewport=${state?.backwardVersoProbeViewportPoints.length}',
  );
  debugPrint('partition ${_partition(evidence.partition)}');
  for (final source
      in state?.backwardPaintSources ?? <BackwardPaintSourceDiagnostic>[]) {
    debugPrint(
      'source ${source.summary} polygonPoints=${source.viewportPolygon.length} '
      'colors=${_counts(evidence.sourceCounts[source.label])}',
    );
  }
}

List<ArticlePageData> _diagnosticPages() {
  return List<ArticlePageData>.generate(
    5,
    (index) => ArticlePageData(
      id: 'phase0_diag_$index',
      title: 'SEAM TRACE / ${index + 1}',
      body: 'page ${index + 1}/5\n\nTRACK-${index + 1}',
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

Widget _buildProbeBackPageSurface(
  BuildContext context,
  int pageIndex,
  Size pageSize,
) {
  final color = switch (pageIndex) {
    2 => const Color(0xFF00E5FF),
    3 => const Color(0xFFFFD600),
    _ => const Color(0xFF7C4DFF),
  };
  return ColoredBox(
    color: color,
    child: Align(
      alignment: Alignment.centerRight,
      child: Container(width: pageSize.width * 0.22, color: Colors.black),
    ),
  );
}

StPageFlipScene? _lastBackScene(List<StPageFlipScene> scenes) {
  for (final scene in scenes.reversed) {
    if (scene.renderFrame?.direction == StPageFlipDirection.back) {
      return scene;
    }
  }
  return null;
}

ArticleReadOnlyBookDebugState? _lastBackDebugState(
  List<ArticleReadOnlyBookDebugState> states,
) {
  for (final state in states.reversed) {
    if (state.renderDirection == StPageFlipDirection.back &&
        state.backwardCompositeMode == 'paperFoldBackwardMainline') {
      return state;
    }
  }
  return null;
}

List<Offset> _toSheetLocalPolygon(
  List<Offset> polygon, {
  required Offset anchor,
  required double angle,
  required StPageFlipDirection direction,
}) {
  if (polygon.length < 3) {
    return const <Offset>[];
  }
  return polygon
      .map(
        (point) => _toSheetLocalPoint(
          point,
          anchor: anchor,
          angle: angle,
          direction: direction,
        ),
      )
      .toList(growable: false);
}

(Offset, Offset)? _toSheetLocalLine(
  (Offset, Offset)? line, {
  required Offset anchor,
  required double angle,
  required StPageFlipDirection direction,
}) {
  if (line == null) {
    return null;
  }
  return (
    _toSheetLocalPoint(
      line.$1,
      anchor: anchor,
      angle: angle,
      direction: direction,
    ),
    _toSheetLocalPoint(
      line.$2,
      anchor: anchor,
      angle: angle,
      direction: direction,
    ),
  );
}

Offset _toSheetLocalPoint(
  Offset point, {
  required Offset anchor,
  required double angle,
  required StPageFlipDirection direction,
}) {
  final translated = direction == StPageFlipDirection.back
      ? Offset(anchor.dx - point.dx, point.dy - anchor.dy)
      : Offset(point.dx - anchor.dx, point.dy - anchor.dy);
  return rotatePointForCanvasTransform(translated, angle);
}

Future<ui.Image> _captureBoundaryImage(GlobalKey boundaryKey) async {
  final context = boundaryKey.currentContext;
  expect(context, isNotNull);
  final renderObject = context!.findRenderObject();
  expect(renderObject, isA<RenderRepaintBoundary>());
  return (renderObject as RenderRepaintBoundary).toImage(pixelRatio: 1);
}

Future<Uint8List> _rawRgbaBytes(ui.Image image) async {
  final byteData = await image.toByteData(format: ui.ImageByteFormat.rawRgba);
  expect(byteData, isNotNull);
  return byteData!.buffer.asUint8List();
}

Color _colorAtBytes(
  int imageWidth,
  int imageHeight,
  Uint8List bytes,
  Offset offset,
) {
  final x = offset.dx.round().clamp(0, imageWidth - 1);
  final y = offset.dy.round().clamp(0, imageHeight - 1);
  final index = (y * imageWidth + x) * 4;
  return Color.fromARGB(
    bytes[index + 3],
    bytes[index],
    bytes[index + 1],
    bytes[index + 2],
  );
}

Map<_ProbeColor, int> _scanColorsInPolygon({
  required int imageWidth,
  required int imageHeight,
  required Uint8List bytes,
  required List<Offset> polygon,
}) {
  final counts = <_ProbeColor, int>{};
  final rect = _polygonBounds(polygon);
  if (rect == null || rect.isEmpty) {
    return counts;
  }
  final left = rect.left.round().clamp(0, imageWidth - 1);
  final right = rect.right.round().clamp(left, imageWidth - 1);
  final top = rect.top.round().clamp(0, imageHeight - 1);
  final bottom = rect.bottom.round().clamp(top, imageHeight - 1);

  for (var y = top; y <= bottom; y += 3) {
    for (var x = left; x <= right; x += 3) {
      final point = Offset(x.toDouble(), y.toDouble());
      if (!_pointInPolygon(point, polygon)) {
        continue;
      }
      final probeColor = _classifyProbeColor(
        _colorAtBytes(imageWidth, imageHeight, bytes, point),
      );
      counts.update(probeColor, (count) => count + 1, ifAbsent: () => 1);
    }
  }
  return counts;
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

bool _pointInPolygon(Offset point, List<Offset> polygon) {
  if (polygon.length < 3) {
    return false;
  }
  var inside = false;
  for (var i = 0, j = polygon.length - 1; i < polygon.length; j = i, i += 1) {
    final pi = polygon[i];
    final pj = polygon[j];
    final crosses =
        ((pi.dy > point.dy) != (pj.dy > point.dy)) &&
        (point.dx <
            (pj.dx - pi.dx) *
                    (point.dy - pi.dy) /
                    ((pj.dy - pi.dy) + 0.000001) +
                pi.dx);
    if (crosses) {
      inside = !inside;
    }
  }
  return inside;
}

_ProbeColor _classifyProbeColor(Color color) {
  final red = _channelByte(color.r);
  final green = _channelByte(color.g);
  final blue = _channelByte(color.b);
  if (red < 35 && green < 35 && blue < 35) {
    return _ProbeColor.black;
  }
  if (green > red + 20 && blue > red + 20 && (green - blue).abs() < 70) {
    return _ProbeColor.cyan;
  }
  if (red > green + 40 && red > blue + 40) {
    return _ProbeColor.red;
  }
  if (green > red + 30 && green > blue + 20) {
    return _ProbeColor.green;
  }
  return _ProbeColor.other;
}

int _channelByte(double channel) {
  return (channel * 255.0).round().clamp(0, 255).toInt();
}

String _partition(BackwardCanonicalSheetFaces? partition) {
  if (partition == null) {
    return 'null';
  }
  return 'failure=${partition.failureReason.name} '
      'rectoFail=${partition.rectoFailureReason.name} '
      'versoFail=${partition.versoFailureReason.name} '
      'sheetBounds=${_rect(polygonBounds(partition.sheetLocalPolygon))} '
      'frontBounds=${_rect(polygonBounds(partition.previousFrontRectoLocalPolygon))} '
      'backBounds=${_rect(polygonBounds(partition.previousBackVersoLocalPolygon))} '
      'frontPoly=${_poly(partition.previousFrontRectoLocalPolygon)} '
      'backPoly=${_poly(partition.previousBackVersoLocalPolygon)} '
      'sheet=${partition.sheetLocalPolygon.length} '
      'front=${partition.previousFrontRectoLocalPolygon.length}/'
      '${partition.rectoArea.toStringAsFixed(1)} '
      'back=${partition.previousBackVersoLocalPolygon.length}/'
      '${partition.versoArea.toStringAsFixed(1)} '
      'current=${partition.currentResidualPagePolygon.length} '
      'overlap=${partition.rectoVersoOverlap.toStringAsFixed(1)}';
}

String _counts(Map<_ProbeColor, int>? counts) {
  if (counts == null || counts.isEmpty) {
    return '{}';
  }
  final entries = counts.entries.toList()
    ..sort((a, b) => a.key.name.compareTo(b.key.name));
  return entries.map((entry) => '${entry.key.name}:${entry.value}').join(',');
}

String _line((Offset, Offset)? line) {
  if (line == null) {
    return '-';
  }
  return '${_offset(line.$1)}->${_offset(line.$2)}';
}

String _offset(Offset? offset) {
  if (offset == null) {
    return '-';
  }
  return '${offset.dx.toStringAsFixed(1)},${offset.dy.toStringAsFixed(1)}';
}

String _rect(Rect? rect) {
  if (rect == null) {
    return '-';
  }
  return '${rect.left.toStringAsFixed(1)},${rect.top.toStringAsFixed(1)},'
      '${rect.right.toStringAsFixed(1)},${rect.bottom.toStringAsFixed(1)}';
}

String _poly(List<Offset> polygon) {
  if (polygon.isEmpty) {
    return '-';
  }
  return polygon.map(_offset).join(';');
}

double _edgeLength(Offset a, Offset b) {
  return (b - a).distance;
}

enum _ProbeColor { red, green, cyan, black, other }

class _BackwardEvidence {
  const _BackwardEvidence({
    required this.label,
    required this.dragDelta,
    required this.capturedBackPageSize,
    required this.scene,
    required this.debugState,
    required this.partition,
    required this.sourceCounts,
  });

  final String label;
  final Offset dragDelta;
  final Size? capturedBackPageSize;
  final StPageFlipScene? scene;
  final ArticleReadOnlyBookDebugState? debugState;
  final BackwardCanonicalSheetFaces? partition;
  final Map<String, Map<_ProbeColor, int>> sourceCounts;

  bool get hasBackScene =>
      scene?.renderFrame?.direction == StPageFlipDirection.back;
}
