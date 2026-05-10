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

@immutable
class _BackwardVisualGeometry {
  const _BackwardVisualGeometry({
    required this.direction,
    required this.localPagePoint,
    required this.flippingClipArea,
    required this.bottomClipArea,
    required this.flippingAnchor,
    required this.bottomAnchor,
    required this.angle,
    required this.foldLine,
    required this.freeEdgeLine,
    required this.foldLineSource,
    required this.edgeLineSource,
  });

  final StPageFlipDirection direction;
  final ui.Offset localPagePoint;
  final List<ui.Offset> flippingClipArea;
  final List<ui.Offset> bottomClipArea;
  final ui.Offset flippingAnchor;
  final ui.Offset bottomAnchor;
  final double angle;
  final (ui.Offset, ui.Offset)? foldLine;
  final (ui.Offset, ui.Offset)? freeEdgeLine;
  final String foldLineSource;
  final String edgeLineSource;
}

/// Builds a backward [StPageFlipRenderFrame] with BACK semantic direction and
/// forward-isomorphic visual geometry in portrait mode.
///
/// 路线 B 主线（参见 `.cursor/rules/12-pageflip-backward-mainline.mdc`）：
/// builder 不再产出任何派生多边形（previousFoldSurfacePolygon/previousFront
/// FoldPolygon/previousBackFoldPolygon/currentResidualPolygon 等）。portrait
/// BACK 的 sheet/current/F/E 使用 forward-isomorphic calculation，页面绑定和
/// 翻页提交语义仍由 `direction == back` 决定。
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

  final visualGeometry = _resolveBackwardVisualGeometry(data);

  final backwardLeafFrame = resolveArticlePageBackwardLeafFrame(
    direction: StPageFlipDirection.back,
    progress: progress,
    reversePose: null,
  )!;
  final backwardProjectedFrame = _buildBackwardProjectedFrame(
    localPagePoint: visualGeometry.localPagePoint,
    foldLine: visualGeometry.foldLine,
    freeEdgeLine: visualGeometry.freeEdgeLine,
    pageSize: data.pageSize,
    foldLineSource: visualGeometry.foldLineSource,
    edgeLineSource: visualGeometry.edgeLineSource,
  );

  final angleBand = resolveForwardCurlAngleBand(
    localPagePoint: resolveBackwardVisualReplayLocalPagePoint(
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
    visualGeometryDirection: visualGeometry.direction,
    corner: data.corner,
    flippingClipArea: List<ui.Offset>.unmodifiable(
      visualGeometry.flippingClipArea,
    ),
    bottomClipArea: List<ui.Offset>.unmodifiable(visualGeometry.bottomClipArea),
    flippingAnchor: visualGeometry.flippingAnchor,
    bottomAnchor: visualGeometry.bottomAnchor,
    angle: visualGeometry.angle,
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
    routeBSpineMirroredApplied:
        visualGeometry.direction == StPageFlipDirection.forward,
  );
}

_BackwardVisualGeometry _resolveBackwardVisualGeometry(
  BackwardRenderFrameData data,
) {
  if (data.orientation == StPageFlipOrientation.portrait) {
    final replayPoint = resolveBackwardVisualReplayLocalPagePoint(
      localPagePoint: data.localPagePoint,
      pageSize: data.pageSize,
    );
    final forwardCalculation = StPageFlipCalculation(
      direction: StPageFlipDirection.forward,
      corner: data.corner,
      pageWidth: data.pageSize.width,
      pageHeight: data.pageSize.height,
    );
    if (forwardCalculation.calc(replayPoint)) {
      final canonicalGeometry = forwardCalculation.getCanonicalFoldGeometry();
      return _BackwardVisualGeometry(
        direction: StPageFlipDirection.forward,
        localPagePoint: replayPoint,
        flippingClipArea: forwardCalculation.getFlippingClipArea(),
        bottomClipArea: forwardCalculation.getBottomClipArea(),
        flippingAnchor: forwardCalculation.getActiveCorner(),
        bottomAnchor: forwardCalculation.getBottomPagePosition(),
        angle: forwardCalculation.getAngle(),
        foldLine: canonicalGeometry?.foldLine,
        freeEdgeLine: canonicalGeometry?.freeEdgeLine,
        foldLineSource: 'backwardForwardIsomorphicFoldLine',
        edgeLineSource: 'backwardForwardIsomorphicFreeEdgeLine',
      );
    }
  }

  return _BackwardVisualGeometry(
    direction: StPageFlipDirection.back,
    localPagePoint: data.localPagePoint,
    flippingClipArea: data.flippingClipArea,
    bottomClipArea: data.bottomClipArea,
    flippingAnchor: data.flippingAnchor,
    bottomAnchor: data.bottomAnchor,
    angle: data.angle,
    foldLine: data.foldLine,
    freeEdgeLine: data.freeEdgeLine,
    foldLineSource: 'backwardCanonicalFoldLine',
    edgeLineSource: 'backwardCanonicalFreeEdgeLine',
  );
}

ArticlePageBackwardProjectedFrame? _buildBackwardProjectedFrame({
  required ui.Offset localPagePoint,
  required (ui.Offset, ui.Offset)? foldLine,
  required (ui.Offset, ui.Offset)? freeEdgeLine,
  required ui.Size pageSize,
  required String foldLineSource,
  required String edgeLineSource,
}) {
  if (pageSize.width <= 0 || pageSize.height <= 0) {
    return null;
  }
  final preserveForwardIsomorphicLines =
      foldLineSource == 'backwardForwardIsomorphicFoldLine';
  final canonicalFoldLine = foldLine == null
      ? null
      : preserveForwardIsomorphicLines
      ? _orderLineTopToBottom(foldLine)
      : _clipLineToPageRect(_orderLineTopToBottom(foldLine), pageSize);
  final canonicalFreeEdgeLine = freeEdgeLine == null
      ? null
      : preserveForwardIsomorphicLines
      ? _orderLineTopToBottom(freeEdgeLine)
      : _clipLineToPageRect(_orderLineTopToBottom(freeEdgeLine), pageSize);
  if (canonicalFoldLine == null || canonicalFreeEdgeLine == null) {
    return null;
  }
  return ArticlePageBackwardProjectedFrame(
    foldLine: canonicalFoldLine,
    projectedRightEdgeLine: canonicalFreeEdgeLine,
    replayLocalPoint: localPagePoint,
    edgeEnteredPage: true,
    foldLineSource: foldLineSource,
    edgeLineSource: edgeLineSource,
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
