import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/app/models/appearance_settings_models.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class SettingsDarkModePage extends ConsumerWidget {
  const SettingsDarkModePage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final appearanceState = ref.watch(appearanceSettingsControllerProvider);
    final snapshot = appearanceState.snapshot;

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.settingsDarkMode,
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoutePaths.settings);
        }
      },
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: ListView(
            padding: EdgeInsets.only(
              left: SettingsSemanticConstants.insetFormListHorizontalPadding,
              right: SettingsSemanticConstants.insetFormListHorizontalPadding,
              top: AppSpacing.intraGroupSm,
              bottom: AppSpacing.xl,
            ),
            children: <Widget>[
              if (appearanceState.lastError != null) ...<Widget>[
                SettingsInsetGroupedSection(
                  isDark: isDark,
                  child: SettingsInsetNavigationRow(
                    isDark: isDark,
                    label: UITextConstants.settingsSyncFailed,
                    trailingText: UITextConstants.settingsRetrySync,
                    isDestructive: true,
                    onTap: () => ref
                        .read(appearanceSettingsControllerProvider.notifier)
                        .syncPending(),
                  ),
                ),
                SizedBox(
                  height: SettingsSemanticConstants.insetFormSectionVerticalGap,
                ),
              ],
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                child: SettingsInsetSwitchRow(
                  isDark: isDark,
                  label: UITextConstants.settingsDarkModeSystem,
                  subtitle: UITextConstants.settingsDarkModeSystemDescription,
                  value: snapshot.themeMode == AppearanceThemeMode.system,
                  onChanged: (value) => _updateThemeMode(
                    ref,
                    snapshot,
                    value
                        ? AppearanceThemeMode.system
                        : AppearanceThemeMode.light,
                  ),
                ),
              ),
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsDarkModeManualSection,
                child: Column(
                  children: <Widget>[
                    SettingsInsetChoiceRow(
                      key: const ValueKey<AppearanceThemeMode>(
                        AppearanceThemeMode.light,
                      ),
                      isDark: isDark,
                      label: UITextConstants.settingsDarkModeLightOption,
                      isSelected:
                          snapshot.themeMode == AppearanceThemeMode.light,
                      onTap: () => _updateThemeMode(
                        ref,
                        snapshot,
                        AppearanceThemeMode.light,
                      ),
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    SettingsInsetChoiceRow(
                      key: const ValueKey<AppearanceThemeMode>(
                        AppearanceThemeMode.dark,
                      ),
                      isDark: isDark,
                      label: UITextConstants.settingsDarkModeDarkOption,
                      isSelected:
                          snapshot.themeMode == AppearanceThemeMode.dark,
                      onTap: () => _updateThemeMode(
                        ref,
                        snapshot,
                        AppearanceThemeMode.dark,
                      ),
                    ),
                  ],
                ),
              ),
              SizedBox(
                height: SettingsSemanticConstants.insetFormSectionVerticalGap,
              ),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsFontSizeSection,
                child: Column(
                  children: <Widget>[
                    for (
                      var index = 0;
                      index < AppearanceFontSizePreset.values.length;
                      index++
                    ) ...<Widget>[
                      SettingsInsetChoiceRow(
                        key: ValueKey<AppearanceFontSizePreset>(
                          AppearanceFontSizePreset.values[index],
                        ),
                        isDark: isDark,
                        label: _fontSizeLabel(
                          AppearanceFontSizePreset.values[index],
                        ),
                        isSelected:
                            snapshot.fontSizePreset ==
                            AppearanceFontSizePreset.values[index],
                        onTap: () => _updateFontSize(
                          ref,
                          snapshot,
                          AppearanceFontSizePreset.values[index],
                        ),
                      ),
                      if (index + 1 < AppearanceFontSizePreset.values.length)
                        SettingsInsetFormSectionDivider(isDark: isDark),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  static Future<void> _updateThemeMode(
    WidgetRef ref,
    AppearanceSettingsSnapshot snapshot,
    AppearanceThemeMode themeMode,
  ) async {
    if (snapshot.themeMode == themeMode) {
      return;
    }
    await ref
        .read(appearanceSettingsControllerProvider.notifier)
        .updateSettings(
          themeMode: themeMode,
          fontSizePreset: snapshot.fontSizePreset,
          applyScope: AppearanceApplyScope.allAccounts,
        );
    _trackAppearanceAction(ref, 'settings_theme_mode_changed');
  }

  static Future<void> _updateFontSize(
    WidgetRef ref,
    AppearanceSettingsSnapshot snapshot,
    AppearanceFontSizePreset preset,
  ) async {
    if (snapshot.fontSizePreset == preset) return;
    await ref
        .read(appearanceSettingsControllerProvider.notifier)
        .updateSettings(
          themeMode: snapshot.themeMode,
          fontSizePreset: preset,
          applyScope: AppearanceApplyScope.allAccounts,
        );
    _trackAppearanceAction(ref, 'settings_font_size_changed');
  }

  static String _fontSizeLabel(AppearanceFontSizePreset preset) =>
      switch (preset) {
        AppearanceFontSizePreset.xs => UITextConstants.settingsFontSizeXs,
        AppearanceFontSizePreset.sm => UITextConstants.settingsFontSizeSm,
        AppearanceFontSizePreset.md => UITextConstants.settingsFontSizeMd,
        AppearanceFontSizePreset.lg => UITextConstants.settingsFontSizeLg,
        AppearanceFontSizePreset.xl => UITextConstants.settingsFontSizeXl,
      };

  static void _trackAppearanceAction(WidgetRef ref, String action) {
    ref
        .read(analyticsProvider)
        .trackEvent(
          AnalyticsEvent(
            eventType: 'settings',
        eventName: action,
            properties: <String, dynamic>{'action': action},
          ),
        );
  }
}
