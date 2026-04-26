import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';
import 'package:quwoquan_app/ui/content/pageflip/types.dart';

@immutable
class ForwardRenderFrameData {
  const ForwardRenderFrameData({
    required this.localPagePoint,
    required this.progress,
    required this.corner,
    required this.pageSize,
    required this.flippingClipArea,
    required this.bottomClipArea,
    required this.flippingAnchor,
    required this.bottomAnchor,
    required this.angle,
    required this.shadow,
  });

  final ui.Offset localPagePoint;
  final double progress;
  final StPageFlipCorner corner;
  final ui.Size pageSize;
  final List<ui.Offset> flippingClipArea;
  final List<ui.Offset> bottomClipArea;
  final ui.Offset flippingAnchor;
  final ui.Offset bottomAnchor;
  final double angle;
  final StPageFlipShadowData? shadow;
}

StPageFlipRenderFrame buildForwardRenderFrame(ForwardRenderFrameData data) {
  final angleBand = resolveForwardCurlAngleBand(
    localPagePoint: data.localPagePoint,
    pageSize: data.pageSize,
    corner: data.corner,
  );
  return StPageFlipRenderFrame(
    localPagePoint: data.localPagePoint,
    progress: data.progress.clamp(0.0, 1.0).toDouble(),
    direction: StPageFlipDirection.forward,
    renderDirection: StPageFlipDirection.forward,
    corner: data.corner,
    flippingClipArea: List<ui.Offset>.unmodifiable(data.flippingClipArea),
    bottomClipArea: List<ui.Offset>.unmodifiable(data.bottomClipArea),
    flippingAnchor: data.flippingAnchor,
    bottomAnchor: data.bottomAnchor,
    angle: data.angle,
    shadow: data.shadow,
    timeline: resolvePageCurlTimeline(
      direction: StPageFlipDirection.forward,
      renderDirection: StPageFlipDirection.forward,
      progress: data.progress,
      localPagePoint: data.localPagePoint,
      pageSize: data.pageSize,
      corner: data.corner,
      angleBand: angleBand,
    ),
  );
}
