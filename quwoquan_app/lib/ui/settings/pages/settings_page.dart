import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/analytics/analytics.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/app/navigation/generated/app_ui_surfaces.g.dart';
import 'package:quwoquan_app/app/providers/appearance_settings_provider.dart';
import 'package:quwoquan_app/assistant/observability/logging/app_exception_telemetry_service.dart';
import 'package:quwoquan_app/app/models/appearance_settings_models.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/settings/widgets/settings_appearance_labels.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show AppCloudOperationIds, LogoutCommand;

class SettingsPage extends ConsumerStatefulWidget {
  const SettingsPage({super.key});

  @override
  ConsumerState<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends ConsumerState<SettingsPage> {
  @override
  Widget build(BuildContext context) {
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
                      onTap: () {
                        _trackSettingsClick(
                          ref,
                          'settings_personas_open',
                          targetKey: 'profile_personas',
                        );
                        context.push(AppRoutePaths.profilePersonas);
                      },
                    ),
                    if (authSession.isAuthenticated) ...<Widget>[
                      SettingsInsetFormSectionDivider(
                        isDark: isDark,
                        leadingInset: SettingsSemanticConstants
                            .insetFormIconDividerLeadingInset,
                      ),
                      SettingsInsetNavigationRow(
                        isDark: isDark,
                        leadingIcon: CupertinoIcons.lock_shield_fill,
                        label: UITextConstants.settingsAccountSecurity,
                        onTap: () {
                          _trackSettingsClick(
                            ref,
                            'settings_account_security_open',
                            targetKey: 'settings_account_security',
                          );
                          context.push(AppRoutePaths.settingsAccountSecurity);
                        },
                      ),
                    ],
                  ],
                ),
              ),
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsPrivacySection,
                child: Column(
                  children: <Widget>[
                    SettingsInsetNavigationRow(
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
                    if (authSession.isAuthenticated) ...<Widget>[
                      SettingsInsetFormSectionDivider(
                        isDark: isDark,
                        leadingInset: SettingsSemanticConstants
                            .insetFormIconDividerLeadingInset,
                      ),
                      SettingsInsetNavigationRow(
                        isDark: isDark,
                        leadingIcon: CupertinoIcons.hand_raised_fill,
                        label: UITextConstants.settingsPrivacyPreferences,
                        onTap: () {
                          _trackSettingsClick(
                            ref,
                            'settings_privacy_open',
                            targetKey: 'settings_privacy',
                          );
                          context.push(AppRoutePaths.settingsPrivacy);
                        },
                      ),
                      SettingsInsetFormSectionDivider(
                        isDark: isDark,
                        leadingInset: SettingsSemanticConstants
                            .insetFormIconDividerLeadingInset,
                      ),
                      SettingsInsetNavigationRow(
                        isDark: isDark,
                        leadingIcon:
                            CupertinoIcons.person_crop_circle_badge_xmark,
                        label: UITextConstants.settingsBlockedUsers,
                        onTap: () {
                          _trackSettingsClick(
                            ref,
                            'settings_blocked_users_open',
                            targetKey: 'blocked_users',
                          );
                          context.push(AppRoutePaths.blockedUsers);
                        },
                      ),
                      SettingsInsetFormSectionDivider(
                        isDark: isDark,
                        leadingInset: SettingsSemanticConstants
                            .insetFormIconDividerLeadingInset,
                      ),
                      SettingsInsetNavigationRow(
                        isDark: isDark,
                        leadingIcon: CupertinoIcons.text_badge_minus,
                        label: UITextConstants.settingsBlockedKeywords,
                        onTap: () {
                          _trackSettingsClick(
                            ref,
                            'settings_blocked_keywords_open',
                            targetKey: 'blocked_keywords',
                          );
                          context.push(AppRoutePaths.blockedKeywords);
                        },
                      ),
                      SettingsInsetFormSectionDivider(
                        isDark: isDark,
                        leadingInset: SettingsSemanticConstants
                            .insetFormIconDividerLeadingInset,
                      ),
                      SettingsInsetNavigationRow(
                        isDark: isDark,
                        leadingIcon: CupertinoIcons.flag,
                        label: UITextConstants.myReportsSettingsTitle,
                        onTap: () {
                          _trackSettingsClick(
                            ref,
                            'settings_my_reports_open',
                            targetKey: 'my_reports',
                          );
                          context.push(AppRoutePaths.myReports);
                        },
                      ),
                    ],
                  ],
                ),
              ),
              if (authSession.isAuthenticated) ...<Widget>[
                _sectionGap(),
                SettingsInsetGroupedSection(
                  isDark: isDark,
                  child: SettingsInsetNavigationRow(
                    isDark: isDark,
                    leadingIcon: CupertinoIcons.bell,
                    label: UITextConstants.settingsNotificationSection,
                    onTap: () {
                      _trackSettingsClick(
                        ref,
                        'settings_notifications_open',
                        targetKey: 'settings_notifications',
                      );
                      context.push(AppRoutePaths.settingsNotifications);
                    },
                  ),
                ),
                _sectionGap(),
                SettingsInsetGroupedSection(
                  isDark: isDark,
                  child: SettingsInsetNavigationRow(
                    isDark: isDark,
                    leadingIcon: CupertinoIcons.phone,
                    label: UITextConstants.settingsCallSection,
                    onTap: () {
                      _trackSettingsClick(
                        ref,
                        'settings_calls_open',
                        targetKey: 'settings_calls',
                      );
                      context.push(AppRoutePaths.settingsCalls);
                    },
                  ),
                ),
              ],
              _sectionGap(),
              SettingsInsetGroupedSection(
                isDark: isDark,
                density: SettingsInsetSectionDensity.compact,
                header: UITextConstants.settingsAppearanceSection,
                child: Column(
                  children: <Widget>[
                    SettingsInsetNavigationRow(
                      isDark: isDark,
                      leadingIcon: CupertinoIcons.moon,
                      label: UITextConstants.settingsDarkMode,
                      trailingText: _darkModeSummary(snapshot, appearanceState),
                      onTap: () {
                        _trackSettingsClick(
                          ref,
                          'settings_appearance_open',
                          targetKey: 'settings_appearance',
                        );
                        context.push(AppRoutePaths.settingsDarkMode);
                      },
                    ),
                    if (appearanceState.lastError != null) ...<Widget>[
                      SettingsInsetFormSectionDivider(isDark: isDark),
                      SettingsInsetCenteredActionRow(
                        isDark: isDark,
                        label: UITextConstants.tryAgain,
                        onTap: () => unawaited(
                          ref
                              .read(
                                appearanceSettingsControllerProvider.notifier,
                              )
                              .refresh(),
                        ),
                      ),
                    ],
                  ],
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
    if (state.isLoading && !state.hasLoaded) {
      return UITextConstants.loading;
    }
    if (state.lastError != null && !state.hasPendingSync) {
      return UITextConstants.loadFailed;
    }
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
    const surface = AppUiSurfaces.settingsHome;
    unawaited(
      ref
          .read(analyticsProvider)
          .trackEvent(
            AnalyticsEvent(
              eventType: 'settings',
              eventName: eventName,
              properties: <String, dynamic>{
                'pageName': 'settings',
                'routeId': surface.routeId,
                'surfaceId': surface.id,
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
    const surface = AppUiSurfaces.settingsHome;
    final controller = ref.read(authSessionControllerProvider.notifier);
    await Future.wait<void>(<Future<void>>[
      ref.read(behaviorRepositoryProvider).clearPendingForLogout(),
      ref.read(appTelemetryReporterProvider).clearPendingForLogout(),
    ]);
    try {
      await ref.read(devicePushEndpointCoordinatorProvider).removeForLogout();
    } catch (error, stackTrace) {
      // mutation 保留在本地，下一次登录后继续提交；本次本地退出不能被远端故障卡死。
      unawaited(
        AppExceptionTelemetryService.instance.recordHandledException(
          source: 'settings.logout.remove_push_endpoint',
          error: error,
          stackTrace: stackTrace,
          pageId: 'settings',
          pageName: 'settings',
          surfaceId: surface.id,
          routeId: surface.routeId,
          operationId: AppCloudOperationIds
              .userDeviceRegistrationRemoveDevicePushEndpoint,
        ),
      );
    }
    if (clearLocalCredential) {
      final session = ref.read(authSessionControllerProvider);
      try {
        await ref
            .read(accountSessionLifecycleCommandWriterProvider)
            .logout(
              LogoutCommand(
                refreshToken: session.refreshToken,
                deviceId: session.installId,
              ),
            );
      } catch (error, stackTrace) {
        // 本地退出优先，远端吊销失败由下次 refresh 兜底；失败必须可观测。
        unawaited(
          AppExceptionTelemetryService.instance.recordHandledException(
            source: 'settings.logout.remote_revoke',
            error: error,
            stackTrace: stackTrace,
            pageId: 'settings',
            pageName: 'settings',
            surfaceId: surface.id,
            routeId: surface.routeId,
            operationId: AppCloudOperationIds.userAccountSessionLogout,
          ),
        );
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
      dismissPolicy: LoginDismissPolicy.safeFallback,
    );
  }
}

enum _LogoutChoice { soft, hard }
