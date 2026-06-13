import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';

String settingsThemeModeLabel(AppearanceThemeMode mode) => switch (mode) {
  AppearanceThemeMode.system => '跟随系统',
  AppearanceThemeMode.light => '浅色',
  AppearanceThemeMode.dark => '深色',
};

String settingsFontSizePresetLabel(AppearanceFontSizePreset preset) =>
    switch (preset) {
      AppearanceFontSizePreset.xs => '特小',
      AppearanceFontSizePreset.sm => '偏小',
      AppearanceFontSizePreset.md => '标准',
      AppearanceFontSizePreset.lg => '偏大',
      AppearanceFontSizePreset.xl => '特大',
    };

String settingsFontSizePresetDescription(AppearanceFontSizePreset preset) =>
    switch (preset) {
      AppearanceFontSizePreset.xs => '适合高信息密度浏览',
      AppearanceFontSizePreset.sm => '比默认更紧凑',
      AppearanceFontSizePreset.md => '推荐默认设置',
      AppearanceFontSizePreset.lg => '更适合长时间阅读',
      AppearanceFontSizePreset.xl => '最大字号，适合远距或弱视场景',
    };

String settingsSourceLabel(AppearanceSettingsSource source) => switch (source) {
  AppearanceSettingsSource.ownerDefault => 'Owner 默认',
  AppearanceSettingsSource.subOverride => '当前子账号覆盖',
  AppearanceSettingsSource.systemDefault => '系统默认',
};
