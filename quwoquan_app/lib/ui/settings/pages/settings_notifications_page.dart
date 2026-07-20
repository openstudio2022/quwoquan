import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/widgets/app_toast.dart';
import 'package:quwoquan_app/ui/settings/providers/user_settings_provider.dart';

class SettingsNotificationsPage extends ConsumerStatefulWidget {
  const SettingsNotificationsPage({super.key});

  @override
  ConsumerState<SettingsNotificationsPage> createState() =>
      _SettingsNotificationsPageState();
}

class _SettingsNotificationsPageState
    extends ConsumerState<SettingsNotificationsPage> {
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
    final settings = state.notification;
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.settingsNotificationSection,
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
                            label: UITextConstants.settingsEnablePush,
                            subtitle:
                                UITextConstants.settingsEnablePushSubtitle,
                            value: settings.enablePush,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setEnablePush(value),
                              ),
                            ),
                          ),
                          SettingsInsetFormSectionDivider(isDark: isDark),
                          SettingsInsetSwitchRow(
                            isDark: isDark,
                            label: UITextConstants.settingsEnableMarketing,
                            subtitle:
                                UITextConstants.settingsEnableMarketingSubtitle,
                            value: settings.enableMarketing,
                            onChanged: (value) => unawaited(
                              _update(
                                ref
                                    .read(userSettingsSectionsProvider.notifier)
                                    .setEnableMarketing(value),
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

  Widget _buildUnavailable(UserSettingsSectionsState state) {
    if (state.isLoading) {
      return const Center(child: CupertinoActivityIndicator());
    }
    return AppPageErrorState(
      semantic: UiErrorSemanticResolver.resolve(
        context,
        error:
            state.rawError ?? StateError('notification_settings_unavailable'),
        category: UiErrorCategory.pageLoad,
        scope: UiErrorScope.page,
      ),
      onAction: (action) async {
        if (action.type == UiErrorActionType.retry) {
          await ref.read(userSettingsSectionsProvider.notifier).load();
        }
      },
    );
  }

  Future<void> _update(Future<bool> operation) async {
    if (!await operation && mounted) {
      AppToast.show(context, UITextConstants.settingsUpdateFailedToast);
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
