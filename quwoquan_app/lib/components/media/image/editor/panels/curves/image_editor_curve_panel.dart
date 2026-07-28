import 'dart:math' as math;

import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/components/media/image/editor/panels/curves/image_editor_curve_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 曲线编辑面板：通道选择 + 直方图背景 + 控制点拖拽画布。
///
/// 交互对齐 Snapseed/醒图曲线：
/// - 点击空白处添加控制点（每通道最多 8 个）；
/// - 拖动控制点调整；端点只能纵向移动；
/// - 把中间控制点拖出画布上下边界外删除；
/// - 通道 chips 切换 RGB/R/G/B，重置按钮恢复当前通道。
class ImageEditorCurvePanel extends StatefulWidget {
  const ImageEditorCurvePanel({
    super.key,
    required this.curves,
    required this.channel,
    required this.histogram,
    required this.onChannelChanged,
    required this.onCurvesChanged,
    required this.onResetChannel,
  });

  final ImageEditorCurvesState curves;
  final ImageEditorCurveChannel channel;

  /// 亮度直方图（256 桶，可为空表示未加载）。
  final List<int>? histogram;
  final ValueChanged<ImageEditorCurveChannel> onChannelChanged;
  final ValueChanged<ImageEditorCurvesState> onCurvesChanged;
  final VoidCallback onResetChannel;

  @override
  State<ImageEditorCurvePanel> createState() => _ImageEditorCurvePanelState();
}

class _ImageEditorCurvePanelState extends State<ImageEditorCurvePanel> {
  int? _draggingIndex;

  Color _channelColor(ImageEditorCurveChannel channel) {
    switch (channel) {
      case ImageEditorCurveChannel.rgb:
        return AppColors.white;
      case ImageEditorCurveChannel.red:
        return AppColors.error;
      case ImageEditorCurveChannel.green:
        return AppColors.success;
      case ImageEditorCurveChannel.blue:
        return AppColors.info;
    }
  }

  String _channelLabel(ImageEditorCurveChannel channel) {
    switch (channel) {
      case ImageEditorCurveChannel.rgb:
        return MediaText.imageEditorProCurveChannelRgb;
      case ImageEditorCurveChannel.red:
        return MediaText.imageEditorProChannelRed;
      case ImageEditorCurveChannel.green:
        return MediaText.imageEditorProChannelGreen;
      case ImageEditorCurveChannel.blue:
        return MediaText.imageEditorProChannelBlue;
    }
  }

  List<ImageEditorCurvePoint> get _points =>
      widget.curves.pointsForChannel(widget.channel);

  void _updatePoints(List<ImageEditorCurvePoint> points) {
    widget.onCurvesChanged(
      widget.curves.withChannelPoints(widget.channel, points),
    );
  }

  Offset _toLocal(ImageEditorCurvePoint point, Size size) {
    return Offset(point.x * size.width, (1 - point.y) * size.height);
  }

  ImageEditorCurvePoint _fromLocal(Offset local, Size size) {
    return ImageEditorCurvePoint(
      (local.dx / size.width).clamp(0.0, 1.0),
      (1 - local.dy / size.height).clamp(0.0, 1.0),
    );
  }

  int? _hitTestPoint(Offset local, Size size) {
    final radius = AppSpacing.iconMedium;
    for (var i = 0; i < _points.length; i++) {
      if ((_toLocal(_points[i], size) - local).distance <= radius) {
        return i;
      }
    }
    return null;
  }

  void _handlePanStart(Offset local, Size size) {
    final hit = _hitTestPoint(local, size);
    if (hit != null) {
      setState(() => _draggingIndex = hit);
      return;
    }
    final points = List<ImageEditorCurvePoint>.of(_points);
    if (points.length >= ImageEditorCurvesState.maxPointsPerChannel) {
      return;
    }
    final candidate = _fromLocal(local, size);
    // 不允许过近的 x 重叠。
    for (final point in points) {
      if ((point.x - candidate.x).abs() < 0.03) {
        return;
      }
    }
    points.add(candidate);
    points.sort((a, b) => a.x.compareTo(b.x));
    _updatePoints(points);
    setState(
      () => _draggingIndex = points.indexWhere(
        (p) => (p.x - candidate.x).abs() < 1e-6,
      ),
    );
  }

