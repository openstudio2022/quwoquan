import 'dart:math' as math;
import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_raster_snapshot.dart';
import 'package:quwoquan_app/components/pageflip_book/src/render/soft/pageflip_book_single_backward_soft_scene.dart';

class PageflipBookSingleBackwardSoftRenderer extends StatelessWidget {
  const PageflipBookSingleBackwardSoftRenderer({
    super.key,
    required this.scene,
  });

  final PageflipBookSingleBackwardSoftScene scene;

  @override
  Widget build(BuildContext context) {
    final rasterBundle = scene.rasterBundle;
    final metrics = _PageflipBookSingleBackwardLeafMetrics.fromScene(scene);
    final layers = <Widget>[];

    if (scene.coveredCurrentSurface != null) {
      layers.add(
        Positioned(
          left: scene.pageRect.left,
          top: scene.pageRect.top,
          width: scene.pageRect.width,
          height: scene.pageRect.height,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              _PageflipBookRasterOrWidgetSlice(
                rasterSnapshot: rasterBundle?.coveredCurrent,
                surface: scene.coveredCurrentSurface,
                pageSize: scene.pageSize,
                sliceLeft: 0,
                sliceWidth: scene.pageSize.width,
              ),
              IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      colors: <Color>[
                        scene.shadowColor.withValues(
                          alpha: metrics.coveredWidth <= 0.5
                              ? 0
                              : 0.04 + scene.frame.unrollProgress * 0.06,
                        ),
                        AppColors.transparent,
                        AppColors.transparent,
                      ],
                      stops: <double>[
                        0.0,
                        (metrics.coveredWidth / math.max(scene.pageSize.width, 1))
                            .clamp(0.0, 1.0)
                            .toDouble(),
                        1.0,
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (metrics.laidDownWidth > 0.5) {
      layers.add(
        Positioned(
          left: scene.pageRect.left,
          top: scene.pageRect.top,
          width: metrics.laidDownWidth,
          height: scene.pageRect.height,
          child: Stack(
            fit: StackFit.expand,
            children: <Widget>[
              _PageflipBookRasterOrWidgetSlice(
                rasterSnapshot: rasterBundle?.turningFront,
                surface: scene.turningFrontSurface,
                pageSize: scene.pageSize,
                sliceLeft: 0,
                sliceWidth: metrics.laidDownWidth,
              ),
              IgnorePointer(
                child: DecoratedBox(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      begin: Alignment.centerLeft,
                      end: Alignment.centerRight,
                      colors: <Color>[
                        scene.paperTintColor.withValues(alpha: 0.02),
                        scene.paperTintColor.withValues(alpha: 0.01),
                        scene.shadowColor.withValues(
                          alpha: 0.08 + scene.frame.unrollProgress * 0.08,
                        ),
                      ],
                      stops: const <double>[0.0, 0.78, 1.0],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      );
    }

    if (metrics.boundaryShadowWidth > 0.5) {
      layers.add(
        Positioned(
          left: metrics.shadowAxisX - metrics.boundaryShadowWidth * 0.46,
          top: scene.pageRect.top,
          width: metrics.boundaryShadowWidth,
          height: scene.pageRect.height,
          child: IgnorePointer(
            child: DecoratedBox(
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  begin: Alignment.centerLeft,
                  end: Alignment.centerRight,
                  colors: <Color>[
                    scene.shadowColor.withValues(
                      alpha: 0.16 + scene.frame.unrollProgress * 0.08,
                    ),
                    scene.shadowColor.withValues(
                      alpha: 0.08 + scene.frame.edgeLift * 0.1,
                    ),
                    AppColors.transparent,
                  ],
                  stops: const <double>[0.0, 0.42, 1.0],
                ),
              ),
            ),
          ),
        ),
      );
    }

    final backLeaf = _buildContinuousLeafBand(
      rasterSnapshot: rasterBundle?.turningBack,
      surface: scene.turningBackSurface,
      baseLeft: metrics.curlLeft,
      sliceLeft: metrics.laidDownWidth,
      bandWidth: metrics.curlWidth,
      liftPx: metrics.maxLiftPx,
      rotationY: metrics.backLeafAngle,
      translateX: metrics.backLeafTranslateX,
      translateY: metrics.backLeafTranslateY,
      translateZ: metrics.backLeafTranslateZ,
      alignment: Alignment.centerLeft,
      isRectoEdge: false,
    );
    if (backLeaf != null) {
      layers.add(backLeaf);
    }

    final rectoLeaf = _buildContinuousLeafBand(
      rasterSnapshot: rasterBundle?.turningFront,
      surface: scene.turningFrontSurface,
      baseLeft: metrics.curlLeft + metrics.curlWidth - metrics.rectoRevealWidth,
      sliceLeft:
          metrics.laidDownWidth + metrics.curlWidth - metrics.rectoRevealWidth,
      bandWidth: metrics.rectoRevealWidth,
      liftPx: metrics.maxLiftPx * 0.9,
      rotationY: metrics.frontLeafAngle,
      translateX: metrics.frontLeafTranslateX,
      translateY: metrics.frontLeafTranslateY,
      translateZ: metrics.frontLeafTranslateZ,
      alignment: Alignment.centerRight,
      isRectoEdge: true,
    );
    if (rectoLeaf != null) {
      layers.add(rectoLeaf);
    }

    return Stack(clipBehavior: Clip.none, children: layers);
  }

  Widget? _buildContinuousLeafBand({
    required PageflipBookRasterSnapshot? rasterSnapshot,
    required Widget surface,
    required double baseLeft,
    required double sliceLeft,
    required double bandWidth,
    required double liftPx,
    required double rotationY,
    required double translateX,
    required double translateY,
    required double translateZ,
    required Alignment alignment,
    bool isRectoEdge = false,
  }) {
    if (bandWidth <= 0.5) {
      return null;
    }
    final horizontalInset = math.max(6.0, bandWidth * (isRectoEdge ? 0.1 : 0.1));
    final verticalInset = math.max(8.0, liftPx.abs() * 1.05);
    final positionedLeft = baseLeft - horizontalInset * (isRectoEdge ? 0.65 : 0.18);
    final positionedTop = scene.pageRect.top - verticalInset;
    final pieceWidth = bandWidth + horizontalInset;
    final pieceHeight = scene.pageRect.height + verticalInset * 2;
    return Positioned(
      left: positionedLeft,
      top: positionedTop,
      width: pieceWidth,
      height: pieceHeight,
      child: Transform(
        alignment: alignment,
        transform: Matrix4.identity()
          ..setEntry(3, 2, 0.00225)
          ..translate(translateX, translateY, translateZ)
          ..rotateY(rotationY),
        child: Stack(
          fit: StackFit.expand,
          clipBehavior: Clip.none,
          children: <Widget>[
            ClipPath(
              clipper: _PageflipBookSingleBackwardLeafClipper(
                liftPx: verticalInset,
                isRectoEdge: isRectoEdge,
              ),
              child: Align(
                alignment: isRectoEdge
                    ? Alignment.centerRight
                    : Alignment.centerLeft,
                child: SizedBox(
                  width: bandWidth,
                  height: scene.pageSize.height,
                  child: _PageflipBookRasterOrWidgetSlice(
                    rasterSnapshot: rasterSnapshot,
                    surface: surface,
                    pageSize: scene.pageSize,
                    sliceLeft: sliceLeft,
                    sliceWidth: bandWidth,
                  ),
                ),
              ),
            ),
            IgnorePointer(
              child: CustomPaint(
                painter: _PageflipBookSingleBackwardLeafShadePainter(
                  shadowColor: scene.shadowColor,
                  highlightColor: scene.highlightColor,
                  paperTintColor: scene.paperTintColor,
                  isRectoEdge: isRectoEdge,
                  progress: scene.frame.unrollProgress,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

@immutable
class _PageflipBookSingleBackwardLeafMetrics {
  const _PageflipBookSingleBackwardLeafMetrics({
    required this.coveredWidth,
    required this.laidDownWidth,
    required this.curlWidth,
    required this.rectoRevealWidth,
    required this.curlLeft,
    required this.shadowAxisX,
    required this.boundaryShadowWidth,
    required this.maxLiftPx,
    required this.backLeafAngle,
    required this.frontLeafAngle,
    required this.backLeafTranslateX,
    required this.backLeafTranslateY,
    required this.backLeafTranslateZ,
    required this.frontLeafTranslateX,
    required this.frontLeafTranslateY,
    required this.frontLeafTranslateZ,
  });

  factory _PageflipBookSingleBackwardLeafMetrics.fromScene(
    PageflipBookSingleBackwardSoftScene scene,
  ) {
    final coveredWidth =
        (scene.pageSize.width * scene.frame.coveredWidthNormalized)
            .clamp(0.0, scene.pageSize.width)
            .toDouble();
    final laidDownWidth =
        (scene.pageSize.width * scene.frame.laidDownWidthNormalized)
            .clamp(0.0, coveredWidth)
            .toDouble();
    final curlWidth = math.min(
      math.max(0.0, coveredWidth - laidDownWidth),
      (scene.pageSize.width * scene.frame.curlWidthNormalized)
          .clamp(0.0, scene.pageSize.width)
          .toDouble(),
    );
    final rectoRevealWidth = math.min(
      curlWidth,
      scene.pageSize.width *
          scene.frame.rectoRevealWidthNormalized.clamp(0.0, 1.0).toDouble(),
    );
    final maxLiftPx =
        (scene.pageRect.height * scene.frame.edgeLift * 0.16)
            .clamp(8.0, scene.pageRect.height * 0.12)
            .toDouble();
    final settleDamping = (1 - scene.frame.settleProgress * 0.78)
        .clamp(0.18, 1.0)
        .toDouble();
    final backLeafAngle =
        (-(0.42 +
                    scene.frame.emergenceProgress * 0.44 +
                    scene.frame.unrollProgress * 0.34) *
                settleDamping)
            .clamp(-1.18, -0.16)
            .toDouble();
    final frontLeafAngle = (backLeafAngle * 0.38).clamp(-0.48, -0.06).toDouble();
    final liftDirection = scene.frame.liftDirection;
    return _PageflipBookSingleBackwardLeafMetrics(
      coveredWidth: coveredWidth,
      laidDownWidth: laidDownWidth,
      curlWidth: curlWidth,
      rectoRevealWidth: rectoRevealWidth * 0.72,
      curlLeft: scene.pageRect.left + laidDownWidth,
      shadowAxisX: scene.pageRect.left +
          scene.pageSize.width *
              scene.frame.shadowAxisNormalized.clamp(0.0, 1.0).toDouble(),
      boundaryShadowWidth: math.max(scene.pageSize.width * 0.1, curlWidth * 1.2),
      maxLiftPx: maxLiftPx,
      backLeafAngle: backLeafAngle,
      frontLeafAngle: frontLeafAngle,
      backLeafTranslateX:
          (-curlWidth * (0.06 + scene.frame.unrollProgress * 0.08))
              .toDouble(),
      backLeafTranslateY:
          (liftDirection *
                  maxLiftPx *
                  (0.74 + scene.frame.emergenceProgress * 0.18))
              .toDouble(),
      backLeafTranslateZ:
          (maxLiftPx * (0.14 + scene.frame.unrollProgress * 0.08)).toDouble(),
      frontLeafTranslateX:
          (-rectoRevealWidth * (0.02 + scene.frame.unrollProgress * 0.025))
              .toDouble(),
      frontLeafTranslateY:
          (liftDirection * maxLiftPx * (0.52 + scene.frame.unrollProgress * 0.1))
              .toDouble(),
      frontLeafTranslateZ:
          (maxLiftPx * (0.02 + scene.frame.unrollProgress * 0.02)).toDouble(),
    );
  }

  final double coveredWidth;
  final double laidDownWidth;
  final double curlWidth;
  final double rectoRevealWidth;
  final double curlLeft;
  final double shadowAxisX;
  final double boundaryShadowWidth;
  final double maxLiftPx;
  final double backLeafAngle;
  final double frontLeafAngle;
  final double backLeafTranslateX;
  final double backLeafTranslateY;
  final double backLeafTranslateZ;
  final double frontLeafTranslateX;
  final double frontLeafTranslateY;
  final double frontLeafTranslateZ;
}

class _PageflipBookSingleBackwardLeafClipper extends CustomClipper<Path> {
  const _PageflipBookSingleBackwardLeafClipper({
    required this.liftPx,
    required this.isRectoEdge,
  });

  final double liftPx;
  final bool isRectoEdge;

  @override
  Path getClip(Size size) {
    final topLift = liftPx.clamp(0.0, size.height * 0.16).toDouble();
    final bottomLift = (liftPx * 0.9).clamp(0.0, size.height * 0.16).toDouble();
    final rightInset = isRectoEdge ? size.width * 0.08 : 0.0;
    final rightX = math.max(size.width * 0.72, size.width - rightInset);
    return Path()
      ..moveTo(0, topLift * 0.68)
      ..quadraticBezierTo(size.width * 0.18, 0, size.width * 0.56, 0)
      ..quadraticBezierTo(size.width * 0.86, topLift * 0.12, rightX, topLift * 0.42)
      ..lineTo(rightX, size.height - bottomLift * 0.42)
      ..quadraticBezierTo(
        size.width * 0.86,
        size.height - bottomLift * 0.12,
        size.width * 0.56,
        size.height,
      )
      ..quadraticBezierTo(
        size.width * 0.18,
        size.height,
        0,
        size.height - bottomLift * 0.68,
      )
      ..close();
  }

  @override
  bool shouldReclip(covariant _PageflipBookSingleBackwardLeafClipper oldClipper) {
    return oldClipper.liftPx != liftPx ||
        oldClipper.isRectoEdge != isRectoEdge;
  }
}

class _PageflipBookSingleBackwardLeafShadePainter extends CustomPainter {
  const _PageflipBookSingleBackwardLeafShadePainter({
    required this.shadowColor,
    required this.highlightColor,
    required this.paperTintColor,
    required this.isRectoEdge,
    required this.progress,
  });

  final Color shadowColor;
  final Color highlightColor;
  final Color paperTintColor;
  final bool isRectoEdge;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) {
      return;
    }
    final rect = Offset.zero & size;
    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.centerLeft,
          end: Alignment.centerRight,
          colors: <Color>[
            highlightColor.withValues(
              alpha: isRectoEdge ? 0.18 + progress * 0.08 : 0.08 + progress * 0.05,
            ),
            paperTintColor.withValues(alpha: isRectoEdge ? 0.1 : 0.08),
            shadowColor.withValues(
              alpha: isRectoEdge ? 0.16 + progress * 0.08 : 0.12 + progress * 0.08,
            ),
          ],
          stops: const <double>[0.0, 0.42, 1.0],
        ).createShader(rect),
    );
    canvas.drawRect(
      rect,
      Paint()
        ..shader = LinearGradient(
          begin: Alignment.topCenter,
          end: Alignment.bottomCenter,
          colors: <Color>[
            shadowColor.withValues(alpha: 0.04),
            AppColors.transparent,
            shadowColor.withValues(alpha: 0.05),
          ],
          stops: const <double>[0.0, 0.22, 1.0],
        ).createShader(rect),
    );
  }

  @override
  bool shouldRepaint(
    covariant _PageflipBookSingleBackwardLeafShadePainter oldDelegate,
  ) {
    return oldDelegate.shadowColor != shadowColor ||
        oldDelegate.highlightColor != highlightColor ||
        oldDelegate.paperTintColor != paperTintColor ||
        oldDelegate.isRectoEdge != isRectoEdge ||
        oldDelegate.progress != progress;
  }
}

class _PageflipBookRasterOrWidgetSlice extends StatelessWidget {
  const _PageflipBookRasterOrWidgetSlice({
    required this.rasterSnapshot,
    required this.surface,
    required this.pageSize,
    required this.sliceLeft,
    required this.sliceWidth,
  });

  final PageflipBookRasterSnapshot? rasterSnapshot;
  final Widget? surface;
  final Size pageSize;
  final double sliceLeft;
  final double sliceWidth;

  @override
  Widget build(BuildContext context) {
    if (rasterSnapshot != null) {
      return CustomPaint(
        painter: _PageflipBookRasterSlicePainter(
          snapshot: rasterSnapshot!,
          sliceLeft: sliceLeft,
          sliceWidth: sliceWidth,
        ),
      );
    }
    if (surface == null) {
      return const SizedBox.shrink();
    }
    return _PageflipBookSurfaceSlice(
      surface: surface!,
      sliceLeft: sliceLeft,
      sliceWidth: sliceWidth,
      pageSize: pageSize,
    );
  }
}

class _PageflipBookSurfaceSlice extends StatelessWidget {
  const _PageflipBookSurfaceSlice({
    required this.surface,
    required this.sliceLeft,
    required this.sliceWidth,
    required this.pageSize,
  });

  final Widget surface;
  final double sliceLeft;
  final double sliceWidth;
  final Size pageSize;

  @override
  Widget build(BuildContext context) {
    final clampedLeft = sliceLeft.clamp(0.0, pageSize.width).toDouble();
    final clampedWidth = sliceWidth
        .clamp(0.0, math.max(0.0, pageSize.width - clampedLeft))
        .toDouble();
    if (clampedWidth <= 0) {
      return const SizedBox.shrink();
    }
    return ClipRect(
      child: Transform.translate(
        offset: Offset(-clampedLeft, 0),
        child: OverflowBox(
          alignment: Alignment.topLeft,
          minWidth: pageSize.width,
          maxWidth: pageSize.width,
          minHeight: pageSize.height,
          maxHeight: pageSize.height,
          child: SizedBox(
            width: pageSize.width,
            height: pageSize.height,
            child: surface,
          ),
        ),
      ),
    );
  }
}

class _PageflipBookRasterSlicePainter extends CustomPainter {
  const _PageflipBookRasterSlicePainter({
    required this.snapshot,
    required this.sliceLeft,
    required this.sliceWidth,
  });

  final PageflipBookRasterSnapshot snapshot;
  final double sliceLeft;
  final double sliceWidth;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) {
      return;
    }
    final srcRect = snapshot.sourceRectForLogicalSlice(
      left: sliceLeft,
      width: sliceWidth,
    );
    if (srcRect.width <= 0 || srcRect.height <= 0) {
      return;
    }
    canvas.drawImageRect(snapshot.image, srcRect, Offset.zero & size, Paint());
  }

  @override
  bool shouldRepaint(covariant _PageflipBookRasterSlicePainter oldDelegate) {
    return oldDelegate.snapshot.image != snapshot.image ||
        oldDelegate.sliceLeft != sliceLeft ||
        oldDelegate.sliceWidth != sliceWidth;
  }
}
