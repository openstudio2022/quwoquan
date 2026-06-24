import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/cloud/services/user/appearance_settings_repository.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/settings/widgets/settings_appearance_labels.dart';

class SettingsPage extends ConsumerWidget {
  const SettingsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final appearanceState = ref.watch(appearanceSettingsControllerProvider);
    final snapshot = appearanceState.snapshot;
    final isDark = ref.watch(isDarkProvider);
    final authSession = ref.watch(authSessionControllerProvider);

    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.settings,
      onBack: () {
        if (context.canPop()) {
          context.pop();
        } else {
          context.go(AppRoutePaths.profile);
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
                header: UITextConstants.settingsAccountSection,
                child: Column(
                  children: <Widget>[
                    _SettingsActionRow(
                      isDark: isDark,
                      icon: CupertinoIcons.person_crop_circle,
                      label: UITextConstants.profileEditLabel,
                      onTap: () {
                        _trackSettingsClick(
                          ref,
                          'settings_profile_edit_click',
                          targetKey: 'profile_edit',
                        );
                        context.push(AppRoutePaths.profileEdit);
                      },
                    ),
                    SettingsInsetFormSectionDivider(isDark: isDark),
                    _SettingsActionRow(
                      isDark: isDark,
                      icon: CupertinoIcons.person_2,
                      label: UITextConstants.profilePersonasLabel,
                      onTap: () => context.push(AppRoutePaths.profilePersonas),
                    ),
                  ],
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                header: UITextConstants.settingsPrivacySection,
                child: _SettingsActionRow(
                  isDark: isDark,
                  icon: CupertinoIcons.lock_shield,
                  label: UITextConstants.settingsPermissionManagement,
                  onTap: () {
                    _trackSettingsClick(
                      ref,
                      'settings_permission_open',
                      targetKey: 'settings_permissions',
                    );
                    context.push(AppRoutePaths.settingsPermissions);
                  },
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                header: UITextConstants.settingsAppearanceSection,
                child: _SettingsActionRow(
                  isDark: isDark,
                  icon: CupertinoIcons.moon,
                  label: UITextConstants.settingsDarkMode,
                  trailingText: _darkModeSummary(snapshot, appearanceState),
                  onTap: () => _showDarkModeSheet(context, ref, snapshot),
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                header: UITextConstants.settingsAboutSection,
                child: _SettingsActionRow(
                  isDark: isDark,
                  icon: CupertinoIcons.info,
                  label: UITextConstants.settingsAboutQuwoquan,
                  onTap: () {
                    _trackSettingsClick(
                      ref,
                      'settings_about_open',
                      targetKey: 'settings_about',
                    );
                    context.push(AppRoutePaths.settingsAbout);
                  },
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                child: Column(
                  children: <Widget>[
                    if (authSession.isAuthenticated) ...<Widget>[
                      _SettingsActionRow(
                        isDark: isDark,
                        icon: CupertinoIcons.person_crop_circle_badge_plus,
                        label: UITextConstants.switchAccount,
                        onTap: () => _handleLogout(
                          context,
                          ref,
                          clearLocalCredential: false,
                          navigateToLogin: true,
                        ),
                      ),
                      SettingsInsetFormSectionDivider(isDark: isDark),
                      _SettingsActionRow(
                        isDark: isDark,
                        icon: CupertinoIcons.square_arrow_right,
                        label: UITextConstants.logout,
                        isDestructive: true,
                        onTap: () => _confirmLogout(context, ref),
                      ),
                    ] else
                      _SettingsActionRow(
                        isDark: isDark,
                        icon: CupertinoIcons.person_crop_circle_badge_checkmark,
                        label: UITextConstants.profileLoginNow,
                        onTap: () => openLoginPage(
                          context,
                          reasonName: AuthPromptReason.actionRequired.name,
                          redirect: AppRoutePaths.settings,
                          dismissFallback: AppRoutePaths.settings,
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

  static Widget _sectionGap() {
    return SizedBox(
      height: SettingsSemanticConstants.insetFormSectionVerticalGap,
    );
  }

  static String _darkModeSummary(
    AppearanceSettingsSnapshot snapshot,
    AppearanceSettingsState state,
  ) {
    final base = settingsDarkModeLabel(snapshot.themeMode);
    return state.hasPendingSync
        ? UITextConstants.settingsPendingSync(base)
        : base;
  }

  static void _trackSettingsClick(
    WidgetRef ref,
    String eventName, {
    required String targetKey,
  }) {
    unawaited(
      ref
          .read(analyticsProvider)
          .trackEvent(
            AnalyticsEvent(
              eventType: 'settings',
              eventName: eventName,
              properties: <String, dynamic>{
                'pageName': 'settings',
                'routeId': AppRoutePaths.settings,
                'surfaceId': 'settings_homepage',
                'targetType': 'settings_action',
                'targetKey': targetKey,
              },
            ),
          ),
    );
  }

  static Future<void> _showDarkModeSheet(
    BuildContext context,
    WidgetRef ref,
    AppearanceSettingsSnapshot snapshot,
  ) async {
    final selected = await showCupertinoModalPopup<AppearanceThemeMode>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: const Text(UITextConstants.settingsDarkMode),
        actions: AppearanceThemeMode.values
            .map(
              (mode) => CupertinoActionSheetAction(
                isDefaultAction: snapshot.themeMode == mode,
                onPressed: () => Navigator.of(ctx).pop(mode),
                child: Text(settingsDarkModeLabel(mode)),
              ),
            )
            .toList(),
        cancelButton: CupertinoActionSheetAction(
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text(UITextConstants.logoutCancel),
        ),
      ),
    );
    if (selected == null || selected == snapshot.themeMode) {
      return;
    }
    await ref
        .read(appearanceSettingsControllerProvider.notifier)
        .updateSettings(
          themeMode: selected,
          fontSizePreset: snapshot.fontSizePreset,
          applyScope: AppearanceApplyScope.allAccounts,
        );
  }

  static Future<void> _confirmLogout(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final choice = await showCupertinoModalPopup<_LogoutChoice>(
      context: context,
      builder: (ctx) => CupertinoActionSheet(
        title: const Text(UITextConstants.logoutSheetTitle),
        message: const Text(UITextConstants.logoutSheetMessage),
        actions: <Widget>[
          CupertinoActionSheetAction(
            onPressed: () => Navigator.of(ctx).pop(_LogoutChoice.soft),
            child: const Text(UITextConstants.logoutSoftAction),
          ),
          CupertinoActionSheetAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(ctx).pop(_LogoutChoice.hard),
            child: const Text(UITextConstants.logoutHardAction),
          ),
        ],
        cancelButton: CupertinoActionSheetAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text(UITextConstants.logoutCancel),
        ),
      ),
    );
    if (choice == null || !context.mounted) {
      return;
    }
    await _handleLogout(
      context,
      ref,
      clearLocalCredential: choice == _LogoutChoice.hard,
      navigateToLogin: true,
    );
  }

  static Future<void> _handleLogout(
    BuildContext context,
    WidgetRef ref, {
    required bool clearLocalCredential,
    required bool navigateToLogin,
  }) async {
    final controller = ref.read(authSessionControllerProvider.notifier);
    if (clearLocalCredential) {
      final session = ref.read(authSessionControllerProvider);
      try {
        await ref
            .read(authRepositoryProvider)
            .logout(
              refreshToken: session.refreshToken,
              deviceId: session.installId,
            );
      } catch (_) {
        // 本地退出优先，远端吊销失败由下次 refresh 兜底。
      }
      await controller.hardLogout();
    } else {
      await controller.softLogout();
    }
    if (!context.mounted) {
      return;
    }
    final days = (kDefaultSessionRememberTtlSeconds / 86400).round();
    AppToast.show(
      context,
      clearLocalCredential
          ? UITextConstants.loginHardLogoutToast
          : UITextConstants.loginSoftLogoutToast.replaceFirst(
              '{days}',
              '$days',
            ),
    );
    if (!navigateToLogin) {
      return;
    }
    openLoginPage(
      context,
      reasonName: AuthPromptReason.manualLoggedOut.name,
      replace: true,
      allowGuestDismissPop: false,
    );
  }
}

enum _LogoutChoice { soft, hard }

class _SettingsActionRow extends StatelessWidget {
  const _SettingsActionRow({
    required this.isDark,
    required this.icon,
    required this.label,
    this.trailingText,
    this.onTap,
    this.isDestructive = false,
  });

  final bool isDark;
  final IconData icon;
  final String label;
  final String? trailingText;
  final VoidCallback? onTap;
  final bool isDestructive;

  @override
  Widget build(BuildContext context) {
    final labelColor = isDestructive
        ? AppColors.iosDestructive(context)
        : SettingsSemanticConstants.labelColor(isDark);
    final secondaryColor = SettingsSemanticConstants.secondaryColor(isDark);
    final trailing = trailingText;

    return CupertinoButton(
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
              Icon(icon, size: AppSpacing.iconMedium, color: secondaryColor),
              SizedBox(width: AppSpacing.containerSm),
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
              if (trailing != null && trailing.trim().isNotEmpty) ...<Widget>[
                SizedBox(width: AppSpacing.intraGroupSm),
                Flexible(
                  child: Text(
                    trailing,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.right,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      color: secondaryColor,
                    ),
                  ),
                ),
              ],
              if (onTap != null) ...<Widget>[
                SizedBox(width: AppSpacing.intraGroupSm),
                Icon(
                  CupertinoIcons.chevron_forward,
                  size: AppSpacing.iconSmall,
                  color: secondaryColor,
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
