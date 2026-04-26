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
  final double maxShadowOpacity;
  final StPageFlipShadowData? shadow;
}

/// Builds a backward [StPageFlipRenderFrame] by reusing the forward
/// [StPageFlipCalculation] on a horizontally-mirrored drag point. This keeps
/// the geometry main line unified with the forward path: instead of a custom
/// 1D rectangular fold, the polygon clipping/intersection logic that already
/// drives the forward flip is reused, then mirrored back for the backward
/// rendering pipeline.
StPageFlipRenderFrame buildBackwardRenderFrame(BackwardRenderFrameData data) {
  return _buildBackwardRenderFrameMirrored(data, dynamicVariant: false);
}

StPageFlipRenderFrame buildBackwardDynamicRenderFrame(
  BackwardRenderFrameData data,
) {
  return _buildBackwardRenderFrameMirrored(data, dynamicVariant: true);
}

StPageFlipRenderFrame _buildBackwardRenderFrameMirrored(
  BackwardRenderFrameData data, {
  required bool dynamicVariant,
}) {
  final progress = data.progress.clamp(0.0, 1.0).toDouble();
  final renderDirection = resolvePageFlipRenderDirection(
    direction: StPageFlipDirection.back,
    orientation: data.orientation,
    reversePose: null,
  );
  final pageWidth = data.pageSize.width;
  final pageHeight = data.pageSize.height;

  final mirroredPos = _mirrorXOffset(
    ui.Offset(
      data.localPagePoint.dx.clamp(0.0, pageWidth).toDouble(),
      data.localPagePoint.dy.clamp(0.0, pageHeight).toDouble(),
    ),
    pageWidth,
  );

  final forwardCalculation = StPageFlipCalculation(
    direction: StPageFlipDirection.forward,
    corner: data.corner,
    pageWidth: pageWidth,
    pageHeight: pageHeight,
  );
  final ok = forwardCalculation.calc(mirroredPos);

  late final List<ui.Offset> flippingClipArea;
  late final List<ui.Offset> bottomClipArea;
  late final ui.Offset flippingAnchor;
  late final ui.Offset bottomAnchor;
  late final double angle;
  if (ok) {
    flippingClipArea = _mirrorPolygonX(
      forwardCalculation.getFlippingClipArea(),
      pageWidth,
    );
    bottomClipArea = _mirrorPolygonX(
      forwardCalculation.getBottomClipArea(),
      pageWidth,
    );
    flippingAnchor = _mirrorXOffset(
      forwardCalculation.getActiveCorner(),
      pageWidth,
    );
    // Bottom layer for backward stays anchored at the right page's spine
    // (book-coords origin), mirroring the forward semantic where the bottom
    // layer stays put while the lifted polygon moves over it.
    bottomAnchor = ui.Offset.zero;
    angle = -forwardCalculation.getAngle();
  } else {
    // The forward calc rejects degenerate inputs (drag right at the corner
    // with no perpendicular displacement). Fall back to an empty geometry so
    // the dynamic layers render nothing for this frame; the static stage
    // remains responsible for the rest position.
    flippingClipArea = const <ui.Offset>[];
    bottomClipArea = const <ui.Offset>[];
    flippingAnchor = ui.Offset(
      0,
      data.corner == StPageFlipCorner.top ? 0 : pageHeight,
    );
    bottomAnchor = ui.Offset.zero;
    angle = 0.0;
  }

  // Backward leaf frame is retained for diagnostics/timeline only — it no
  // longer drives geometry. The unified mainline above is the source of truth
  // for all clipping/rotation values.
  final backwardLeafFrame = resolveArticlePageBackwardLeafFrame(
    direction: StPageFlipDirection.back,
    progress: progress,
    reversePose: null,
  );

  final replayLocalPoint = resolveBackwardReplayLocalPagePoint(
    localPagePoint: data.localPagePoint,
    pageSize: data.pageSize,
  );
  final angleBand = resolveForwardCurlAngleBand(
    localPagePoint: replayLocalPoint,
    pageSize: data.pageSize,
    corner: data.corner,
  );

  return StPageFlipRenderFrame(
    localPagePoint: data.localPagePoint,
    progress: progress,
    direction: StPageFlipDirection.back,
    renderDirection: renderDirection,
    corner: data.corner,
    flippingClipArea: List<ui.Offset>.unmodifiable(
      flippingClipArea.isEmpty ? data.flippingClipArea : flippingClipArea,
    ),
    bottomClipArea: List<ui.Offset>.unmodifiable(
      bottomClipArea.isEmpty ? data.bottomClipArea : bottomClipArea,
    ),
    flippingAnchor: ok ? flippingAnchor : data.flippingAnchor,
    bottomAnchor: bottomAnchor,
    angle: ok ? angle : (dynamicVariant ? data.angle : 0.0),
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
  );
}

ui.Offset _mirrorXOffset(ui.Offset point, double width) =>
    ui.Offset(width - point.dx, point.dy);

List<ui.Offset> _mirrorPolygonX(List<ui.Offset> polygon, double width) {
  if (polygon.isEmpty) {
    return const <ui.Offset>[];
  }
  return polygon.map((p) => _mirrorXOffset(p, width)).toList(growable: false);
}
