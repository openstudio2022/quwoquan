import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
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
  }
}
