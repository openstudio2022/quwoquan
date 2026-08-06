import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/service/content_service/content/profile_interaction_activity_view/application/public/share_interaction_models.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';

class ShareEmptyState extends StatelessWidget {
  const ShareEmptyState({
    super.key,
    required this.direction,
    required this.onAction,
  });

  final ShareInteractionDirection direction;
  final VoidCallback onAction;

  @override
  Widget build(BuildContext context) {
    final isReceived = direction == ShareInteractionDirection.received;
    final isDark = CupertinoTheme.brightnessOf(context) == Brightness.dark;
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerLg,
        vertical: AppSpacing.interGroupXl,
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: <Widget>[
          Icon(
            CupertinoIcons.arrowshape_turn_up_right,
            size: AppSpacing.iconLarge,
            color: AppColors.iosSecondaryLabel(context),
          ),
          SizedBox(height: AppSpacing.md),
          Text(
            isReceived
                ? ProfileText.profileShareReceivedEmptyTitle
                : ProfileText.profileShareInitiatedEmptyTitle,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosBody,
              color: AppColorsFunctional.getColor(
                isDark,
                ColorType.foregroundPrimary,
              ),
            ),
          ),
          SizedBox(height: AppSpacing.xs),
          Text(
            isReceived
                ? ProfileText.profileShareReceivedEmptyDescription
                : ProfileText.profileShareInitiatedEmptyDescription,
            textAlign: TextAlign.center,
            style: TextStyle(
              fontSize: AppTypography.iosFootnote,
              color: AppColors.iosSecondaryLabel(context),
            ),
          ),
          SizedBox(height: AppSpacing.md),
          CupertinoButton(
            minimumSize: const Size(
              AppSpacing.minInteractiveSize,
              AppSpacing.minInteractiveSize,
            ),
            padding: EdgeInsets.symmetric(horizontal: AppSpacing.containerMd),
            color: AppColors.iosAccent(context),
            borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
            onPressed: onAction,
            child: Text(
              isReceived
                  ? ProfileText.profileShareReceivedEmptyAction
                  : ProfileText.profileShareInitiatedEmptyAction,
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                color: AppColors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
