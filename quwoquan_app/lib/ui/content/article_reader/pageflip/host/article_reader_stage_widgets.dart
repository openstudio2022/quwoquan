import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/content/article_reader/templates/article_reader_template_theme.dart';
import 'package:quwoquan_app/ui/content/article_presentation_models.dart';

enum ArticlePageCurlCorner { topLeft, topRight, bottomLeft, bottomRight }

class ArticleReaderStagePainter extends CustomPainter {
  const ArticleReaderStagePainter({
    required this.palette,
    required this.pageRect,
    required this.pageCount,
    this.activeCorner,
    this.progress = 0,
  });

  final ArticleTemplatePalette palette;
  final Rect pageRect;
  final int pageCount;
  final ArticlePageCurlCorner? activeCorner;
  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final stageRect = Offset.zero & size;
    final softenedDeskBase = Color.lerp(
      palette.paperColor,
      AppColors.worksBackground,
      0.82,
    )!;
    final deskTop = Color.alphaBlend(
      palette.stageBackground.withValues(alpha: 0.64),
      softenedDeskBase,
    );
    final deskBottom = Color.alphaBlend(
      palette.stageBackground.withValues(alpha: 0.58),
      Color.lerp(softenedDeskBase, AppColors.worksDrawerBg, 0.28)!,
    );
    final stagePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.topCenter,
        end: Alignment.bottomCenter,
        colors: <Color>[
          deskTop,
          Color.alphaBlend(
            palette.stageBackground.withValues(alpha: 0.5),
            AppColors.iosSystemSurfaceDark,
          ),
          deskBottom,
        ],
        stops: const <double>[0.0, 0.52, 1.0],
      ).createShader(stageRect);
    canvas.drawRect(stageRect, stagePaint);

    final haloPaint = Paint()
      ..shader = RadialGradient(
        center: const Alignment(0, -0.18),
        radius: 0.92,
        colors: <Color>[
          AppColors.white.withValues(alpha: 0.05),
          palette.paperColor.withValues(alpha: 0.03),
          AppColors.transparent,
        ],
      ).createShader(stageRect);
    canvas.drawRect(stageRect, haloPaint);

    final stageSpec = resolveArticleReaderStageSpec();
    final spineRect = Rect.fromCenter(
      center: Offset(pageRect.center.dx, pageRect.center.dy),
      width: stageSpec.spineShadowWidth,
      height: pageRect.height + 32,
    );
    final spinePaint = Paint()
      ..shader = LinearGradient(
        begin: Alignment.centerLeft,
        end: Alignment.centerRight,
        colors: <Color>[
          AppColors.black.withValues(alpha: 0.03),
          AppColors.black.withValues(alpha: 0.18 + progress * 0.08),
          AppColors.iosProfileSurfaceLight.withValues(alpha: 0.06),
          AppColors.transparent,
        ],
        stops: const <double>[0.0, 0.36, 0.72, 1.0],
      ).createShader(spineRect);
    canvas.drawRect(spineRect, spinePaint);

    final stackPaint = Paint()
      ..color = AppColors.iosProfileSurfaceLight.withValues(alpha: 0.14)
      ..strokeWidth = 1;
    final stackCount = math.min(pageCount, stageSpec.pageStackCount);
    for (var index = 0; index < stackCount; index += 1) {
      final inset = (index + 1) * stageSpec.pageStackSpacing;
      final alpha = 0.16 - (index * 0.022);
      stackPaint.color = AppColors.iosProfileSurfaceLight.withValues(
        alpha: alpha.clamp(0.04, 0.16).toDouble(),
      );
      final leftX = pageRect.left - inset;
      final rightX = pageRect.right + inset;
      canvas.drawLine(
        Offset(leftX, pageRect.top + 12),
        Offset(leftX, pageRect.bottom - 12),
        stackPaint,
      );
      canvas.drawLine(
        Offset(rightX, pageRect.top + 12),
        Offset(rightX, pageRect.bottom - 12),
        stackPaint,
      );
    }

    if (activeCorner != null && progress > 0) {
      final isForward =
          activeCorner == ArticlePageCurlCorner.topRight ||
          activeCorner == ArticlePageCurlCorner.bottomRight;
      final foldShadowRect = Rect.fromLTWH(
        isForward ? pageRect.right - (pageRect.width * 0.32) : pageRect.left,
        pageRect.top,
        pageRect.width * 0.32,
        pageRect.height,
      );
      final foldShadowPaint = Paint()
        ..shader = LinearGradient(
          begin: isForward ? Alignment.centerRight : Alignment.centerLeft,
          end: isForward ? Alignment.centerLeft : Alignment.centerRight,
          colors: <Color>[
            AppColors.black.withValues(alpha: 0.14 * progress),
            AppColors.black.withValues(alpha: 0.04 * progress),
            AppColors.iosProfileSurfaceLight.withValues(alpha: 0.02 * progress),
            AppColors.transparent,
          ],
        ).createShader(foldShadowRect);
      canvas.drawRect(foldShadowRect, foldShadowPaint);
    }
  }

  @override
  bool shouldRepaint(covariant ArticleReaderStagePainter oldDelegate) {
    return oldDelegate.palette != palette ||
        oldDelegate.pageRect != pageRect ||
        oldDelegate.pageCount != pageCount ||
        oldDelegate.activeCorner != activeCorner ||
        oldDelegate.progress != progress;
  }
}

class ArticleBookStylePagerHintPainter extends CustomPainter {
  const ArticleBookStylePagerHintPainter(this.palette);

  final ArticleTemplatePalette palette;

  @override
  void paint(Canvas canvas, Size size) {
    const foldSize = 24.0;
    final foldPaint = Paint()
      ..shader =
          LinearGradient(
            begin: Alignment.topRight,
            end: Alignment.bottomLeft,
            colors: <Color>[
              AppColors.white.withValues(alpha: 0.42),
              palette.paperBorderColor.withValues(alpha: 0.28),
            ],
          ).createShader(
            Rect.fromLTWH(size.width - foldSize, 0, foldSize, foldSize),
          );
    final topFold = Path()
      ..moveTo(size.width, 0)
      ..lineTo(size.width - foldSize, 0)
      ..lineTo(size.width, foldSize)
      ..close();
    final bottomFold = Path()
      ..moveTo(size.width, size.height)
      ..lineTo(size.width - foldSize, size.height)
      ..lineTo(size.width, size.height - foldSize)
      ..close();
    canvas.drawPath(topFold, foldPaint);
    canvas.drawPath(bottomFold, foldPaint);
  }

  @override
  bool shouldRepaint(covariant ArticleBookStylePagerHintPainter oldDelegate) {
    return oldDelegate.palette != palette;
  }
}
