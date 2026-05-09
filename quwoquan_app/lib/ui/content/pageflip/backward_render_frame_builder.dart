import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/geometry.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class BackwardRenderFrameData {
  const BackwardRenderFrameData({
    required this.localPagePoint,
    required this.progress,
    required this.orientation,
    required this.corner,
    required this.pageSize,
    required this.flippingClipArea,
    required this.bottomClipArea,
    required this.flippingAnchor,
    required this.bottomAnchor,
    required this.angle,
    required this.foldLine,
    required this.freeEdgeLine,
    required this.maxShadowOpacity,
    this.shadow,
  });

  final ui.Offset localPagePoint;
  final double progress;
  final StPageFlipOrientation orientation;
  final StPageFlipCorner corner;
  final ui.Size pageSize;
  final List<ui.Offset> flippingClipArea;
  final List<ui.Offset> bottomClipArea;
  final ui.Offset flippingAnchor;
  final ui.Offset bottomAnchor;
  final double angle;
  final (ui.Offset, ui.Offset)? foldLine;
  final (ui.Offset, ui.Offset)? freeEdgeLine;
  final double maxShadowOpacity;
  final StPageFlipShadowData? shadow;
}

/// Builds a backward [StPageFlipRenderFrame] from the native BACK
/// [StPageFlipCalculation] outputs. Backward is a first-class paper-fold
/// direction; it must not recreate a forward calculation and mirror it.
///
/// 路线 B 主线（参见 `.cursor/rules/12-pageflip-backward-mainline.mdc`）：
/// builder 不再产出任何派生多边形（previousFoldSurfacePolygon/previousFront
/// FoldPolygon/previousBackFoldPolygon/currentResidualPolygon 等），sheet 与
/// current 的真相源直接是 `flippingClipArea / bottomClipArea`。projected frame
/// 仅承载 fold line 与 free-edge line 用于 diagnostic guide layer。
StPageFlipRenderFrame buildBackwardRenderFrame(BackwardRenderFrameData data) {
  return _buildBackwardRenderFrame(data);
}

StPageFlipRenderFrame buildBackwardDynamicRenderFrame(
  BackwardRenderFrameData data,
) {
  return _buildBackwardRenderFrame(data);
}

(ui.Offset, ui.Offset) _orderLineTopToBottom((ui.Offset, ui.Offset) line) {
  if (line.$1.dy < line.$2.dy) {
    return line;
  }
  if (line.$1.dy > line.$2.dy) {
    return (line.$2, line.$1);
  }
  return line.$1.dx <= line.$2.dx ? line : (line.$2, line.$1);
}

StPageFlipRenderFrame _buildBackwardRenderFrame(BackwardRenderFrameData data) {
  final progress = data.progress.clamp(0.0, 1.0).toDouble();
  final renderDirection = resolvePageFlipRenderDirection(
    direction: StPageFlipDirection.back,
    orientation: data.orientation,
    reversePose: null,
  );

  // Native StPageFlip BACK: frame builder must pass the BACK calculation
  // outputs through unchanged. The visual projection is direction-aware in the
  // host (`drawSoft` equivalent), not pre-mirrored here. In single-page
  // portrait, this keeps the spine at the visible current page's left edge.
  final flippingClipArea = data.flippingClipArea;
  final bottomClipArea = data.bottomClipArea;
  final flippingAnchor = data.flippingAnchor;
  final bottomAnchor = data.bottomAnchor;
  final foldLine = data.foldLine;
  final freeEdgeLine = data.freeEdgeLine;

  final backwardLeafFrame = resolveArticlePageBackwardLeafFrame(
    direction: StPageFlipDirection.back,
    progress: progress,
    reversePose: null,
  )!;
  final backwardProjectedFrame = _buildBackwardProjectedFrame(
    localPagePoint: data.localPagePoint,
    foldLine: foldLine,
    freeEdgeLine: freeEdgeLine,
    pageSize: data.pageSize,
  );

  final angleBand = resolveForwardCurlAngleBand(
    localPagePoint: resolveBackwardReplayLocalPagePoint(
      localPagePoint: data.localPagePoint,
      pageSize: data.pageSize,
    ),
    pageSize: data.pageSize,
    corner: data.corner,
  );

  return StPageFlipRenderFrame(
    localPagePoint: data.localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.back,
    renderDirection: renderDirection,
    corner: data.corner,
    flippingClipArea: List<ui.Offset>.unmodifiable(flippingClipArea),
    bottomClipArea: List<ui.Offset>.unmodifiable(bottomClipArea),
    flippingAnchor: flippingAnchor,
    bottomAnchor: bottomAnchor,
    angle: data.angle,
    shadow: data.shadow,
    timeline: resolvePageCurlTimeline(
      direction: StPageFlipDirection.back,
      renderDirection: renderDirection,
      progress: progress,
      localPagePoint: data.localPagePoint,
      pageSize: data.pageSize,
      corner: data.corner,
      angleBand: angleBand,
      reversePose: null,
    ),
    reversePose: null,
    backwardLeafFrame: backwardLeafFrame,
    backwardProjectedFrame: backwardProjectedFrame,
    routeBSpineMirroredApplied: false,
  );
}

