import 'package:quwoquan_app/runtime/shell/settings/appearance_settings_models.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

String settingsDarkModeLabel(AppearanceThemeMode mode) => switch (mode) {
  AppearanceThemeMode.light => SettingsText.settingsDarkModeOff,
  AppearanceThemeMode.dark => SettingsText.settingsDarkModeOn,
  AppearanceThemeMode.system => SettingsText.settingsDarkModeSystem,
};
