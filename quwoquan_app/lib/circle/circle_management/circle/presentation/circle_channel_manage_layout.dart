import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';

/// 圈子频道管理页的响应式布局语义。
class CircleChannelManageLayout {
  CircleChannelManageLayout._();

  /// 顶部半屏面板的最大高度比例。
  static double panelMaxHeightRatio(BuildContext context) =>
      AppSpacing.responsiveValue(
        context,
        compact: 0.52,
        regular: 0.5,
        expanded: 0.46,
      );

  /// 频道 chip 宫格列数。
  static int gridColumns(BuildContext context) => AppSpacing.responsiveValue(
    context,
    compact: 3,
    regular: 4,
    expanded: 5,
  ).round();

  /// chip 宫格间距，平板上稍微放松。
  static double chipGridSpacing(BuildContext context) =>
      AppSpacing.responsiveValue(
        context,
        compact: AppSpacing.intraGroupSm,
        regular: AppSpacing.intraGroupSm,
        expanded: AppSpacing.containerSm,
      );
}
