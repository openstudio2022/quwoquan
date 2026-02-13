import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class EditorSessionOpsStrip extends StatelessWidget {
  const EditorSessionOpsStrip({
    super.key,
    required this.supportsCompare,
    required this.isComparing,
    required this.onCompareStart,
    required this.onCompareEnd,
  });

  final bool supportsCompare;
  final bool isComparing;
  final VoidCallback? onCompareStart;
  final VoidCallback? onCompareEnd;

  /// 与底部 X/勾 功能面板底栏一致的语义高度，保证对比图标与勾勾垂直对齐（所有页面此系统图标一致）
  static double get sessionOpsStripHeight =>
      AppSpacing.intraGroupSm * 2 + AppSpacing.iconButtonMinSizeMd;

  /// 对比图标与底部勾使用相同触控宽度，保证竖屏时在同一竖线上
  static double get compareIconTouchWidth => AppSpacing.iconButtonMinSizeMd;

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: sessionOpsStripHeight,
      child: Padding(
        padding: EdgeInsets.only(
          left: AppSpacing.containerMd,
          right: AppSpacing.containerMd,
          top: AppSpacing.intraGroupSm,
          bottom: AppSpacing.intraGroupSm,
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            const Spacer(),
            if (supportsCompare)
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onLongPressStart: (_) => onCompareStart?.call(),
                onLongPressEnd: (_) => onCompareEnd?.call(),
                onTapDown: (_) => onCompareStart?.call(),
                onTapUp: (_) => onCompareEnd?.call(),
                onTapCancel: onCompareEnd,
                child: SizedBox(
                  width: compareIconTouchWidth,
                  height: sessionOpsStripHeight,
                  child: Center(
                    child: _CompareSplitGlyph(
                      size: AppSpacing.iconMedium,
                      alpha: isComparing ? 1.0 : 0.9,
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

class _CompareSplitGlyph extends StatelessWidget {
  const _CompareSplitGlyph({
    this.size = 24,
    this.alpha = 1.0,
  });

  final double size;
  final double alpha;

  @override
  Widget build(BuildContext context) {
    final side = size;
    return SizedBox(
      width: side,
      height: side,
      child: Row(
        children: [
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(
                  color: AppColors.white.withValues(alpha: 0.9 * alpha),
                  width: AppSpacing.xs / 4,
                ),
                borderRadius: BorderRadius.circular(AppSpacing.xs / 4),
              ),
            ),
          ),
          Container(
            width: AppSpacing.xs / 4,
            color: AppColors.white.withValues(alpha: 0.75 * alpha),
          ),
          Expanded(
            child: Container(
              decoration: BoxDecoration(
                border: Border.all(
                  color: AppColors.white.withValues(alpha: 0.5 * alpha),
                  width: AppSpacing.xs / 4,
                ),
                borderRadius: BorderRadius.circular(AppSpacing.xs / 4),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
