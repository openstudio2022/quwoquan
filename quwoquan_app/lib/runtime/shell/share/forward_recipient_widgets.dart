import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/avatar/rounded_square_avatar.dart';
import 'package:quwoquan_app/design_system/search/embedded/inset_grouped_member_list_card.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/runtime/di/share/forward_share_models.dart';

class ForwardRecipientListCard extends StatelessWidget {
  const ForwardRecipientListCard({
    super.key,
    required this.isDark,
    required this.recipients,
    required this.onRecipientTap,
  });

  final bool isDark;
  final List<AppForwardRecipient> recipients;
  final ValueChanged<AppForwardRecipient> onRecipientTap;

  @override
  Widget build(BuildContext context) {
    return InsetGroupedMemberListCard(
      isDark: isDark,
      dividerKind: MemberListDividerInsetKind.navigate,
      tileWidgets: [
        for (final recipient in recipients)
          ForwardRecipientTile(
            isDark: isDark,
            recipient: recipient,
            onTap: () => onRecipientTap(recipient),
          ),
      ],
    );
  }
}

class ForwardRecipientTile extends StatelessWidget {
  const ForwardRecipientTile({
    super.key,
    required this.isDark,
    required this.recipient,
    required this.onTap,
    this.showChevron = false,
  });

  final bool isDark;
  final AppForwardRecipient recipient;
  final VoidCallback onTap;
  final bool showChevron;

  @override
  Widget build(BuildContext context) {
    final fgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return CupertinoButton(
      padding: EdgeInsets.zero,
      onPressed: onTap,
      child: Padding(
        padding: EdgeInsets.symmetric(
          horizontal: SettingsSemanticConstants.blockHorizontalPadding,
          vertical: AppSpacing.sm,
        ),
        child: Row(
          children: [
            RoundedSquareAvatar(
              size: AppSpacing.largeButtonSize,
              imageUrl: recipient.avatarUrl,
              name: recipient.title,
              backgroundColor: SettingsSemanticConstants.blockBackground(
                isDark,
              ),
            ),
            SizedBox(width: AppSpacing.interGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Text(
                    recipient.title,
                    style: TextStyle(
                      fontSize: AppTypography.lg,
                      color: fgPrimary,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                  if (recipient.displaySubtitle.isNotEmpty) ...[
                    SizedBox(height: AppSpacing.intraGroupXs),
                    Text(
                      recipient.displaySubtitle,
                      style: TextStyle(
                        fontSize: AppTypography.sm,
                        color: fgSecondary,
                      ),
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ],
                ],
              ),
            ),
            if (showChevron) ...[
              SizedBox(width: AppSpacing.intraGroupSm),
              Icon(
                CupertinoIcons.chevron_forward,
                size: AppSpacing.iconMedium,
                color: SettingsSemanticConstants.selectionChevronColor(isDark),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class ForwardRecentRecipientItem extends StatelessWidget {
  const ForwardRecentRecipientItem({
    super.key,
    required this.isDark,
    required this.recipient,
    required this.onTap,
  });

  final bool isDark;
  final AppForwardRecipient recipient;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    return SizedBox(
      width: AppSpacing.avatarUserXl,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        onPressed: onTap,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            RoundedSquareAvatar(
              size: AppSpacing.avatarUserLg,
              imageUrl: recipient.avatarUrl,
              name: recipient.title,
              backgroundColor: SettingsSemanticConstants.blockBackground(
                isDark,
              ),
            ),
            SizedBox(height: AppSpacing.intraGroupXs),
            Text(
              recipient.title,
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: AppTypography.iosCaption2,
                color: fgSecondary,
              ),
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
      ),
    );
  }
}

class ForwardRecentRecipientRail extends StatelessWidget {
  const ForwardRecentRecipientRail({
    super.key,
    required this.isDark,
    required this.recipients,
    required this.onRecipientTap,
    this.maxCount,
  });

  final bool isDark;
  final List<AppForwardRecipient> recipients;
  final ValueChanged<AppForwardRecipient> onRecipientTap;
  final int? maxCount;

  @override
  Widget build(BuildContext context) {
    final visibleRecipients = maxCount == null
        ? recipients
        : recipients.take(maxCount!).toList(growable: false);
    return SizedBox(
      height: AppSpacing.avatarUserXl + AppSpacing.containerLg,
      child: SingleChildScrollView(
        scrollDirection: Axis.horizontal,
        child: Row(
          children: <Widget>[
            for (var index = 0; index < visibleRecipients.length; index++)
              Padding(
                padding: EdgeInsets.only(
                  right: index == visibleRecipients.length - 1
                      ? 0
                      : AppSpacing.containerMd,
                ),
                child: ForwardRecentRecipientItem(
                  isDark: isDark,
                  recipient: visibleRecipients[index],
                  onTap: () => onRecipientTap(visibleRecipients[index]),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class ForwardSectionHeader extends StatelessWidget {
  const ForwardSectionHeader({
    super.key,
    required this.isDark,
    required this.title,
  });

  final bool isDark;
  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: TextStyle(
        fontSize: AppTypography.iosFootnote,
        fontWeight: AppTypography.semiBold,
        color: AppColorsFunctional.getColor(
          isDark,
          ColorType.foregroundPrimary,
        ),
      ),
    );
  }
}
