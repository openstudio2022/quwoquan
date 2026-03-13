import 'dart:ui' show PlatformDispatcher;

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

enum AppThemeModeSetting { system, light, dark }

class ThemeState {
  final AppThemeModeSetting themeModeSetting;
  final Brightness systemBrightness;

  const ThemeState({
    this.themeModeSetting = AppThemeModeSetting.system,
    this.systemBrightness = Brightness.light,
  });

  ThemeMode get themeMode => switch (themeModeSetting) {
    AppThemeModeSetting.system => ThemeMode.system,
    AppThemeModeSetting.light => ThemeMode.light,
    AppThemeModeSetting.dark => ThemeMode.dark,
  };

  Brightness get effectiveBrightness => switch (themeModeSetting) {
    AppThemeModeSetting.system => systemBrightness,
    AppThemeModeSetting.light => Brightness.light,
    AppThemeModeSetting.dark => Brightness.dark,
  };

  bool get isDark => effectiveBrightness == Brightness.dark;

  ThemeState copyWith({
    AppThemeModeSetting? themeModeSetting,
    Brightness? systemBrightness,
  }) {
    return ThemeState(
      themeModeSetting: themeModeSetting ?? this.themeModeSetting,
      systemBrightness: systemBrightness ?? this.systemBrightness,
    );
  }

  @override
  bool operator ==(Object other) {
    return other is ThemeState &&
        other.themeModeSetting == themeModeSetting &&
        other.systemBrightness == systemBrightness;
  }

  @override
  int get hashCode => Object.hash(themeModeSetting, systemBrightness);
}

class ThemeNotifier extends Notifier<ThemeState> {
  @override
  ThemeState build() {
    return ThemeState(
      systemBrightness: PlatformDispatcher.instance.platformBrightness,
    );
  }

  void toggleTheme() {
    final nextSetting = switch (state.effectiveBrightness) {
      Brightness.dark => AppThemeModeSetting.light,
      Brightness.light => AppThemeModeSetting.dark,
    };
    setThemeModeSetting(nextSetting);
  }

  void setDark(bool isDark) {
    setThemeModeSetting(
      isDark ? AppThemeModeSetting.dark : AppThemeModeSetting.light,
    );
  }

  void setThemeModeSetting(AppThemeModeSetting setting) {
    if (state.themeModeSetting == setting) return;
    state = state.copyWith(themeModeSetting: setting);
  }

  void updateSystemBrightness(Brightness brightness) {
    if (state.systemBrightness == brightness) return;
    state = state.copyWith(systemBrightness: brightness);
  }

  void resetToSystem() {
    setThemeModeSetting(AppThemeModeSetting.system);
  }
}

final themeProvider = NotifierProvider<ThemeNotifier, ThemeState>(() {
  return ThemeNotifier();
});

final effectiveIsDarkProvider = Provider<bool>((ref) {
  return ref.watch(themeProvider).isDark;
});

