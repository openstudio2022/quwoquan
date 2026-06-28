import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum SettingsPermissionLayer { contacts, circles, entities }

class SettingsPermissionsPage extends ConsumerWidget {
  const SettingsPermissionsPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.settingsPermissionManagement,
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
                header: UITextConstants.settingsPermissionLayerSection,
                child: Column(
                  children: <Widget>[
                    for (
                      var i = 0;
                      i < SettingsPermissionLayer.values.length;
                      i += 1
                    ) ...<Widget>[
                      _PermissionLayerRow(
                        isDark: isDark,
                        layer: SettingsPermissionLayer.values[i],
                      ),
                      if (i != SettingsPermissionLayer.values.length - 1)
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
}

class _PermissionLayerRow extends StatelessWidget {
  const _PermissionLayerRow({required this.isDark, required this.layer});

  final bool isDark;
  final SettingsPermissionLayer layer;

  @override
  Widget build(BuildContext context) {
    return SettingsInsetFormRow(
      isDark: isDark,
      label: switch (layer) {
        SettingsPermissionLayer.contacts =>
          UITextConstants.settingsContactsPermission,
        SettingsPermissionLayer.circles =>
          UITextConstants.settingsCirclesPermission,
        SettingsPermissionLayer.entities =>
          UITextConstants.settingsEntitiesPermission,
      },
      trailing: SettingsInsetTrailingText(
        isDark: isDark,
        value: UITextConstants.settingsPermissionReserved,
      ),
    );
  }
}
