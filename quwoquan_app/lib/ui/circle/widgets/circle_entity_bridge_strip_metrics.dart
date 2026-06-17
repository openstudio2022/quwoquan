import 'package:flutter/widgets.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 圈子-实体桥接条的自适应高度计算。
///
/// 卡片内容随系统字号增大而变高（标题 1 行 + 提示 2 行）；固定高度在大字号下会
/// 1px 级溢出。这里按 [MediaQuery.textScalerOf] 计算自然内容高度，取与断点基准的
/// 较大者，保证大字号自适应不裁切，同时不撑破窄屏安全区。
double resolveCirclesEntityBridgeStripHeight(BuildContext context) {
  final base = AppSpacing.responsiveValue(
    context,
    compact: AppSpacing.bottomNavHeight * 2.25,
    regular: AppSpacing.bottomNavHeight * 2.35,
    expanded: AppSpacing.bottomNavHeight * 2.45,
  );
  final scaler = MediaQuery.textScalerOf(context);
  final direction = Directionality.of(context);
  final titlePainter = TextPainter(
    text: const TextSpan(
      text: 'Hg',
      style: TextStyle(fontSize: AppTypography.smPlus),
    ),
    textDirection: direction,
    textScaler: scaler,
    maxLines: 1,
  )..layout();
  final hintPainter = TextPainter(
    text: const TextSpan(
      text: 'Hg\nHg',
      style: TextStyle(
        fontSize: AppTypography.xsPlus,
        height: AppTypography.lineHeightTight,
      ),
    ),
    textDirection: direction,
    textScaler: scaler,
    maxLines: 2,
  )..layout();
  final avatarRow = AppSpacing.avatarCircleSm + AppSpacing.intraGroupXs;
  // 末项 intraGroupXs 吸收文本亚像素取整冗余，避免 spaceBetween 紧约束下的 1px 溢出。
  final content =
      AppSpacing.containerSm * 2 +
      avatarRow +
      AppSpacing.intraGroupSm +
      titlePainter.height +
      AppSpacing.oneHalf +
      hintPainter.height +
      AppSpacing.intraGroupXs;
  return content > base ? content : base;
}
