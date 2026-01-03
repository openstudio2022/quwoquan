import 'package:flutter/material.dart';
import 'app_spacing.dart';

/// 间距尺寸枚举
enum SpacingSize {
  xs,
  sm,
  md,
  lg,
  xl,
}

/// BuildContext扩展方法 - 用于获取间距
extension SpacingExtension on BuildContext {
  /// 安全获取组内间距（带默认值）
  double safeGetIntraGroupSpacing(SpacingSize size) {
    switch (size) {
      case SpacingSize.xs:
        return AppSpacing.xs;
      case SpacingSize.sm:
        return AppSpacing.sm;
      case SpacingSize.md:
        return AppSpacing.md;
      case SpacingSize.lg:
        return AppSpacing.lg;
      case SpacingSize.xl:
        return AppSpacing.xl;
    }
  }

  /// 安全获取组间间距（带默认值）
  double safeGetInterGroupSpacing(SpacingSize size) {
    switch (size) {
      case SpacingSize.xs:
        return AppSpacing.xs * 2;
      case SpacingSize.sm:
        return AppSpacing.sm * 2;
      case SpacingSize.md:
        return AppSpacing.md * 2;
      case SpacingSize.lg:
        return AppSpacing.lg * 2;
      case SpacingSize.xl:
        return AppSpacing.xl * 2;
    }
  }

  /// 安全获取容器间距（带默认值）
  double safeGetContainerSpacing(SpacingSize size) {
    switch (size) {
      case SpacingSize.xs:
        return AppSpacing.xs * 2;
      case SpacingSize.sm:
        return AppSpacing.sm * 2;
      case SpacingSize.md:
        return AppSpacing.md;
      case SpacingSize.lg:
        return AppSpacing.lg;
      case SpacingSize.xl:
        return AppSpacing.xl;
    }
  }
}

