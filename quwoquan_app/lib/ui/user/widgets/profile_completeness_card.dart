import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class ProfileCompletenessCard extends StatelessWidget {
  const ProfileCompletenessCard({
    super.key,
    required this.percent,
    required this.missingItems,
    required this.onTap,
  });

  final int percent;
  final List<String> missingItems;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final resolvedPercent = percent.clamp(0, 100);
    if (resolvedPercent >= 100) {
      return const SizedBox.shrink();
    }
    return CupertinoButton(
      key: const ValueKey<String>('profile-completeness-card'),
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: onTap,
      child: Container(
        width: double.infinity,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.containerMd,
          vertical: AppSpacing.containerSm,
        ),
        decoration: BoxDecoration(
          color: AppColors.iosAccent(context).withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(AppSpacing.largeBorderRadius),
          border: Border.all(
            color: AppColors.iosAccent(context).withValues(alpha: 0.12),
            width: AppSpacing.hairline,
          ),
        ),
        child: Row(
          children: <Widget>[
            Icon(
              CupertinoIcons.sparkles,
              size: AppSpacing.iconSmall,
              color: AppColors.iosAccent(context),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: <Widget>[
                  Text(
                    UITextConstants.profileCompletenessPrompt(resolvedPercent),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosSubheadline,
                      fontWeight: AppTypography.regular,
                      color: AppColors.iosAccent(context),
                    ),
                  ),
                  SizedBox(height: AppSpacing.intraGroupXs / 2),
                  Text(
                    _subtitle,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: TextStyle(
                      fontSize: AppTypography.iosCaption1,
                      color: AppColors.iosSecondaryLabel(context),
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(width: AppSpacing.intraGroupSm),
            Icon(
              CupertinoIcons.chevron_forward,
              size: AppSpacing.iconXSmall,
              color: AppColors.iosTertiaryLabel(context),
            ),
          ],
        ),
      ),
    );
  }

  String get _subtitle {
    final labels = missingItems
        .map(_labelForMissingItem)
        .where((label) => label.isNotEmpty);
    if (labels.isEmpty) {
      return UITextConstants.profileCompletenessSubtitle;
    }
    return labels.join(' · ');
  }

  static String _labelForMissingItem(String item) {
    switch (item) {
      case 'avatar':
        return UITextConstants.profileCompletenessAvatar;
      case 'tags':
        return UITextConstants.profileCompletenessTags;
      case 'circles':
        return UITextConstants.profileCompletenessCircles;
      case 'entities':
        return UITextConstants.profileCompletenessEntities;
      default:
        return item;
    }
  }
}
