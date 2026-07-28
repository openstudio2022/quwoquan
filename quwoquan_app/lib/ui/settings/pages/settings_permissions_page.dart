import 'dart:async';

import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/services/app_permission_coordinator.dart';

class SettingsPermissionsPage extends ConsumerWidget {
  const SettingsPermissionsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    final contactsAvailable = ref.watch(platformCapabilitiesProvider).contacts;
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: SettingsText.settingsPermissionManagement,
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
                header: SettingsText.settingsPermissionLayerSection,
                child: _ContactsPermissionRow(
                  isDark: isDark,
                  available: contactsAvailable,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _ContactsPermissionRow extends StatelessWidget {
  const _ContactsPermissionRow({required this.isDark, required this.available});

  final bool isDark;
  final bool available;

  @override
  Widget build(BuildContext context) {
    return SettingsInsetFormRow(
      isDark: isDark,
      label: SettingsText.settingsContactsPermission,
      trailing: SettingsInsetTrailingText(
        isDark: isDark,
        value: available
            ? FoundationText.openSettings
            : SettingsText.settingsPermissionUnavailable,
      ),
      onTap: available
          ? () => unawaited(
              AppPermissionCoordinator.current.openSettings(
                AppPermissionKind.contacts,
              ),
            )
          : null,
    );
  }
}
