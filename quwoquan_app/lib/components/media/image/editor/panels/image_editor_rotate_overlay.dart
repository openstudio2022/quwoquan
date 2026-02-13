import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

// ---------------------------------------------------------------------------
// 旋转刻度盘常量
// ---------------------------------------------------------------------------

/// 旋转刻度盘/覆盖层的全局常量
class RotateOverlayConstants {
  RotateOverlayConstants._();

  /// 微调旋转最大角度（±）
  static const double fineMaxDegrees = 45.0;

  /// 拖动灵敏度：每个像素对应多少度
  static const double fineDragSensitivity = 0.25;

  /// 刻度盘大刻度间隔（度）
  static const double dialTickMajorStep = 5.0;

  /// 刻度盘小刻度间隔（度）
  static const double dialTickMinorStep = 1.0;

  /// 刻度盘在任意时刻可见的角度范围（±）
  static const double dialVisibleDegrees = 18.0;

  /// 刻度盘高度因子（相对 bottomNavHeight）
  static const double dialHeightFactor = 1.8;

  /// 刻度盘到底部操作栏的间距
  static double get dialBottomPadding => AppSpacing.md;

  /// 刻度盘实际高度
  static double get dialHeight =>
      AppSpacing.bottomNavHeight * dialHeightFactor;

  /// 刻度盘 + 底部间距 = 图片区域需要预留的底部空间
  static double get bottomReserve => dialHeight + dialBottomPadding;

  /// 滑动提示动画持续时间
  static const Duration hintAnimDuration = Duration(milliseconds: 600);

  /// 滑动提示动画角度摆幅
  static const double hintAnimDegrees = 3.0;
}

// ---------------------------------------------------------------------------
// 几何工具
// ---------------------------------------------------------------------------

/// 旋转相关几何计算
class RotateGeometry {
  RotateGeometry._();

  /// 旋转 [radians] 角度后，图片要缩放多少才能刚好填满原始范围框。
  static double scaleToFill(double w, double h, double radians) {
    if (w <= 0 || h <= 0) return 1;
    final absCos = math.cos(radians).abs();
    final absSin = math.sin(radians).abs();
    final aspect = math.max(w / h, h / w);
    return absCos + aspect * absSin;
  }

  /// 计算旋转态下的范围框尺寸（支持超长竖图 / 超长横图）
  static ({double w, double h}) frameSize({
    required double availableW,
    required double availableH,
    required double ratio,
  }) {
    if (ratio <= 0) return (w: availableW, h: availableH);
    final containerRatio = availableW / availableH;
    double fw, fh;
    if (containerRatio > ratio) {
      fh = availableH;
      fw = fh * ratio;
    } else {
      fw = availableW;
      fh = fw / ratio;
    }
    fw = fw.clamp(0.0, availableW);
    fh = fh.clamp(0.0, availableH);
    return (w: fw, h: fh);
  }
}

// ---------------------------------------------------------------------------
// 旋转覆盖层 Widget（刻度盘 + 宫格范围框 + 提示动效）
// ---------------------------------------------------------------------------

/// 旋转工具覆盖层：碗形刻度盘 + 范围框/宫格
class ImageEditorRotateOverlay extends StatefulWidget {
  const ImageEditorRotateOverlay({
    super.key,
    required this.rotateFineDegrees,
    required this.isRotateEdited,
    required this.imageAspectRatio,
    required this.onFineDragUpdate,
  });

  final double rotateFineDegrees;
  final bool isRotateEdited;
  final double imageAspectRatio;
  final ValueChanged<double> onFineDragUpdate;

  @override
  State<ImageEditorRotateOverlay> createState() =>
      _ImageEditorRotateOverlayState();
}

