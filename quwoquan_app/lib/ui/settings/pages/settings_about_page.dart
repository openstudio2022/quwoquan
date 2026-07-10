import 'package:flutter/cupertino.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class SettingsAboutPage extends ConsumerWidget {
  const SettingsAboutPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final isDark = ref.watch(isDarkProvider);
    return SettingsInsetFormPageScaffold(
      isDark: isDark,
      title: UITextConstants.settingsAboutQuwoquan,
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
          child: FutureBuilder<PackageInfo>(
            future: PackageInfo.fromPlatform(),
            builder: (context, snapshot) {
              final version =
                  snapshot.data?.version ??
                  UITextConstants.settingsAboutDefaultVersion;
              return ListView(
                padding: EdgeInsets.only(
                  left:
                      SettingsSemanticConstants.insetFormListHorizontalPadding,
                  right:
                      SettingsSemanticConstants.insetFormListHorizontalPadding,
                  top: AppSpacing.intraGroupSm,
                  bottom: AppSpacing.xl,
                ),
                children: <Widget>[
                  SettingsInsetGroupedSection(
                    isDark: isDark,
                    density: SettingsInsetSectionDensity.compact,
                    child: Column(
                      children: <Widget>[
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.loginBrandName,
                          trailing: SettingsInsetTrailingText(
                            isDark: isDark,
                            value: UITextConstants.settingsAppOfficialName,
                          ),
                        ),
                        SettingsInsetFormSectionDivider(isDark: isDark),
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.settingsVersion,
                          trailing: SettingsInsetTrailingText(
                            isDark: isDark,
                            value: UITextConstants.settingsVersionValue(
                              version,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  SettingsInsetGroupedSection(
                    isDark: isDark,
                    density: SettingsInsetSectionDensity.compact,
                    child: Column(
                      children: <Widget>[
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.userAgreement,
                          trailing: SettingsInsetChevron(isDark: isDark),
                          onTap: () {
                            context.push(AppRoutePaths.legalUserAgreement);
                          },
                        ),
                        SettingsInsetFormSectionDivider(isDark: isDark),
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.privacyPolicy,
                          trailing: SettingsInsetChevron(isDark: isDark),
                          onTap: () {
                            context.push(AppRoutePaths.legalPrivacyPolicy);
                          },
                        ),
                        SettingsInsetFormSectionDivider(isDark: isDark),
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.permissionsStatement,
                          trailing: SettingsInsetChevron(isDark: isDark),
                          onTap: () {
                            context.push(AppRoutePaths.legalPermissions);
                          },
                        ),
                        SettingsInsetFormSectionDivider(isDark: isDark),
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.thirdPartySdkList,
                          trailing: SettingsInsetChevron(isDark: isDark),
                          onTap: () {
                            context.push(AppRoutePaths.legalThirdPartySdkList);
                          },
                        ),
                      ],
                    ),
                  ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}
