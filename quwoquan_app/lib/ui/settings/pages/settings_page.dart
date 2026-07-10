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
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsAccountSection,
                child: Column(
                  children: <Widget>[
                    SettingsInsetNavigationRow(
                      isDark: isDark,
                      leadingIcon: CupertinoIcons.person_crop_circle,
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
                    SettingsInsetFormSectionDivider(
                      isDark: isDark,
                      leadingInset: SettingsSemanticConstants
                          .insetFormIconDividerLeadingInset,
                    ),
                    SettingsInsetNavigationRow(
                      isDark: isDark,
                      leadingIcon: CupertinoIcons.person_2,
                      label: UITextConstants.profilePersonasLabel,
                      onTap: () => context.push(AppRoutePaths.profilePersonas),
                    ),
                  ],
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsPrivacySection,
                child: SettingsInsetNavigationRow(
                  isDark: isDark,
                  leadingIcon: CupertinoIcons.lock_shield,
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
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsAppearanceSection,
                child: SettingsInsetNavigationRow(
                  isDark: isDark,
                  leadingIcon: CupertinoIcons.moon,
                  label: UITextConstants.settingsDarkMode,
                  trailingText: _darkModeSummary(snapshot, appearanceState),
                  onTap: () => context.push(AppRoutePaths.settingsDarkMode),
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsAboutSection,
                child: SettingsInsetNavigationRow(
                  isDark: isDark,
                  leadingIcon: CupertinoIcons.info,
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
                density: SettingsInsetSectionDensity.compact,
                child: Column(
                  children: <Widget>[
                    if (authSession.isAuthenticated) ...<Widget>[
                      SettingsInsetCenteredActionRow(
                        isDark: isDark,
                        label: UITextConstants.switchAccount,
                        onTap: () => _handleLogout(
                          context,
                          ref,
                          clearLocalCredential: false,
                          navigateToLogin: true,
                        ),
                      ),
                      SettingsInsetFormSectionDivider(isDark: isDark),
                      SettingsInsetCenteredActionRow(
                        isDark: isDark,
                        label: UITextConstants.logout,
                        isDestructive: true,
                        onTap: () => _confirmLogout(context, ref),
                      ),
                    ] else
                      SettingsInsetCenteredActionRow(
                        isDark: isDark,
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

  static Future<void> _confirmLogout(
    BuildContext context,
    WidgetRef ref,
  ) async {
    final choice = await showAppCupertinoDialog<_LogoutChoice>(
      context: context,
      builder: (ctx) => CupertinoAlertDialog(
        title: const Text(UITextConstants.logoutDialogTitle),
        content: const Text(UITextConstants.logoutDialogMessage),
        actions: <Widget>[
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(),
            child: const Text(UITextConstants.logoutDialogCancel),
          ),
          CupertinoDialogAction(
            onPressed: () => Navigator.of(ctx).pop(_LogoutChoice.soft),
            child: const Text(UITextConstants.logoutDialogSoftAction),
          ),
          CupertinoDialogAction(
            isDestructiveAction: true,
            onPressed: () => Navigator.of(ctx).pop(_LogoutChoice.hard),
            child: const Text(UITextConstants.logoutDialogHardAction),
          ),
        ],
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
