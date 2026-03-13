import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';

/// 全局无衬线黑体（思源黑体简体）
const String _kDefaultFontFamily = 'Noto Sans SC';

class AppTheme {
  static ThemeData get lightTheme => _buildTheme(Brightness.light);

  static ThemeData get darkTheme => _buildTheme(Brightness.dark);

  static ThemeData _buildTheme(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final palette = isDark ? AppColors.dark : AppColors.light;
    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primaryColor,
      brightness: brightness,
    ).copyWith(
      surface: palette.backgroundPrimary,
      onSurface: palette.foregroundPrimary,
    );
    final baseTextTheme = isDark
        ? ThemeData.dark().textTheme
        : ThemeData.light().textTheme;
    final textTheme = baseTextTheme.apply(
      bodyColor: palette.foregroundPrimary,
      displayColor: palette.foregroundPrimary,
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: palette.backgroundSecondary,
      dividerColor: AppColorsFunctional.getColor(isDark, ColorType.borderPrimary),
      fontFamily: _kDefaultFontFamily,
      textTheme: textTheme,
      appBarTheme: AppBarTheme(
        backgroundColor: palette.backgroundPrimary,
        foregroundColor: palette.foregroundPrimary,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        systemOverlayStyle: systemUiOverlayStyleFor(brightness),
      ),
      cupertinoOverrideTheme: NoDefaultCupertinoThemeData(
        brightness: brightness,
        primaryColor: AppColors.primaryColor,
        scaffoldBackgroundColor: palette.backgroundSecondary,
        barBackgroundColor: palette.backgroundPrimary,
        textTheme: CupertinoTextThemeData(
          primaryColor: AppColors.primaryColor,
          textStyle: textTheme.bodyMedium,
          actionTextStyle: textTheme.bodyLarge?.copyWith(
            color: AppColors.primaryColor,
          ),
          navActionTextStyle: textTheme.bodyLarge?.copyWith(
            color: AppColors.primaryColor,
          ),
          navTitleTextStyle: textTheme.titleLarge,
          navLargeTitleTextStyle: textTheme.headlineMedium,
          tabLabelTextStyle: textTheme.bodySmall,
          pickerTextStyle: textTheme.bodyLarge,
          dateTimePickerTextStyle: textTheme.bodyLarge,
        ),
      ),
    );
  }

  static SystemUiOverlayStyle systemUiOverlayStyleFor(Brightness brightness) {
    final iconBrightness = brightness == Brightness.dark
        ? Brightness.light
        : Brightness.dark;
    return SystemUiOverlayStyle(
      statusBarColor: Colors.transparent,
      statusBarIconBrightness: iconBrightness,
      statusBarBrightness: brightness,
      systemNavigationBarColor: Colors.transparent,
      systemNavigationBarIconBrightness: iconBrightness,
    );
  }
}

