import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 更多功能弹窗样式配置
class MoreActionStyle {
  final Color? backgroundColorLight;
  final Color? backgroundColorDark;
  final Color? titleColorLight;
  final Color? titleColorDark;
  final Color? itemBackgroundColorLight;
  final Color? itemBackgroundColorDark;
  final Color? iconColorLight;
  final Color? iconColorDark;
  final Color? textColorLight;
  final Color? textColorDark;
  final Color? bottomBackgroundColorLight;
  final Color? bottomBackgroundColorDark;
  final Color? bottomTextColorLight;
  final Color? bottomTextColorDark;
  final Color? bottomSubtitleColorLight;
  final Color? bottomSubtitleColorDark;
  final double? borderRadius;
  final double? itemBorderRadius;
  final double? bottomBorderRadius;

  const MoreActionStyle({
    this.backgroundColorLight,
    this.backgroundColorDark,
    this.titleColorLight,
    this.titleColorDark,
    this.itemBackgroundColorLight,
    this.itemBackgroundColorDark,
    this.iconColorLight,
    this.iconColorDark,
    this.textColorLight,
    this.textColorDark,
    this.bottomBackgroundColorLight,
    this.bottomBackgroundColorDark,
    this.bottomTextColorLight,
    this.bottomTextColorDark,
    this.bottomSubtitleColorLight,
    this.bottomSubtitleColorDark,
    this.borderRadius,
    this.itemBorderRadius,
    this.bottomBorderRadius,
  });

  /// 默认样式
  static const MoreActionStyle defaultStyle = MoreActionStyle();

  /// 媒体post样式
  static const MoreActionStyle mediaPostStyle = MoreActionStyle(
    borderRadius: 20.0,
    itemBorderRadius: 8.0,
    bottomBorderRadius: 12.0,
  );

  /// 图片浏览样式
  static const MoreActionStyle imageViewerStyle = MoreActionStyle(
    borderRadius: 16.0,
    itemBorderRadius: 6.0,
    bottomBorderRadius: 10.0,
  );

  /// 作者主页样式
  static const MoreActionStyle profileStyle = MoreActionStyle(
    borderRadius: 24.0,
    itemBorderRadius: 10.0,
    bottomBorderRadius: 14.0,
  );

  /// 深色主题样式
  static MoreActionStyle get darkStyle => MoreActionStyle(
    backgroundColorDark: AppColors.dark.backgroundPrimary,
    titleColorDark: AppColors.dark.foregroundSecondary,
    itemBackgroundColorDark: AppColors.dark.backgroundSecondary,
    iconColorDark: AppColors.dark.foregroundPrimary,
    textColorDark: AppColors.dark.foregroundPrimary,
    bottomBackgroundColorDark: AppColors.dark.backgroundSecondary,
    bottomTextColorDark: AppColors.dark.foregroundInverse,
    bottomSubtitleColorDark: AppColors.dark.foregroundSecondary,
  );

  /// 浅色主题样式
  static MoreActionStyle get lightStyle => MoreActionStyle(
    backgroundColorLight: AppColors.light.backgroundSecondary,
    titleColorLight: AppColors.light.foregroundPrimary,
    itemBackgroundColorLight: AppColors.light.backgroundPrimary,
    iconColorLight: AppColors.light.foregroundPrimary,
    textColorLight: AppColors.light.foregroundPrimary,
    bottomBackgroundColorLight: AppColors.light.backgroundPrimary,
    bottomTextColorLight: AppColors.light.foregroundPrimary,
    bottomSubtitleColorLight: AppColors.light.foregroundSecondary,
  );
}
