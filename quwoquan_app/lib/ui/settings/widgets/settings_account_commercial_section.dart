import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/app/navigation/generated/app_route_paths.g.dart';
import 'package:quwoquan_app/components/settings_form/settings_inset_form_page.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/ui/settings/widgets/settings_commercial_account_text.dart';

class SettingsAccountCommercialSection extends StatelessWidget {
  const SettingsAccountCommercialSection({
    super.key,
    required this.isDark,
    required this.isAuthenticated,
  });

  final bool isDark;
  final bool isAuthenticated;

  @override
  Widget build(BuildContext context) {
    return SettingsInsetGroupedSection(
      isDark: isDark,
      header: SettingsCommercialAccountText.sectionTitle,
      child: Column(
        children: <Widget>[
          if (isAuthenticated) ...<Widget>[
            _CommercialAccountRow(
              icon: CupertinoIcons.person_crop_circle_badge_checkmark,
              label: SettingsCommercialAccountText.credentials,
              trailingText: SettingsCommercialAccountText.credentialsReady,
              message: SettingsCommercialAccountText.credentialsMessage,
            ),
            SettingsInsetFormSectionDivider(isDark: isDark),
            _CommercialAccountRow(
              icon: CupertinoIcons.device_phone_portrait,
              label: SettingsCommercialAccountText.devices,
              trailingText: SettingsCommercialAccountText.devicesBlocked,
              message: SettingsCommercialAccountText.devicesMessage,
            ),
            SettingsInsetFormSectionDivider(isDark: isDark),
            _CommercialAccountRow(
              icon: CupertinoIcons.lock_shield,
              label: SettingsCommercialAccountText.delete,
              trailingText: SettingsCommercialAccountText.deleteBlocked,
              message: SettingsCommercialAccountText.deleteMessage,
            ),
            SettingsInsetFormSectionDivider(isDark: isDark),
            _CommercialAccountRow(
              icon: CupertinoIcons.doc_text,
              label: SettingsCommercialAccountText.dataRights,
              trailingText: SettingsCommercialAccountText.dataRightsBlocked,
              message: SettingsCommercialAccountText.dataRightsMessage,
            ),
          ] else ...<Widget>[
            _CommercialSettingsRow(
              icon: CupertinoIcons.lock_shield,
              label: SettingsCommercialAccountText.loginRequired,
              onTap: () => openLoginPage(
                context,
                reasonName: AuthGateReason.settingsAccount.name,
                redirect: AppRoutePaths.settings,
                dismissFallback: AppRoutePaths.settings,
              ),
            ),
          ],
        ],
      ),
    );
  }
}

class _CommercialAccountRow extends StatelessWidget {
  const _CommercialAccountRow({
    required this.icon,
    required this.label,
    required this.trailingText,
    required this.message,
  });

  final IconData icon;
  final String label;
  final String trailingText;
  final String message;

  @override
  Widget build(BuildContext context) {
    return _CommercialSettingsRow(
      icon: icon,
      label: label,
      trailingText: trailingText,
      onTap: () =>
          _showCommercialAccountNotice(context, title: label, message: message),
    );
  }
}

class _CommercialSettingsRow extends StatelessWidget {
  const _CommercialSettingsRow({
    required this.icon,
    required this.label,
    required this.onTap,
    this.trailingText,
  });

  final IconData icon;
  final String label;
  final String? trailingText;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final titleStyle = CupertinoTheme.of(context).textTheme.textStyle.copyWith(
      fontSize: AppTypography.iosSubheadline,
      fontWeight: AppTypography.regular,
    );
    final accent = AppColors.iosAccent(context);

    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Container(
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.md,
          vertical: AppSpacing.fourteen,
        ),
        child: Row(
          children: <Widget>[
            Container(
              width: AppSpacing.buttonHeightSm,
              height: AppSpacing.buttonHeightSm,
              decoration: BoxDecoration(
                color: AppColors.iosTintedFill(context),
                borderRadius: BorderRadius.circular(
                  AppSpacing.largeBorderRadius,
                ),
              ),
              child: Icon(icon, size: AppSpacing.iconSmall, color: accent),
            ),
            SizedBox(width: AppSpacing.intraGroupLg),
            Expanded(
              child: Text(label, style: titleStyle, textAlign: TextAlign.left),
            ),
            if (trailingText != null) ...<Widget>[
              Flexible(
                child: Text(
                  trailingText!,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: CupertinoTheme.of(context).textTheme.textStyle
                      .copyWith(
                        fontSize: AppTypography.smPlus,
                        color: CupertinoColors.secondaryLabel.resolveFrom(
                          context,
                        ),
                      ),
                ),
              ),
              SizedBox(width: AppSpacing.sm),
            ],
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconSmall,
              color: CupertinoColors.systemGrey2,
            ),
          ],
        ),
      ),
    );
  }
}

void _showCommercialAccountNotice(
  BuildContext context, {
  required String title,
  required String message,
}) {
  showCupertinoDialog<void>(
    context: context,
    builder: (ctx) => CupertinoAlertDialog(
      title: Text(title),
      content: Text(message),
      actions: <Widget>[
        CupertinoDialogAction(
          isDefaultAction: true,
          onPressed: () => Navigator.of(ctx).pop(),
          child: const Text(UITextConstants.ok),
        ),
      ],
    ),
  );
}
