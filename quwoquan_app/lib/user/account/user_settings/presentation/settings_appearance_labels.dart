import 'package:quwoquan_app/app/models/appearance_settings_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

String settingsDarkModeLabel(AppearanceThemeMode mode) => switch (mode) {
  AppearanceThemeMode.light => SettingsText.settingsDarkModeOff,
  AppearanceThemeMode.dark => SettingsText.settingsDarkModeOn,
  AppearanceThemeMode.system => SettingsText.settingsDarkModeSystem,
};
