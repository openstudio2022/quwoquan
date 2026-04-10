import 'dart:math' as math;
import 'dart:ui' as ui;

import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/pageflip/render_frame.dart';

@immutable
class ArticlePageBackwardLeafRenderScene {
  const ArticlePageBackwardLeafRenderScene({
    required this.pageRect,
    required this.pageSize,
    required this.leafRecto,
    required this.leafVerso,
    required this.frame,
    required this.shadowColor,
    required this.highlightColor,
    required this.paperTintColor,
  });

  final Rect pageRect;
  final Size pageSize;
  final Widget leafRecto;
  final Widget leafVerso;
  final ArticlePageBackwardLeafFrame frame;
  final Color shadowColor;
  final Color highlightColor;
  final Color paperTintColor;
}

class ArticlePageBackwardLeafRenderer extends StatelessWidget {
  const ArticlePageBackwardLeafRenderer({super.key, required this.scene});

  final ArticlePageBackwardLeafRenderScene scene;

  @override
  Widget build(BuildContext context) {
    final laidDownWidth = scene.pageSize.width * scene.frame.laidDownWidthNormalized;
    final curlWidth = scene.pageSize.width * scene.frame.curlWidthNormalized;
    final rectoRevealWidth = scene.pageSize.width *
        scene.frame.rectoRevealWidthNormalized.clamp(0.0, 1.0).toDouble();
    final boundaryShadowWidth = math.max(
      scene.pageSize.width * 0.08,
      curlWidth * 1.45,
    );
    final liftPx = scene.pageRect.width * scene.frame.edgeLift * 0.08;
    final curlLeft = scene.pageRect.left + laidDownWidth;

    return Stack(
      children: <Widget>[
        if (laidDownWidth > 0.5)
          Positioned(
            left: scene.pageRect.left,
            top: scene.pageRect.top,
            width: laidDownWidth,
            height: scene.pageRect.height,
            child: Stack(
              fit: StackFit.expand,
              children: <Widget>[
                _ClippedLeafSurface(
                  surface: scene.leafRecto,
                  visibleWidth: laidDownWidth,
                  pageSize: scene.pageSize,
                  alignment: Alignment.centerLeft,
                ),
                IgnorePointer(
                  child: DecoratedBox(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.centerLeft,
                        end: Alignment.centerRight,
                        colors: <Color>[
                          AppColors.transparent,
                          scene.paperTintColor.withValues(alpha: 0.02),
                          scene.shadowColor.withValues(
                            alpha: 0.1 + scene.frame.unrollProgress * 0.08,
                          ),
                        ],
                        stops: const <double>[0.0, 0.72, 1.0],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
        if (boundaryShadowWidth > 0.5)
          Positioned(
            left: curlLeft - boundaryShadowWidth * 0.36,
            top: scene.pageRect.top,
            width: boundaryShadowWidth,
            height: scene.pageRect.height,
            child: IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                    colors: <Color>[
                      scene.shadowColor.withValues(
                        alpha: 0.16 + scene.frame.unrollProgress * 0.12,
                      ),
                      scene.shadowColor.withValues(
                        alpha: 0.08 + scene.frame.emergenceProgress * 0.06,
                      ),
                      AppColors.transparent,
                    ],
                    stops: const <double>[0.0, 0.36, 1.0],
                  ),
                ),
              ),
            ),
          ),
        if (curlWidth > 0.5)
          Positioned(
            left: curlLeft,
            top: scene.pageRect.top - liftPx,
            width: curlWidth,
            height: scene.pageRect.height + liftPx * 2,
            child: _BackwardLeafCurlFlap(
              pageSize: scene.pageSize,
              leafRecto: scene.leafRecto,
              leafVerso: scene.leafVerso,
              curlWidth: curlWidth,
              rectoRevealWidth: math.min(rectoRevealWidth, curlWidth),
              liftPx: liftPx,
              unrollProgress: scene.frame.unrollProgress,
              settleProgress: scene.frame.settleProgress,
              shadowColor: scene.shadowColor,
              highlightColor: scene.highlightColor,
              paperTintColor: scene.paperTintColor,
            ),
          ),
      ],
    );
  }
}

class _BackwardLeafCurlFlap extends StatelessWidget {
  const _BackwardLeafCurlFlap({
    required this.pageSize,
    required this.leafRecto,
    required this.leafVerso,
    required this.curlWidth,
    required this.rectoRevealWidth,
    required this.liftPx,
    required this.unrollProgress,
    required this.settleProgress,
    required this.shadowColor,
    required this.highlightColor,
    required this.paperTintColor,
  });

