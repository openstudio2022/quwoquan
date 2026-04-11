import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/ui/user/widgets/profile_ios_components.dart';

class ProfileStatsRow extends StatelessWidget {
  const ProfileStatsRow({
    super.key,
    required this.isDark,
    required this.profile,
    this.onStatTap,
  });

  final bool isDark;
  final ProfileSubjectViewData? profile;
  final void Function(String type)? onStatTap;

  String _formatCount(int count) {
    return formatCompactActionCount(count);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final separator = AppColors.iosSeparator(
      context,
    ).withValues(alpha: isDark ? 0.28 : 0.18);
    final subject = profile;

    final items = [
      _StatItem(
        value: _formatCount(subject?.circleCount ?? 0),
        label: UITextConstants.contactsTabCircles,
        type: 'circles',
      ),
      _StatItem(
        value: _formatCount(subject?.followingCount ?? 0),
        label: UITextConstants.follow,
        type: 'following',
      ),
      _StatItem(
        value: _formatCount(subject?.followerCount ?? 0),
        label: UITextConstants.circleFans,
        type: 'fans',
      ),
    ];

    return ProfileIosSectionCard(
      padding: EdgeInsets.symmetric(vertical: AppSpacing.containerSm),
      backgroundColor: AppColors.iosProfileSurface(context),
      borderColor: AppColors.iosSeparator(
        context,
      ).withValues(alpha: isDark ? 0.24 : 0.1),
      child: Row(
        children: <Widget>[
          for (var i = 0; i < items.length; i += 1) ...<Widget>[
            Expanded(
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                onPressed: onStatTap != null
                    ? () => onStatTap!(items[i].type)
                    : null,
                child: Padding(
                  padding: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupXs,
                  ),
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: <Widget>[
                      Text(
                        items[i].value,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: AppTypography.iosTitle3,
                          fontWeight: AppTypography.semiBold,
                          color: fg,
                          letterSpacing: -0.32,
                        ),
                      ),
                      SizedBox(height: AppSpacing.intraGroupXs / 2),
                      Text(
                        items[i].label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        textAlign: TextAlign.center,
                        style: TextStyle(
                          fontSize: AppTypography.iosFootnote,
                          fontWeight: AppTypography.medium,
                          color: fgSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),
            if (i != items.length - 1)
              Container(
                width: AppSpacing.hairline,
                height: AppSpacing.buttonHeightSm,
                color: separator,
              ),
          ],
        ],
      ),
    );
  }
}

class _StatItem {
  const _StatItem({
    required this.value,
    required this.label,
    required this.type,
  });
  final String value;
  final String label;
  final String type;
}
