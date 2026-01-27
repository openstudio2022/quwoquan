import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/design_system/theme/theme_provider.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

final appThemeProvider = Provider<ThemeData>((ref) {
  final isDark = ref.watch(isDarkProvider);
  return isDark ? _darkTheme : _lightTheme;
});

final _lightTheme = ThemeData(
  brightness: Brightness.light,
  primaryColor: AppColors.primaryColor,
  scaffoldBackgroundColor: AppColors.light.backgroundPrimary,
);

final _darkTheme = ThemeData(
  brightness: Brightness.dark,
  primaryColor: AppColors.primaryColor,
  scaffoldBackgroundColor: AppColors.dark.backgroundPrimary,
);

/// 应用主题类
class AppTheme {
  static ThemeData get lightTheme => _lightTheme;
  static ThemeData get darkTheme => _darkTheme;
}