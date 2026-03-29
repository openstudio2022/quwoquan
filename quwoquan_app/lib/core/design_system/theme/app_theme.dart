import 'package:flutter/cupertino.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/core/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/core/design_system/typography/app_typography.dart';

/// 非 iOS 平台的默认无衬线黑体（思源黑体简体）。
const String _kDefaultFontFamily = 'Noto Sans SC';

String? _platformFontFamily() {
  switch (defaultTargetPlatform) {
    case TargetPlatform.iOS:
    case TargetPlatform.macOS:
      return null;
    default:
      return _kDefaultFontFamily;
  }
}

List<String> _platformFontFallbacks() {
  return const <String>[
    '.SF Pro Text',
    'PingFang SC',
    'Helvetica Neue',
    'Noto Sans SC',
  ];
}

class AppTheme {
  static ThemeData get lightTheme => _buildTheme(Brightness.light);

  static ThemeData get darkTheme => _buildTheme(Brightness.dark);

  static ThemeData _buildTheme(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final palette = isDark ? AppColors.dark : AppColors.light;
    final primaryAccent = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionForeground,
    );
    final scaffoldBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.pageBackground,
    );
    final surfaceBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceElevated,
    );
    final elevatedSurface = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundSecondary,
    );
    final mutedSurface = AppColorsFunctional.getColor(
      isDark,
      ColorType.surfaceMuted,
    );
    final separatorColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorOpaque,
    );
    final selectionColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionBackground,
    );
    final colorScheme =
        ColorScheme.fromSeed(
          seedColor: primaryAccent,
          brightness: brightness,
        ).copyWith(
          primary: primaryAccent,
          secondary: primaryAccent,
          error: AppColors.error,
          surfaceContainerHighest: mutedSurface,
          surface: surfaceBackground,
          onSurface: palette.foregroundPrimary,
        );
    final baseTextTheme = isDark
        ? ThemeData.dark().textTheme
        : ThemeData.light().textTheme;
    final themedBase = baseTextTheme.apply(
      bodyColor: palette.foregroundPrimary,
      displayColor: palette.foregroundPrimary,
    );
    final textTheme = themedBase.copyWith(
      bodyLarge: themedBase.bodyLarge?.copyWith(
        fontSize: AppTypography.iosBody,
        height: AppTypography.bodyLineHeight,
      ),
      bodyMedium: themedBase.bodyMedium?.copyWith(
        fontSize: AppTypography.iosSubheadline,
        height: AppTypography.bodyLineHeight,
      ),
      bodySmall: themedBase.bodySmall?.copyWith(
        fontSize: AppTypography.iosFootnote,
        height: AppTypography.lineHeightCompact,
      ),
      titleMedium: themedBase.titleMedium?.copyWith(
        fontSize: AppTypography.iosNavTitle,
        fontWeight: AppTypography.semiBold,
      ),
      titleLarge: themedBase.titleLarge?.copyWith(
        fontSize: AppTypography.iosTitle3,
        fontWeight: AppTypography.semiBold,
      ),
      headlineSmall: themedBase.headlineSmall?.copyWith(
        fontSize: AppTypography.iosTitle2,
        fontWeight: AppTypography.bold,
      ),
      headlineMedium: themedBase.headlineMedium?.copyWith(
        fontSize: AppTypography.iosLargeTitle,
        fontWeight: AppTypography.bold,
      ),
    );

    return ThemeData(
      useMaterial3: true,
      brightness: brightness,
      colorScheme: colorScheme,
      scaffoldBackgroundColor: scaffoldBackground,
      dividerColor: separatorColor,
      fontFamily: _platformFontFamily(),
      fontFamilyFallback: _platformFontFallbacks(),
      textTheme: textTheme,
      canvasColor: surfaceBackground,
      splashFactory: NoSplash.splashFactory,
      splashColor: Colors.transparent,
      highlightColor: Colors.transparent,
      hoverColor: selectionColor,
      textSelectionTheme: TextSelectionThemeData(
        cursorColor: primaryAccent,
        selectionColor: selectionColor,
        selectionHandleColor: primaryAccent,
      ),
      appBarTheme: AppBarTheme(
        backgroundColor: surfaceBackground,
        foregroundColor: palette.foregroundPrimary,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        titleTextStyle: textTheme.titleMedium?.copyWith(
          color: palette.foregroundPrimary,
          fontSize: AppTypography.iosNavTitle,
          fontWeight: AppTypography.medium,
        ),
        systemOverlayStyle: systemUiOverlayStyleFor(brightness),
      ),
      dividerTheme: DividerThemeData(
        color: separatorColor,
        thickness: AppSpacing.hairline,
        space: AppSpacing.one,
      ),
      bottomSheetTheme: BottomSheetThemeData(
        backgroundColor: elevatedSurface,
        modalBackgroundColor: elevatedSurface,
        surfaceTintColor: Colors.transparent,
      ),
      cupertinoOverrideTheme: NoDefaultCupertinoThemeData(
        brightness: brightness,
        primaryColor: primaryAccent,
        scaffoldBackgroundColor: scaffoldBackground,
        barBackgroundColor: surfaceBackground.withValues(alpha: 0.92),
        textTheme: CupertinoTextThemeData(
          primaryColor: primaryAccent,
          textStyle: textTheme.bodyMedium?.copyWith(
            fontSize: AppTypography.iosSubheadline,
            height: AppTypography.bodyLineHeight,
          ),
          actionTextStyle: textTheme.bodyLarge?.copyWith(
            color: primaryAccent,
            fontSize: AppTypography.iosButton,
            fontWeight: AppTypography.semiBold,
          ),
          navActionTextStyle: textTheme.bodyLarge?.copyWith(
            color: palette.foregroundPrimary,
            fontSize: AppTypography.iosButton,
            fontWeight: AppTypography.medium,
          ),
          navTitleTextStyle: textTheme.titleLarge?.copyWith(
            fontSize: AppTypography.iosNavTitle,
            fontWeight: AppTypography.medium,
          ),
          navLargeTitleTextStyle: textTheme.headlineMedium?.copyWith(
            fontSize: AppTypography.iosLargeTitle,
            fontWeight: AppTypography.bold,
          ),
          tabLabelTextStyle: textTheme.bodySmall?.copyWith(
            fontSize: AppTypography.iosCaption1,
          ),
          pickerTextStyle: textTheme.bodyLarge?.copyWith(
            fontSize: AppTypography.iosBody,
          ),
          dateTimePickerTextStyle: textTheme.bodyLarge?.copyWith(
            fontSize: AppTypography.iosBody,
          ),
        ),
      ),
      cardColor: elevatedSurface,
      cardTheme: CardThemeData(
        color: elevatedSurface,
        surfaceTintColor: Colors.transparent,
        elevation: 0,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
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
