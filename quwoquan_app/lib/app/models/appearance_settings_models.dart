import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    as contracts;

enum AppearanceThemeMode {
  system('system'),
  light('light'),
  dark('dark');

  const AppearanceThemeMode(this.wireValue);
  final String wireValue;

  static AppearanceThemeMode fromWire(String? value) =>
      AppearanceThemeMode.values.firstWhere(
        (mode) => mode.wireValue == value,
        orElse: () => AppearanceThemeMode.system,
      );
}

enum AppearanceFontSizePreset {
  xs('xs'),
  sm('sm'),
  md('md'),
  lg('lg'),
  xl('xl');

  const AppearanceFontSizePreset(this.wireValue);
  final String wireValue;

  static AppearanceFontSizePreset fromWire(String? value) =>
      AppearanceFontSizePreset.values.firstWhere(
        (preset) => preset.wireValue == value,
        orElse: () => AppearanceFontSizePreset.md,
      );
}

enum AppearanceSettingsSource {
  ownerDefault('owner_default'),
  subOverride('sub_override'),
  systemDefault('system_default');

  const AppearanceSettingsSource(this.wireValue);
  final String wireValue;

  static AppearanceSettingsSource fromWire(String? value) =>
      AppearanceSettingsSource.values.firstWhere(
        (source) => source.wireValue == value,
        orElse: () => AppearanceSettingsSource.systemDefault,
      );
}

enum AppearanceApplyScope {
  allAccounts,
  currentPersona,
  inheritOwnerDefault;

  contracts.AppearanceApplyScope get contract => switch (this) {
    AppearanceApplyScope.allAccounts =>
      contracts.AppearanceApplyScope.allAccounts,
    AppearanceApplyScope.currentPersona =>
      contracts.AppearanceApplyScope.currentPersona,
    AppearanceApplyScope.inheritOwnerDefault =>
      contracts.AppearanceApplyScope.inheritOwnerDefault,
  };
}

class AppearanceSettingsSnapshot {
  const AppearanceSettingsSnapshot({
    required this.themeMode,
    required this.fontSizePreset,
    required this.source,
    required this.ownerDefaultThemeMode,
    required this.ownerDefaultFontSizePreset,
    required this.hasPersonaOverride,
    required this.version,
    required this.updatedAt,
    this.pendingSync = false,
  });

  final AppearanceThemeMode themeMode;
  final AppearanceFontSizePreset fontSizePreset;
  final AppearanceSettingsSource source;
  final AppearanceThemeMode ownerDefaultThemeMode;
  final AppearanceFontSizePreset ownerDefaultFontSizePreset;
  final bool hasPersonaOverride;
  final int version;
  final DateTime updatedAt;
  final bool pendingSync;

  factory AppearanceSettingsSnapshot.fromContract(
    contracts.AppearanceSettingsView view,
  ) => AppearanceSettingsSnapshot(
    themeMode: AppearanceThemeMode.fromWire(view.themeMode.wireValue),
    fontSizePreset: AppearanceFontSizePreset.fromWire(
      view.fontSizePreset.wireValue,
    ),
    source: AppearanceSettingsSource.fromWire(view.source.wireValue),
    ownerDefaultThemeMode: AppearanceThemeMode.fromWire(
      view.ownerDefaultThemeMode.wireValue,
    ),
    ownerDefaultFontSizePreset: AppearanceFontSizePreset.fromWire(
      view.ownerDefaultFontSizePreset.wireValue,
    ),
    hasPersonaOverride: view.hasPersonaOverride,
    version: view.version,
    updatedAt: view.updatedAt,
  );

  AppearanceSettingsSnapshot copyWith({
    AppearanceThemeMode? themeMode,
    AppearanceFontSizePreset? fontSizePreset,
    AppearanceSettingsSource? source,
    AppearanceThemeMode? ownerDefaultThemeMode,
    AppearanceFontSizePreset? ownerDefaultFontSizePreset,
    bool? hasPersonaOverride,
    int? version,
    DateTime? updatedAt,
    bool? pendingSync,
  }) => AppearanceSettingsSnapshot(
    themeMode: themeMode ?? this.themeMode,
    fontSizePreset: fontSizePreset ?? this.fontSizePreset,
    source: source ?? this.source,
    ownerDefaultThemeMode: ownerDefaultThemeMode ?? this.ownerDefaultThemeMode,
    ownerDefaultFontSizePreset:
        ownerDefaultFontSizePreset ?? this.ownerDefaultFontSizePreset,
    hasPersonaOverride: hasPersonaOverride ?? this.hasPersonaOverride,
    version: version ?? this.version,
    updatedAt: updatedAt ?? this.updatedAt,
    pendingSync: pendingSync ?? this.pendingSync,
  );
}

class AppearanceSettingsMutation {
  const AppearanceSettingsMutation({
    required this.themeMode,
    required this.fontSizePreset,
    required this.applyScope,
  });

  final AppearanceThemeMode themeMode;
  final AppearanceFontSizePreset fontSizePreset;
  final AppearanceApplyScope applyScope;

  contracts.UpdateAppearanceSettingsCommand get contract =>
      contracts.UpdateAppearanceSettingsCommand(
        themeMode: switch (themeMode) {
          AppearanceThemeMode.system => contracts.ThemeModeSetting.system,
          AppearanceThemeMode.light => contracts.ThemeModeSetting.light,
          AppearanceThemeMode.dark => contracts.ThemeModeSetting.dark,
        },
        fontSizePreset: switch (fontSizePreset) {
          AppearanceFontSizePreset.xs => contracts.FontSizePreset.xs,
          AppearanceFontSizePreset.sm => contracts.FontSizePreset.sm,
          AppearanceFontSizePreset.md => contracts.FontSizePreset.md,
          AppearanceFontSizePreset.lg => contracts.FontSizePreset.lg,
          AppearanceFontSizePreset.xl => contracts.FontSizePreset.xl,
        },
        applyScope: applyScope.contract,
      );
}
