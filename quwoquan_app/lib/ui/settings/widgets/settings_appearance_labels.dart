import 'package:quwoquan_app/app/models/appearance_settings_models.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';

String settingsDarkModeLabel(AppearanceThemeMode mode) => switch (mode) {
  AppearanceThemeMode.light => UITextConstants.settingsDarkModeOff,
  AppearanceThemeMode.dark => UITextConstants.settingsDarkModeOn,
  AppearanceThemeMode.system => UITextConstants.settingsDarkModeSystem,
};
