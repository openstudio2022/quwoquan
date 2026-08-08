import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/runtime/observability/analytics.dart';
import 'package:quwoquan_app/runtime/shell/settings/appearance_settings_models.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/runtime/shell/state/appearance_settings_provider.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/layout/web_page_max_width_frame.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';

class SettingsDarkModePage extends ConsumerStatefulWidget {
  const SettingsDarkModePage({super.key});

  @override
  ConsumerState<SettingsDarkModePage> createState() =>
      _SettingsDarkModePageState();
}

class _SettingsDarkModePageState extends ConsumerState<SettingsDarkModePage> {
  @override
  void initState() {
    super.initState();
    unawaited(
      Future<void>.microtask(
        () => ref.read(appearanceSettingsControllerProvider.notifier).refresh(),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final appearanceState = ref.watch(appearanceSettingsControllerProvider);
    final snapshot = appearanceState.snapshot;

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: SettingsText.settingsDarkMode,
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
          child: appearanceState.isLoading
              ? AppRequestFeedback.section()
              : !appearanceState.hasLoaded
              ? _buildUnavailable(appearanceState)
              : ListView(
                  padding: EdgeInsets.only(
                    left: SettingsSemanticConstants
                        .insetFormListHorizontalPadding,
                    right: SettingsSemanticConstants
                        .insetFormListHorizontalPadding,
                    top: AppSpacing.intraGroupSm,
                    bottom: AppSpacing.xl,
                  ),
                  children: <Widget>[
                    if (appearanceState.lastError != null) ...<Widget>[
                      SettingsInsetGroupedSection(
                        isDark: isDark,
                        child: SettingsInsetNavigationRow(
                          isDark: isDark,
                          label: SettingsText.settingsSyncFailed,
                          trailingText: SettingsText.settingsRetrySync,
                          isDestructive: true,
                          onTap: () => ref
                              .read(
                                appearanceSettingsControllerProvider.notifier,
                              )
                              .syncPending(),
                        ),
                      ),
                      SizedBox(
                        height: SettingsSemanticConstants
                            .insetFormSectionVerticalGap,
                      ),
                    ],
                    SettingsInsetGroupedSection(
                      isDark: isDark,
                      density: SettingsInsetSectionDensity.compact,
                      child: SettingsInsetSwitchRow(
                        isDark: isDark,
                        label: SettingsText.settingsDarkModeSystem,
                        subtitle:
                            SettingsText.settingsDarkModeSystemDescription,
                        value: snapshot.themeMode == AppearanceThemeMode.system,
                        onChanged: (value) => _updateThemeMode(
                          snapshot,
                          value
                              ? AppearanceThemeMode.system
                              : AppearanceThemeMode.light,
                        ),
                      ),
                    ),
                    SizedBox(
                      height:
                          SettingsSemanticConstants.insetFormSectionVerticalGap,
                    ),
                    SettingsInsetGroupedSection(
                      isDark: isDark,
                      density: SettingsInsetSectionDensity.compact,
                      header: SettingsText.settingsDarkModeManualSection,
                      child: Column(
                        children: <Widget>[
                          SettingsInsetChoiceRow(
                            key: const ValueKey<AppearanceThemeMode>(
                              AppearanceThemeMode.light,
                            ),
                            isDark: isDark,
                            label: SettingsText.settingsDarkModeLightOption,
                            isSelected:
                                snapshot.themeMode == AppearanceThemeMode.light,
                            onTap: () => _updateThemeMode(
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
                            label: SettingsText.settingsDarkModeDarkOption,
                            isSelected:
                                snapshot.themeMode == AppearanceThemeMode.dark,
                            onTap: () => _updateThemeMode(
                              snapshot,
                              AppearanceThemeMode.dark,
                            ),
                          ),
                        ],
                      ),
                    ),
                    SizedBox(
                      height:
                          SettingsSemanticConstants.insetFormSectionVerticalGap,
                    ),
                    SettingsInsetGroupedSection(
                      isDark: isDark,
                      density: SettingsInsetSectionDensity.compact,
                      header: SettingsText.settingsFontSizeSection,
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
                                snapshot,
                                AppearanceFontSizePreset.values[index],
                              ),
                            ),
                            if (index + 1 <
                                AppearanceFontSizePreset.values.length)
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

  Widget _buildUnavailable(AppearanceSettingsState state) => AppPageErrorState(
    semantic: UiErrorSemanticResolver.resolve(
      context,
      error: state.lastError ?? StateError('appearance_settings_unavailable'),
      category: UiErrorCategory.pageLoad,
      scope: UiErrorScope.page,
    ),
    onRecovery: (action) async {
      if (action.type != UiErrorActionType.retry) {
        return UiRecoveryOutcome.cancelled;
      }
      await ref.read(appearanceSettingsControllerProvider.notifier).refresh();
      final current = ref.read(appearanceSettingsControllerProvider);
      return current.hasLoaded && current.lastError == null
          ? UiRecoveryOutcome.recovered
          : UiRecoveryOutcome.stillBlocked;
    },
  );

  Future<void> _updateThemeMode(
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
    _trackAppearanceAction('settings_theme_mode_changed');
  }

  Future<void> _updateFontSize(
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
    _trackAppearanceAction('settings_font_size_changed');
  }

  static String _fontSizeLabel(AppearanceFontSizePreset preset) =>
      switch (preset) {
        AppearanceFontSizePreset.xs => SettingsText.settingsFontSizeXs,
        AppearanceFontSizePreset.sm => SettingsText.settingsFontSizeSm,
        AppearanceFontSizePreset.md => SettingsText.settingsFontSizeMd,
        AppearanceFontSizePreset.lg => SettingsText.settingsFontSizeLg,
        AppearanceFontSizePreset.xl => SettingsText.settingsFontSizeXl,
      };

  void _trackAppearanceAction(String action) {
    ref
        .read(analyticsProvider)
        .trackEvent(
          AnalyticsEvent(
            eventType: 'settings',
            eventName: action,
            properties: <String, Object?>{'action': action},
          ),
        );
  }
}
