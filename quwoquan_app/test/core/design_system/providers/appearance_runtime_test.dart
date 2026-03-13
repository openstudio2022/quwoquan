import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:quwoquan_app/app/providers/accessibility_provider.dart';
import 'package:quwoquan_app/core/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/core/design_system/theme/app_theme.dart';
import 'package:quwoquan_app/core/providers/app_providers.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  GoogleFonts.config.allowRuntimeFetching = false;

  group('ThemeNotifier', () {
    test('默认跟随系统主题', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final state = container.read(themeProvider);

      expect(state.themeModeSetting, AppThemeModeSetting.system);
      expect(state.themeMode, ThemeMode.system);
      expect(state.effectiveBrightness, Brightness.light);
      expect(container.read(effectiveIsDarkProvider), isFalse);
    });

    test('system 模式下系统亮度变化会驱动 effective brightness', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      container.read(themeProvider.notifier).updateSystemBrightness(
            Brightness.dark,
          );

      final state = container.read(themeProvider);
      expect(state.themeModeSetting, AppThemeModeSetting.system);
      expect(state.effectiveBrightness, Brightness.dark);
      expect(container.read(effectiveIsDarkProvider), isTrue);
    });

    test('toggleTheme 从 system 切到当前亮度反向的显式主题', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      container.read(themeProvider.notifier).updateSystemBrightness(
            Brightness.light,
          );
      container.read(themeProvider.notifier).toggleTheme();

      final state = container.read(themeProvider);
      expect(state.themeModeSetting, AppThemeModeSetting.dark);
      expect(state.themeMode, ThemeMode.dark);
      expect(state.isDark, isTrue);
    });
  });

  group('AccessibilityNotifier', () {
    test('字号预设会叠加到系统 text scale', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      final notifier = container.read(accessibilityProvider.notifier);
      notifier.setSystemTextScaleFactor(1.1);
      notifier.setFontSizePreset(AppFontSizePreset.lg);

      final state = container.read(accessibilityProvider);
      expect(state.actualTextScaleFactor, closeTo(1.21, 0.0001));
    });

    test('可从 MediaQueryData 同步系统无障碍设置', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      const mediaQueryData = MediaQueryData(
        size: Size(834, 1194),
        boldText: true,
        highContrast: true,
        textScaler: TextScaler.linear(1.2),
      );

      container
          .read(accessibilityProvider.notifier)
          .updateFromMediaQueryData(mediaQueryData);

      final state = container.read(accessibilityProvider);
      expect(state.boldText, isTrue);
      expect(state.highContrast, isTrue);
      expect(state.textScaleFactor, closeTo(1.2, 0.0001));
    });
  });

  group('ResponsiveNotifier', () {
    test('宽度会映射到 compact / regular / expanded', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      const compactData = MediaQueryData(size: Size(320, 640));
      const regularData = MediaQueryData(size: Size(390, 844));
      const expandedData = MediaQueryData(size: Size(834, 1194));

      container
          .read(responsiveProvider.notifier)
          .updateFromMediaQueryData(compactData);
      expect(container.read(responsiveProvider).breakpoint, AppBreakpoint.compact);

      container
          .read(responsiveProvider.notifier)
          .updateFromMediaQueryData(regularData);
      expect(container.read(responsiveProvider).breakpoint, AppBreakpoint.regular);

      container
          .read(responsiveProvider.notifier)
          .updateFromMediaQueryData(expandedData);
      expect(container.read(responsiveProvider).breakpoint, AppBreakpoint.expanded);
    });
  });

  group('appearanceSnapshotProvider', () {
    test('汇总主题、字号和断点', () {
      final container = ProviderContainer();
      addTearDown(container.dispose);

      container.read(themeProvider.notifier).updateSystemBrightness(
            Brightness.dark,
          );
      container.read(accessibilityProvider.notifier).setSystemTextScaleFactor(1.0);
      container.read(accessibilityProvider.notifier).setFontSizePreset(
            AppFontSizePreset.xl,
          );
      container
          .read(responsiveProvider.notifier)
          .updateFromMediaQueryData(const MediaQueryData(size: Size(1024, 768)));

      final snapshot = container.read(appearanceSnapshotProvider);
      expect(snapshot.themeMode, ThemeMode.system);
      expect(snapshot.isDark, isTrue);
      expect(snapshot.breakpoint, AppBreakpoint.expanded);
      expect(snapshot.textScaleFactor, closeTo(1.2, 0.0001));
    });
  });

  group('AppTheme', () {
    test('light 和 dark theme 都提供 Cupertino override', () {
      expect(AppTheme.lightTheme.cupertinoOverrideTheme, isNotNull);
      expect(AppTheme.darkTheme.cupertinoOverrideTheme, isNotNull);
      expect(
        AppTheme.lightTheme.cupertinoOverrideTheme?.brightness,
        Brightness.light,
      );
      expect(
        AppTheme.darkTheme.cupertinoOverrideTheme?.brightness,
        Brightness.dark,
      );
    });

    test('深色系统栏样式使用亮色图标', () {
      final overlay = AppTheme.systemUiOverlayStyleFor(Brightness.dark);
      expect(overlay.statusBarIconBrightness, Brightness.light);
      expect(overlay.systemNavigationBarIconBrightness, Brightness.light);
    });
  });
}
