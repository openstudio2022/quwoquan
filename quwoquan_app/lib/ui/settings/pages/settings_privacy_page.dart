import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/settings/providers/user_settings_provider.dart';
import 'package:quwoquan_cloud_contracts/quwoquan_cloud_contracts.dart'
    show ProfileVisibility;

class SettingsPrivacyPage extends ConsumerStatefulWidget {
  const SettingsPrivacyPage({super.key});

  @override
  ConsumerState<SettingsPrivacyPage> createState() =>
      _SettingsPrivacyPageState();
}

class _SettingsPrivacyPageState extends ConsumerState<SettingsPrivacyPage> {
  @override
  void initState() {
    super.initState();
    Future<void>.microtask(
      () => ref.read(userSettingsSectionsProvider.notifier).load(),
    );
  }

  @override
  Widget build(BuildContext context) {
    final isDark = ref.watch(isDarkProvider);
    final state = ref.watch(userSettingsSectionsProvider);
    final settings = state.privacy;
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: SettingsText.settingsPrivacyPreferences,
      onBack: () => _goBack(context),
      body: WebPageMaxWidthFrame(
        child: SafeArea(
          bottom: false,
          child: settings == null
              ? _buildUnavailable(state)
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
                    SettingsInsetGroupedSection(
                      isDark: isDark,
                      child: Column(
                        children: <Widget>[
                          SettingsInsetSwitchRow(
                            isDark: isDark,
                            label: SettingsText.settingsAllowStrangerMessage,
                            value: settings.allowStrangerMsg,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setAllowStrangerMsg(value),
                              ),
                            ),
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          SettingsInsetSwitchRow(
                            isDark: isDark,
                            label: SettingsText.settingsAssistantEnabled,
                            value: settings.assistantEnabled,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setAssistantEnabled(value),
                              ),
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
                      header: SettingsText.settingsProfileVisibility,
                      child: Column(
                        children: <Widget>[
                          _visibilityRow(
                            isDark: isDark,
                            label: SettingsText.settingsProfileVisibilityPublic,
                            value: ProfileVisibility.public,
                            selected: ProfileVisibility.fromWire(
                              settings.profileVisibility,
                              'PrivacySettingsView.profileVisibility',
                            ),
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          _visibilityRow(
                            isDark: isDark,
                            label:
                                SettingsText.settingsProfileVisibilityPrivate,
                            value: ProfileVisibility.privateProfile,
                            selected: ProfileVisibility.fromWire(
                              settings.profileVisibility,
                              'PrivacySettingsView.profileVisibility',
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

  Widget _visibilityRow({
    required bool isDark,
    required String label,
    required ProfileVisibility value,
    required ProfileVisibility selected,
  }) => SettingsInsetChoiceRow(
    isDark: isDark,
    label: label,
    isSelected: selected == value,
    onTap: () => unawaited(
      _update(
        ref
            .read(userSettingsSectionsProvider.notifier)
            .setProfileVisibility(value),
      ),
    ),
  );

  Widget _buildUnavailable(UserSettingsSectionsState state) {
    if (state.isLoading) {
      return AppRequestFeedback.section();
    }
    return AppPageErrorState(
      semantic: UiErrorSemanticResolver.resolve(
        context,
        error: state.rawError ?? StateError('privacy_settings_unavailable'),
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      ),
      onRecovery: (action) async {
        if (action.type == UiErrorActionType.retry) {
          await ref.read(userSettingsSectionsProvider.notifier).load();
          return ref.read(userSettingsSectionsProvider).rawError == null
              ? UiRecoveryOutcome.recovered
              : UiRecoveryOutcome.stillBlocked;
        }
        return UiRecoveryOutcome.cancelled;
      },
    );
  }

  Future<void> _update(Future<bool> operation) async {
    if (!await operation && mounted) {
      final error = ref.read(userSettingsSectionsProvider).rawError;
      await AppActionErrorFeedback.show(
        context,
        semantic: runtimeErrorSemantic(
          context,
          error: error ?? StateError('privacy_settings_update_failed'),
          category: UiErrorCategory.backgroundAction,
          scope: UiErrorScope.dialog,
          allowRetry: false,
          presentation: UiErrorPresentation.actionDialog,
        ),
      );
    }
  }

  void _goBack(BuildContext context) {
    if (context.canPop()) {
      context.pop();
    } else {
      context.go(AppRoutePaths.settings);
    }
  }
}
