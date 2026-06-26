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
                    child: Column(
                      children: <Widget>[
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.loginBrandName,
                          trailing: Text(
                            UITextConstants.settingsAppOfficialName,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.right,
                            style: TextStyle(
                              fontSize: AppTypography.iosSubheadline,
                              color: SettingsSemanticConstants.secondaryColor(
                                isDark,
                              ),
                            ),
                          ),
                        ),
                        SettingsInsetFormSectionDivider(isDark: isDark),
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.settingsVersion,
                          trailing: Text(
                            UITextConstants.settingsVersionValue(version),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            textAlign: TextAlign.right,
                            style: TextStyle(
                              fontSize: AppTypography.iosSubheadline,
                              color: SettingsSemanticConstants.secondaryColor(
                                isDark,
                              ),
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupSm),
                  SettingsInsetGroupedSection(
                    isDark: isDark,
                    child: Column(
                      children: <Widget>[
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.userAgreement,
                          trailing: Icon(
                            CupertinoIcons.chevron_forward,
                            size: AppSpacing.iconSmall,
                            color: SettingsSemanticConstants.secondaryColor(
                              isDark,
                            ),
                          ),
                          onTap: () {
                            context.push(AppRoutePaths.legalUserAgreement);
                          },
                        ),
                        SettingsInsetFormSectionDivider(isDark: isDark),
                        SettingsInsetFormRow(
                          isDark: isDark,
                          label: UITextConstants.privacyPolicy,
                          trailing: Icon(
                            CupertinoIcons.chevron_forward,
                            size: AppSpacing.iconSmall,
                            color: SettingsSemanticConstants.secondaryColor(
                              isDark,
                            ),
                          ),
                          onTap: () {
                            context.push(AppRoutePaths.legalPrivacyPolicy);
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
