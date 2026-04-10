import 'package:flutter/material.dart';
import 'package:quwoquan_app/components/pageflip_book/src/pose/pageflip_book_single_backward_pose.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

class PageflipBookBackwardDebugOverlay extends StatelessWidget {
  const PageflipBookBackwardDebugOverlay({
    super.key,
    required this.stageSize,
    required this.pageRect,
    required this.pose,
  });

  static const ValueKey<String> overlayKey = ValueKey<String>(
    'pageflip_book_backward_debug_overlay',
  );
  static const ValueKey<String> metricsKey = ValueKey<String>(
    'pageflip_book_backward_debug_metrics',
  );

  final Size stageSize;
  final Rect pageRect;
  final PageflipBookSingleBackwardPose pose;

  @override
  Widget build(BuildContext context) {
    final coveredEdgeX =
        pageRect.left + pageRect.width * pose.coveredWidthNormalized;
    final curlPivotX =
        pageRect.left + pageRect.width * pose.curlPivotNormalized;
    final liftArrowOffset =
        pose.edgeLift * pageRect.height * 0.16 * pose.liftDirection;
    final fingerPoint = Offset(
      pageRect.left + pose.dragPoint.dx,
      pageRect.top + pose.dragPoint.dy,
    );
    return IgnorePointer(
      child: Stack(
        children: <Widget>[
          CustomPaint(
            key: overlayKey,
            size: stageSize,
            painter: _PageflipBookBackwardDebugPainter(
              pageRect: pageRect,
              fingerPoint: fingerPoint,
              coveredEdgeX: coveredEdgeX,
              curlPivotX: curlPivotX,
              liftArrowOffset: liftArrowOffset,
            ),
          ),
          Positioned(
            left: pageRect.left + AppSpacing.sm,
            top: pageRect.top + AppSpacing.sm,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: AppColors.welcomeBackgroundDark.withValues(alpha: 0.92),
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(
                  horizontal: AppSpacing.sm,
                  vertical: AppSpacing.six,
                ),
                child: Text(
                  key: metricsKey,
                  'cp=${pose.commitProgress.toStringAsFixed(2)} '
                  'cov=${pose.coveredWidthNormalized.toStringAsFixed(2)} '
                  'curl=${pose.curlWidthNormalized.toStringAsFixed(2)} '
                  'lift=${pose.edgeLift.toStringAsFixed(2)}',
                  style: const TextStyle(
                    color: AppColors.white,
                    fontSize: AppTypography.xs,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _PageflipBookBackwardDebugPainter extends CustomPainter {
  const _PageflipBookBackwardDebugPainter({
    required this.pageRect,
    required this.fingerPoint,
    required this.coveredEdgeX,
    required this.curlPivotX,
    required this.liftArrowOffset,
  });

  final Rect pageRect;
  final Offset fingerPoint;
  final double coveredEdgeX;
  final double curlPivotX;
  final double liftArrowOffset;

  @override
  void paint(Canvas canvas, Size size) {
    final pageBorderPaint = Paint()
      ..color = AppColors.welcomeBackground
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.one;
    final coveredEdgePaint = Paint()
      ..color = AppColors.success
      ..strokeWidth = AppSpacing.oneHalf;
    final curlPivotPaint = Paint()
      ..color = AppColors.warning
      ..strokeWidth = AppSpacing.oneHalf;
    final fingerPaint = Paint()
      ..color = AppColors.error
      ..style = PaintingStyle.fill;
    final liftPaint = Paint()
      ..color = AppColors.networkCallQualityWeak
      ..strokeWidth = AppSpacing.oneHalf;

    canvas.drawRect(pageRect, pageBorderPaint);
    canvas.drawLine(
      Offset(coveredEdgeX, pageRect.top),
      Offset(coveredEdgeX, pageRect.bottom),
      coveredEdgePaint,
    );
    canvas.drawLine(
      Offset(curlPivotX, pageRect.top),
      Offset(curlPivotX, pageRect.bottom),
      curlPivotPaint,
    );
    canvas.drawCircle(fingerPoint, 4, fingerPaint);

    final liftStart = Offset(curlPivotX, pageRect.center.dy);
    final liftEnd = Offset(curlPivotX, pageRect.center.dy + liftArrowOffset);
    canvas.drawLine(liftStart, liftEnd, liftPaint);
    canvas.drawCircle(liftEnd, 3, liftPaint);
  }

  @override
  bool shouldRepaint(_PageflipBookBackwardDebugPainter oldDelegate) {
    return pageRect != oldDelegate.pageRect ||
        fingerPoint != oldDelegate.fingerPoint ||
        coveredEdgeX != oldDelegate.coveredEdgeX ||
        curlPivotX != oldDelegate.curlPivotX ||
        liftArrowOffset != oldDelegate.liftArrowOffset;
  }
}
