import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/runtime/shell/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/design_system/feedback/app_request_feedback.dart';
import 'package:quwoquan_app/design_system/feedback/error_states/app_error_states.dart';
import 'package:quwoquan_app/design_system/forms/settings/settings_inset_form_page.dart';
import 'package:quwoquan_app/design_system/layout/web_page_max_width_frame.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/errors/runtime_error_display.dart';
import 'package:quwoquan_app/runtime/errors/ui_error_semantics.dart';
import 'package:quwoquan_app/service/user_service/account/user_settings/application/user_settings_provider.dart';

class SettingsCallsPage extends ConsumerStatefulWidget {
  const SettingsCallsPage({super.key});

  @override
  ConsumerState<SettingsCallsPage> createState() => _SettingsCallsPageState();
}

class _SettingsCallsPageState extends ConsumerState<SettingsCallsPage> {
  static const String _defaultRingtone = 'official.default';
  static const String _classicRingtone = 'official.classic';
  static const String _softRingtone = 'official.soft';

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
    final settings = state.call;
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: SettingsText.settingsCallSection,
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
                      header: SettingsText.settingsCallRingtone,
                      child: Column(
                        children: <Widget>[
                          _ringtoneRow(
                            isDark: isDark,
                            label: SettingsText.settingsCallRingtoneDefault,
                            ringtoneId: _defaultRingtone,
                            selected: settings.defaultIncomingCallRingtoneId,
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          _ringtoneRow(
                            isDark: isDark,
                            label: SettingsText.settingsCallRingtoneClassic,
                            ringtoneId: _classicRingtone,
                            selected: settings.defaultIncomingCallRingtoneId,
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          _ringtoneRow(
                            isDark: isDark,
                            label: SettingsText.settingsCallRingtoneSoft,
                            ringtoneId: _softRingtone,
                            selected: settings.defaultIncomingCallRingtoneId,
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
                      child: Column(
                        children: <Widget>[
                          SettingsInsetSwitchRow(
                            isDark: isDark,
                            label: SettingsText
                                .settingsAllowCallerRingtoneOverride,
                            subtitle: SettingsText
                                .settingsAllowCallerRingtoneOverrideSubtitle,
                            value: settings.allowCallerRingtoneOverride,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setAllowCallerRingtoneOverride(value),
                              ),
                            ),
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          SettingsInsetSwitchRow(
                            isDark: isDark,
                            label: SettingsText.settingsEnableCallVibration,
                            value: settings.enableCallVibration,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setEnableCallVibration(value),
                              ),
                            ),
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          SettingsInsetSwitchRow(
                            isDark: isDark,
                            label: SettingsText.settingsEnableGroupCallRing,
                            subtitle: SettingsText
                                .settingsEnableGroupCallRingSubtitle,
                            value: settings.enableGroupCallRing,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setEnableGroupCallRing(value),
                              ),
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

  Widget _ringtoneRow({
    required bool isDark,
    required String label,
    required String ringtoneId,
    required String? selected,
  }) => SettingsInsetChoiceRow(
    isDark: isDark,
    label: label,
    isSelected: selected == ringtoneId,
    onTap: () => unawaited(
      _update(
        ref
            .read(userSettingsSectionsProvider.notifier)
            .setDefaultRingtone(ringtoneId),
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
        error: state.rawError ?? StateError('call_settings_unavailable'),
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
          error: error ?? StateError('call_settings_update_failed'),
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
