import 'package:flutter/material.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

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
    breakpoint: AppBreakpoint.regular,
    responsiveState: const ResponsiveState(),
  );
}