  void _handlePanUpdate(Offset local, Size size) {
    final index = _draggingIndex;
    if (index == null || index < 0 || index >= _points.length) {
      return;
    }
    final points = List<ImageEditorCurvePoint>.of(_points);
    final isEndpoint = index == 0 || index == points.length - 1;
    // 中间点拖出上下边界较远时删除（Snapseed 语义）。
    if (!isEndpoint &&
        (local.dy < -AppSpacing.iconLarge ||
            local.dy > size.height + AppSpacing.iconLarge)) {
      points.removeAt(index);
      _updatePoints(points);
      setState(() => _draggingIndex = null);
      return;
    }
    final next = _fromLocal(local, size);
    final minX = index == 0 ? 0.0 : points[index - 1].x + 0.02;
    final maxX = index == points.length - 1 ? 1.0 : points[index + 1].x - 0.02;
    points[index] = ImageEditorCurvePoint(
      isEndpoint ? points[index].x : next.x.clamp(minX, maxX),
      next.y,
    );
    _updatePoints(points);
  }

  @override
  Widget build(BuildContext context) {
    final channelColor = _channelColor(widget.channel);
    return Column(
      mainAxisSize: MainAxisSize.min,
      children: [
        Padding(
          padding: EdgeInsets.symmetric(
            horizontal: AppSpacing.containerSm,
            vertical: AppSpacing.xs,
          ),
          child: Row(
            children: [
              for (final channel in ImageEditorCurveChannel.values) ...[
                _buildChannelChip(channel),
                SizedBox(width: AppSpacing.intraGroupSm),
              ],
              const Spacer(),
              CupertinoButton(
                padding: EdgeInsets.symmetric(horizontal: AppSpacing.sm),
                minimumSize: Size.square(AppSpacing.minInteractiveSize),
                onPressed: widget.onResetChannel,
                child: Icon(
                  CupertinoIcons.refresh,
                  color: AppColors.white.withValues(alpha: 0.85),
                  size: AppSpacing.iconMedium,
                ),
              ),
            ],
          ),
        ),
        Padding(
          padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerSm),
          child: AspectRatio(
            aspectRatio: 2.05,
            child: LayoutBuilder(
              builder: (context, constraints) {
                final size = Size(constraints.maxWidth, constraints.maxHeight);
                return GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onPanStart: (details) =>
                      _handlePanStart(details.localPosition, size),
                  onPanUpdate: (details) =>
                      _handlePanUpdate(details.localPosition, size),
                  onPanEnd: (_) => setState(() => _draggingIndex = null),
                  onPanCancel: () => setState(() => _draggingIndex = null),
                  child: CustomPaint(
                    size: size,
                    painter: _CurveCanvasPainter(
                      points: _points,
                      lut: widget.curves.lutForChannel(widget.channel),
                      histogram: widget.histogram,
                      curveColor: channelColor,
                      draggingIndex: _draggingIndex,
                    ),
                  ),
                );
              },
            ),
          ),
        ),
        SizedBox(height: AppSpacing.xs),
      ],
    );
  }

  Widget _buildChannelChip(ImageEditorCurveChannel channel) {
    final selected = widget.channel == channel;
    final color = _channelColor(channel);
    final edited = !widget.curves.channelIsIdentity(channel);
    return CupertinoButton(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.sm,
        vertical: AppSpacing.xs,
      ),
      minimumSize: Size.zero,
      onPressed: () => widget.onChannelChanged(channel),
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.sm,
          vertical: AppSpacing.xs / 2,
        ),
        decoration: BoxDecoration(
          color: selected
              ? color.withValues(alpha: 0.22)
              : AppColors.white.withValues(alpha: 0.06),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(
            color: selected
                ? color
                : AppColors.white.withValues(alpha: edited ? 0.5 : 0.18),
          ),
        ),
        child: Text(
          _channelLabel(channel),
          style: TextStyle(
            color: selected ? color : AppColors.white.withValues(alpha: 0.75),
            fontSize: AppTypography.sm,
            fontWeight: selected ? FontWeight.w600 : FontWeight.normal,
          ),
        ),
      ),
    );
  }
}