ArticlePageBackwardProjectedFrame? _buildBackwardProjectedFrame({
  required ui.Offset localPagePoint,
  required (ui.Offset, ui.Offset)? foldLine,
  required (ui.Offset, ui.Offset)? freeEdgeLine,
  required ui.Size pageSize,
}) {
  if (pageSize.width <= 0 || pageSize.height <= 0) {
    return null;
  }
  final canonicalFoldLine = foldLine == null
      ? null
      : _clipLineToPageRect(_orderLineTopToBottom(foldLine), pageSize);
  final canonicalFreeEdgeLine = freeEdgeLine == null
      ? null
      : _clipLineToPageRect(_orderLineTopToBottom(freeEdgeLine), pageSize);
  if (canonicalFoldLine == null || canonicalFreeEdgeLine == null) {
    return null;
  }
  return ArticlePageBackwardProjectedFrame(
    foldLine: canonicalFoldLine,
    projectedRightEdgeLine: canonicalFreeEdgeLine,
    replayLocalPoint: localPagePoint,
    edgeEnteredPage: true,
    foldLineSource: 'backwardCanonicalFoldLine',
    edgeLineSource: 'backwardCanonicalFreeEdgeLine',
  );
}

(ui.Offset, ui.Offset)? _clipLineToPageRect(
  (ui.Offset, ui.Offset) line,
  ui.Size pageSize,
) {
  final orderedLine = _orderLineTopToBottom(line);
  final bounds = ui.Rect.fromLTWH(
    -0.5,
    -0.5,
    pageSize.width + 1,
    pageSize.height + 1,
  );
  final rectEdges = <List<ui.Offset>>[
    <ui.Offset>[ui.Offset.zero, ui.Offset(pageSize.width, 0)],
    <ui.Offset>[
      ui.Offset(pageSize.width, 0),
      ui.Offset(pageSize.width, pageSize.height),
    ],
    <ui.Offset>[
      ui.Offset(pageSize.width, pageSize.height),
      ui.Offset(0, pageSize.height),
    ],
    <ui.Offset>[ui.Offset(0, pageSize.height), ui.Offset.zero],
  ];
  final intersections = <ui.Offset>[];
  for (final edge in rectEdges) {
    ui.Offset? point;
    try {
      point = pointInRect(
        bounds,
        intersectLines(<ui.Offset>[orderedLine.$1, orderedLine.$2], edge),
      );
    } catch (_) {
      continue;
    }
    if (point != null &&
        intersections.every(
          (existing) => distanceBetweenPoints(existing, point) > 0.5,
        )) {
      intersections.add(point);
    }
  }
  if (intersections.length >= 2) {
    intersections.sort((a, b) {
      final byY = a.dy.compareTo(b.dy);
      return byY == 0 ? a.dx.compareTo(b.dx) : byY;
    });
    return _orderLineTopToBottom((intersections.first, intersections.last));
  }
  final insidePoints = <ui.Offset>[
    if (pointInRect(bounds, orderedLine.$1) != null) orderedLine.$1,
    if (pointInRect(bounds, orderedLine.$2) != null) orderedLine.$2,
  ];
  if (insidePoints.length >= 2) {
    return _orderLineTopToBottom((insidePoints.first, insidePoints.last));
  }
  if (intersections.length == 1 && insidePoints.length == 1) {
    return _orderLineTopToBottom((intersections.first, insidePoints.first));
  }
  return null;
}
