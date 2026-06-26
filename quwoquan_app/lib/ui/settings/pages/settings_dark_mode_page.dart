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
                child: _FollowSystemRow(
                  isDark: isDark,
                  isSelected: snapshot.themeMode == AppearanceThemeMode.system,
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
                header: UITextConstants.settingsDarkModeManualSection,
                child: Column(
                  children: <Widget>[
                    _ManualThemeModeRow(
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
                    _ManualThemeModeRow(
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

class _FollowSystemRow extends StatelessWidget {
  const _FollowSystemRow({
    required this.isDark,
    required this.isSelected,
    required this.onChanged,
  });

  final bool isDark;
  final bool isSelected;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final labelColor = SettingsSemanticConstants.labelColor(isDark);
    final secondaryColor = SettingsSemanticConstants.secondaryColor(isDark);
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: () => onChanged(!isSelected),
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: AppSpacing.minInteractiveSize,
            ),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(
                        UITextConstants.settingsDarkModeSystem,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosSubheadline,
                          fontWeight: AppTypography.regular,
                          color: labelColor,
                        ),
                      ),
                      SizedBox(height: AppSpacing.xs),
                      Text(
                        UITextConstants.settingsDarkModeSystemDescription,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          fontWeight: AppTypography.regular,
                          color: secondaryColor,
                        ),
                      ),
                    ],
                  ),
                ),
                SizedBox(width: AppSpacing.containerMd),
                CupertinoSwitch(
                  value: isSelected,
                  onChanged: onChanged,
                  activeTrackColor:
                      SettingsSemanticConstants.switchActiveTrackColor,
                  inactiveTrackColor:
                      SettingsSemanticConstants.switchInactiveTrackColor(
                        isDark,
                      ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ManualThemeModeRow extends StatelessWidget {
  const _ManualThemeModeRow({
    super.key,
    required this.isDark,
    required this.label,
    required this.isSelected,
    required this.onTap,
  });

  final bool isDark;
  final String label;
  final bool isSelected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final labelColor = SettingsSemanticConstants.labelColor(isDark);
    return SizedBox(
      width: double.infinity,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Padding(
          padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
          child: ConstrainedBox(
            constraints: const BoxConstraints(
              minHeight: AppSpacing.minInteractiveSize,
            ),
            child: Row(
              children: <Widget>[
                Expanded(
                  child: Text(
                    label,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.regular,
                      color: labelColor,
                    ),
                  ),
                ),
                if (isSelected)
                  Icon(
                    CupertinoIcons.check_mark,
                    size: AppSpacing.iconSmall,
                    color: AppColors.primaryColor,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