class _ImageEditorRotateOverlayState extends State<ImageEditorRotateOverlay>
    with SingleTickerProviderStateMixin {
  late final AnimationController _hintController;
  late final Animation<double> _hintAnim;
  bool _hintDone = false;

  @override
  void initState() {
    super.initState();
    _hintController = AnimationController(
      vsync: this,
      duration: RotateOverlayConstants.hintAnimDuration,
    );
    // 左 → 右 → 0 摆动
    _hintAnim = TweenSequence<double>([
      TweenSequenceItem(
        tween: Tween(begin: 0.0, end: -RotateOverlayConstants.hintAnimDegrees)
            .chain(CurveTween(curve: Curves.easeOut)),
        weight: 30,
      ),
      TweenSequenceItem(
        tween: Tween(
                begin: -RotateOverlayConstants.hintAnimDegrees,
                end: RotateOverlayConstants.hintAnimDegrees)
            .chain(CurveTween(curve: Curves.easeInOut)),
        weight: 40,
      ),
      TweenSequenceItem(
        tween: Tween(begin: RotateOverlayConstants.hintAnimDegrees, end: 0.0)
            .chain(CurveTween(curve: Curves.easeIn)),
        weight: 30,
      ),
    ]).animate(_hintController);
    // 首次进入播放一次提示动画
    _hintController.forward();
    _hintController.addStatusListener((status) {
      if (status == AnimationStatus.completed) {
        setState(() => _hintDone = true);
      }
    });
  }

  @override
  void didUpdateWidget(covariant ImageEditorRotateOverlay oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 用户开始手动旋转后取消提示
    if (widget.isRotateEdited && !_hintDone) {
      _hintController.stop();
      setState(() => _hintDone = true);
    }
  }

  @override
  void dispose() {
    _hintController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final dialHeight = RotateOverlayConstants.dialHeight;
    final bottomReserve = RotateOverlayConstants.bottomReserve;

    return LayoutBuilder(
      builder: (context, constraints) {
        final topPad = MediaQuery.paddingOf(context).top;
        final availableWidth = constraints.maxWidth;
        final availableHeight =
            (constraints.maxHeight - topPad - bottomReserve)
                .clamp(1.0, constraints.maxHeight);
        final frame = RotateGeometry.frameSize(
          availableW: availableWidth,
          availableH: availableHeight,
          ratio: widget.imageAspectRatio,
        );
        // 上下等留白居中
        final verticalGap = availableHeight - frame.h;
        final topOffset = topPad + verticalGap / 2;
        final bottomOffset = bottomReserve + verticalGap / 2;
        // 宫格密度
        final minSide = math.min(frame.w, frame.h);
        final maxSide = math.max(frame.w, frame.h);
        const shortGridCount = 4;
        final longGridCount =
            (shortGridCount * maxSide / minSide).round().clamp(4, 12);
        final gridColumns =
            frame.w >= frame.h ? longGridCount : shortGridCount;
        final gridRows =
            frame.h >= frame.w ? longGridCount : shortGridCount;

        // 提示动画中的虚拟角度
        final hintAngle =
            (!_hintDone && _hintController.isAnimating) ? _hintAnim.value : 0.0;
        // 刻度盘显示的当前角度（正常旋转 + 提示动画）
        final displayAngle = widget.rotateFineDegrees + hintAngle;

        return AnimatedBuilder(
          animation: _hintController,
          builder: (context, _) {
            return Stack(
              children: [
                // 范围框 + 宫格（始终显示）
                Padding(
                  padding: EdgeInsets.only(
                    top: topOffset,
                    bottom: bottomOffset,
                  ),
                  child: Center(
                    child: SizedBox(
                      width: frame.w,
                      height: frame.h,
                      child: CustomPaint(
                        painter: RotateFramePainter(
                          columns: gridColumns,
                          rows: gridRows,
                        ),
                      ),
                    ),
                  ),
                ),
                // 刻度盘（始终显示刻度 + 数字）
                Positioned(
                  left: 0,
                  right: 0,
                  bottom: RotateOverlayConstants.dialBottomPadding,
                  height: dialHeight,
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onHorizontalDragUpdate: (details) {
                      final next = widget.rotateFineDegrees +
                          details.delta.dx *
                              RotateOverlayConstants.fineDragSensitivity;
                      widget.onFineDragUpdate(next);
                    },
                    child: CustomPaint(
                      size: Size.infinite,
                      painter: RotateDialPainter(
                        angleDegrees: displayAngle,
                        maxDegrees: RotateOverlayConstants.fineMaxDegrees,
                        majorStep: RotateOverlayConstants.dialTickMajorStep,
                        minorStep: RotateOverlayConstants.dialTickMinorStep,
                        visibleDegrees:
                            RotateOverlayConstants.dialVisibleDegrees,
                        showTicks: true, // 始终显示刻度
                      ),
                    ),
                  ),
                ),
              ],
            );
          },
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// 旋转预览 Widget（Transform + 暗淡溢出 + 内容区裁剪）
// ---------------------------------------------------------------------------

/// 旋转预览：
/// - 范围框内：正常显示
/// - 范围框外（旋转超出部分）：暗淡半透明显示
/// - 超出内容区（状态栏 / 面板区）：不显示
class ImageEditorRotatePreview extends StatelessWidget {
  const ImageEditorRotatePreview({
    super.key,
    required this.totalDegrees,
    required this.flipHorizontal,
    required this.flipVertical,
    required this.imageAspectRatio,
    required this.child,
  });

  final double totalDegrees;
  final bool flipHorizontal;
  final bool flipVertical;
  final double imageAspectRatio;
  final Widget child;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final topPad = MediaQuery.paddingOf(context).top;
        final bottomReserve = RotateOverlayConstants.bottomReserve;
        final availableWidth = constraints.maxWidth;
        final availableHeight =
            (constraints.maxHeight - topPad - bottomReserve)
                .clamp(1.0, constraints.maxHeight);
        final frame = RotateGeometry.frameSize(
          availableW: availableWidth,
          availableH: availableHeight,
          ratio: imageAspectRatio,
        );
        final radians = totalDegrees * math.pi / 180;
        final scale = RotateGeometry.scaleToFill(frame.w, frame.h, radians);
        // 上下等留白居中
        final verticalGap = availableHeight - frame.h;

        final baseImage = SizedBox(
          width: frame.w,
          height: frame.h,
          child: FittedBox(fit: BoxFit.cover, child: child),
        );
        final transformMatrix = Matrix4.identity()
          ..scaleByDouble(
            flipHorizontal ? -scale : scale,
            flipVertical ? -scale : scale,
            1.0,
            1.0,
          )
          ..rotateZ(radians);

        final isRotated = totalDegrees.abs() > 0.001;

        // 内容区裁剪（不侵入状态栏和面板区域）
        return ClipRect(
          child: Padding(
            padding: EdgeInsets.only(top: topPad, bottom: bottomReserve),
            child: Center(
              child: Padding(
                padding: EdgeInsets.only(
                  top: verticalGap / 2,
                  bottom: verticalGap / 2,
                ),
                child: Stack(
                  alignment: Alignment.center,
                  clipBehavior: Clip.none,
                  children: [
                    // 底层：完整旋转图片（暗淡，溢出可见但被内容区裁剪）
                    if (isRotated)
                      Opacity(
                        opacity: 0.3,
                        child: Transform(
                          alignment: Alignment.center,
                          transform: transformMatrix,
                          child: baseImage,
                        ),
                      ),
                    // 上层：范围框内裁剪（正常亮度）
                    ClipRect(
                      child: SizedBox(
                        width: frame.w,
                        height: frame.h,
                        child: Transform(
                          alignment: Alignment.center,
                          transform: transformMatrix,
                          child: baseImage,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
        );
      },
    );
  }
}

// ---------------------------------------------------------------------------
// 碗形刻度盘 Painter
// ---------------------------------------------------------------------------

/// 旋转仪表盘：朝下平缓碗形弧 + 滑动刻度 + 蓝色三角指针
class RotateDialPainter extends CustomPainter {
  const RotateDialPainter({
    required this.angleDegrees,
    required this.maxDegrees,
    required this.majorStep,
    required this.minorStep,
    required this.visibleDegrees,
    required this.showTicks,
  });

  final double angleDegrees;
  final double maxDegrees;
  final double majorStep;
  final double minorStep;
  final double visibleDegrees;
  final bool showTicks;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty) return;

    // ---- 几何 ----
    final halfArc = visibleDegrees * math.pi / 180;
    final majorLen = AppSpacing.md;
    final labelH = AppTypography.xs + AppSpacing.xs;
    final pointerH = AppSpacing.sm + AppSpacing.xs;
    final belowArc = majorLen + labelH + pointerH;
    final maxBowl = (size.height - belowArc).clamp(10.0, size.height);
    final rFromDepth =
        maxBowl / (1 - math.cos(halfArc)).clamp(0.001, 1.0);
    final chord = size.width * 0.6;
    final rFromChord =
        chord / (2 * math.sin(halfArc).clamp(0.001, 1.0));
    final radius = math.min(rFromDepth, rFromChord);
    final bowlDepth = radius * (1 - math.cos(halfArc));
    const arcTopY = 2.0;
    final arcBottomY = arcTopY + bowlDepth;
    final center = Offset(size.width / 2, arcBottomY - radius);

    // ---- 弧线（始终可见） ----
    final arcPaint = Paint()
      ..color = AppColors.white.withValues(alpha: 0.3)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1.0;
    final arcRect = Rect.fromCircle(center: center, radius: radius);
    canvas.drawArc(
      arcRect,
      math.pi / 2 - halfArc,
      halfArc * 2,
      false,
      arcPaint,
    );

    // ---- 刻度（始终显示） ----
    if (showTicks) {
      final minorPaint = Paint()
        ..color = AppColors.white.withValues(alpha: 0.5)
        ..strokeWidth = 1.0;
      final majorPaint = Paint()
        ..color = AppColors.white.withValues(alpha: 0.9)
        ..strokeWidth = 1.5;
      final minorLen = AppSpacing.sm;
      final tickExtent = maxDegrees + 10;

      for (double d = -tickExtent; d <= tickExtent; d += minorStep) {
        final relative = d - angleDegrees;
        if (relative.abs() > visibleDegrees + 0.5) continue;
        final isMajor = (d % majorStep).abs() < 0.01;
        final len = isMajor ? majorLen : minorLen;
        final theta = math.pi / 2 + relative * math.pi / 180;
        final cosT = math.cos(theta);
        final sinT = math.sin(theta);
        final p1 = Offset(
          center.dx + cosT * radius,
          center.dy + sinT * radius,
        );
        final p2 = Offset(
          center.dx + cosT * (radius + len),
          center.dy + sinT * (radius + len),
        );
        canvas.drawLine(p1, p2, isMajor ? majorPaint : minorPaint);

        // 数字标签：仅 |d| ≤ 45° 的整 5° 处
        if (isMajor && d.abs() <= maxDegrees + 0.01) {
          final label = d.round().toString();
          final tp = TextPainter(
            text: TextSpan(
              text: label,
              style: TextStyle(
                color: AppColors.white.withValues(alpha: 0.9),
                fontSize: AppTypography.xs,
              ),
            ),
            textDirection: TextDirection.ltr,
          )..layout();
          final labelR = radius + len + AppSpacing.xs;
          final lp = Offset(
            center.dx + cosT * labelR - tp.width / 2,
            center.dy + sinT * labelR - tp.height / 2,
          );
          tp.paint(canvas, lp);
        }
      }
    }

    // ---- 蓝色三角指针（固定在弧底部正中） ----
    final triSize = AppSpacing.sm;
    final tipY = arcBottomY;
    final baseY = arcBottomY + triSize + AppSpacing.xs;
    final pointerPath = Path()
      ..moveTo(size.width / 2, tipY)
      ..lineTo(size.width / 2 - triSize * 0.6, baseY)
      ..lineTo(size.width / 2 + triSize * 0.6, baseY)
      ..close();
    canvas.drawPath(
      pointerPath,
      Paint()
        ..color = AppColors.primaryColor
        ..style = PaintingStyle.fill,
    );
  }

  @override
  bool shouldRepaint(covariant RotateDialPainter old) {
    return old.angleDegrees != angleDegrees ||
        old.maxDegrees != maxDegrees ||
        old.majorStep != majorStep ||
        old.minorStep != minorStep ||
        old.visibleDegrees != visibleDegrees ||
        old.showTicks != showTicks;
  }
}

// ---------------------------------------------------------------------------
// 范围框 + 宫格 Painter
// ---------------------------------------------------------------------------

/// 旋转范围框与宫格辅助线
class RotateFramePainter extends CustomPainter {
  const RotateFramePainter({
    required this.columns,
    required this.rows,
  });

  final int columns;
  final int rows;

  @override
  void paint(Canvas canvas, Size size) {
    if (size.isEmpty || columns <= 0 || rows <= 0) return;
    final borderPaint = Paint()
      ..color = AppColors.white.withValues(alpha: 0.35)
      ..style = PaintingStyle.stroke
      ..strokeWidth = AppSpacing.xs / 2;
    final gridPaint = Paint()
      ..color = AppColors.white.withValues(alpha: 0.35)
      ..strokeWidth = AppSpacing.xs / 4;
    canvas.drawRect(Offset.zero & size, borderPaint);
    final colW = size.width / columns;
    final rowH = size.height / rows;
    for (int c = 1; c < columns; c++) {
      final x = colW * c;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
    }
    for (int r = 1; r < rows; r++) {
      final y = rowH * r;
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }
  }

  @override
  bool shouldRepaint(covariant RotateFramePainter old) {
    return old.columns != columns || old.rows != rows;
  }
}
