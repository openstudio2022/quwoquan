import 'package:flutter/material.dart';
import 'package:quwoquan_app/runtime/shell/state/accessibility_provider.dart';
import 'package:quwoquan_app/runtime/di/app_providers.dart';

/// 冷启动欢迎路径使用的轻量外观快照，避免首帧 watch 聚合 Provider 链。
AppearanceSnapshot startupWelcomeAppearanceSnapshot() {
  final brightness =
      WidgetsBinding.instance.platformDispatcher.platformBrightness;
  final isDark = brightness == Brightness.dark;
  return AppearanceSnapshot(
    themeMode: ThemeMode.system,
    effectiveBrightness: brightness,
    isDark: isDark,
    fontSizePreset: AppFontSizePreset.md,
    textScaleFactor: 1,
    boldText: false,
    highContrast: false,
    disableAnimations: WidgetsBinding
        .instance
        .platformDispatcher
        .accessibilityFeatures
        .disableAnimations,
    breakpoint: AppBreakpoint.regular,
    responsiveState: const ResponsiveState(),
  );
}