class _CurveCanvasPainter extends CustomPainter {
  const _CurveCanvasPainter({
    required this.points,
    required this.lut,
    required this.histogram,
    required this.curveColor,
    required this.draggingIndex,
  });

  final List<ImageEditorCurvePoint> points;
  final List<int> lut;
  final List<int>? histogram;
  final Color curveColor;
  final int? draggingIndex;

  @override
  void paint(Canvas canvas, Size size) {
    final borderPaint = Paint()
      ..style = PaintingStyle.stroke
      ..strokeWidth = 1
      ..color = AppColors.white.withValues(alpha: 0.25);
    canvas.drawRect(Offset.zero & size, borderPaint);
    // 三分网格。
    final gridPaint = Paint()
      ..strokeWidth = 0.5
      ..color = AppColors.white.withValues(alpha: 0.14);
    for (var i = 1; i < 4; i++) {
      final x = size.width * i / 4;
      final y = size.height * i / 4;
      canvas.drawLine(Offset(x, 0), Offset(x, size.height), gridPaint);
      canvas.drawLine(Offset(0, y), Offset(size.width, y), gridPaint);
    }
    // 对角参考线。
    canvas.drawLine(
      Offset(0, size.height),
      Offset(size.width, 0),
      Paint()
        ..strokeWidth = 0.8
        ..color = AppColors.white.withValues(alpha: 0.20),
    );
    // 直方图背景。
    final hist = histogram;
    if (hist != null && hist.length == 256) {
      final maxCount = hist.fold<int>(0, math.max);
      if (maxCount > 0) {
        final histPath = Path()..moveTo(0, size.height);
        for (var i = 0; i < 256; i++) {
          final x = i / 255 * size.width;
          final h = (hist[i] / maxCount) * size.height * 0.9;
          histPath.lineTo(x, size.height - h);
        }
        histPath
          ..lineTo(size.width, size.height)
          ..close();
        canvas.drawPath(
          histPath,
          Paint()..color = AppColors.white.withValues(alpha: 0.12),
        );
      }
    }
    // 曲线本体（直接采样 LUT，与像素引擎同一真相源）。
    final curvePath = Path();
    for (var i = 0; i < 256; i++) {
      final x = i / 255 * size.width;
      final y = (1 - lut[i] / 255) * size.height;
      if (i == 0) {
        curvePath.moveTo(x, y);
      } else {
        curvePath.lineTo(x, y);
      }
    }
    canvas.drawPath(
      curvePath,
      Paint()
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round
        ..color = curveColor,
    );
    // 控制点。
    for (var i = 0; i < points.length; i++) {
      final center = Offset(
        points[i].x * size.width,
        (1 - points[i].y) * size.height,
      );
      final isDragging = draggingIndex == i;
      canvas.drawCircle(
        center,
        isDragging ? AppSpacing.xs * 1.6 : AppSpacing.xs * 1.2,
        Paint()..color = curveColor,
      );
      canvas.drawCircle(
        center,
        isDragging ? AppSpacing.xs * 1.6 : AppSpacing.xs * 1.2,
        Paint()
          ..style = PaintingStyle.stroke
          ..strokeWidth = 1.5
          ..color = AppColors.black.withValues(alpha: 0.6),
      );
    }
  }

  @override
  bool shouldRepaint(covariant _CurveCanvasPainter oldDelegate) {
    return oldDelegate.points != points ||
        oldDelegate.histogram != histogram ||
        oldDelegate.curveColor != curveColor ||
        oldDelegate.draggingIndex != draggingIndex ||
        !identical(oldDelegate.lut, lut);
  }
}