  final Size pageSize;
  final Widget leafRecto;
  final Widget leafVerso;
  final double curlWidth;
  final double rectoRevealWidth;
  final double liftPx;
  final double unrollProgress;
  final double settleProgress;
  final Color shadowColor;
  final Color highlightColor;
  final Color paperTintColor;

  @override
  Widget build(BuildContext context) {
    final flapAngle = (ui.lerpDouble(-1.34, -0.2, unrollProgress) ?? -0.64) *
        (1 - settleProgress * 0.72);
    final flapShadow = 0.1 + (1 - settleProgress) * 0.12;
    final paperWashAlpha = 0.04 + (1 - settleProgress) * 0.06;
    return ClipRect(
      child: Transform(
        alignment: Alignment.centerLeft,
        transform: Matrix4.identity()
          ..setEntry(3, 2, 0.002)
          ..translate(0.0, liftPx * 0.12, 0.0)
          ..rotateY(flapAngle),
        child: Stack(
          fit: StackFit.expand,
          children: <Widget>[
            _ClippedLeafSurface(
              surface: leafVerso,
              visibleWidth: curlWidth,
              pageSize: pageSize,
              alignment: Alignment.centerLeft,
            ),
            if (rectoRevealWidth > 0.5)
              Align(
                alignment: Alignment.centerLeft,
                child: SizedBox(
                  width: rectoRevealWidth,
                  height: pageSize.height + liftPx * 2,
                  child: _ClippedLeafSurface(
                    surface: leafRecto,
                    visibleWidth: rectoRevealWidth,
                    pageSize: pageSize,
                    alignment: Alignment.centerLeft,
                  ),
                ),
              ),
            IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.centerLeft,
                    end: Alignment.centerRight,
                    colors: <Color>[
                      highlightColor.withValues(alpha: 0.14 + unrollProgress * 0.1),
                      paperTintColor.withValues(alpha: paperWashAlpha),
                      shadowColor.withValues(alpha: flapShadow),
                    ],
                    stops: const <double>[0.0, 0.38, 1.0],
                  ),
                ),
              ),
            ),
            IgnorePointer(
              child: DecoratedBox(
                decoration: BoxDecoration(
                  gradient: LinearGradient(
                    begin: Alignment.topCenter,
                    end: Alignment.bottomCenter,
                    colors: <Color>[
                      highlightColor.withValues(alpha: 0.08 + unrollProgress * 0.04),
                      AppColors.transparent,
                      shadowColor.withValues(alpha: 0.05 + flapShadow * 0.35),
                    ],
                    stops: const <double>[0.0, 0.5, 1.0],
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ClippedLeafSurface extends StatelessWidget {
  const _ClippedLeafSurface({
    required this.surface,
    required this.visibleWidth,
    required this.pageSize,
    required this.alignment,
  });

  final Widget surface;
  final double visibleWidth;
  final Size pageSize;
  final Alignment alignment;

  @override
  Widget build(BuildContext context) {
    final widthFactor = (visibleWidth / math.max(pageSize.width, 1.0))
        .clamp(0.0, 1.0)
        .toDouble();
    return ClipRect(
      child: Align(
        alignment: alignment,
        widthFactor: widthFactor,
        child: SizedBox(
          width: pageSize.width,
          height: pageSize.height,
          child: surface,
        ),
      ),
    );
  }
}
