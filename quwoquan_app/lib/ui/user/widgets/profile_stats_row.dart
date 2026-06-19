import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/cloud/services/user/profile_homepage_models.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';

class ProfileStatsRow extends StatelessWidget {
  const ProfileStatsRow({
    super.key,
    required this.isDark,
    required this.profile,
    this.onStatTap,
  });

  final bool isDark;
  final SubAccountProfileViewData? profile;
  final void Function(String type)? onStatTap;

  String _formatCount(int count) {
    return formatCompactActionCount(count);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final subject = profile;

    final items = [
      _StatItem(
        value: _formatCount(subject?.followerCount ?? 0),
        label: UITextConstants.profileStatFollowers,
        type: 'fans',
      ),
      _StatItem(
        value: _formatCount(subject?.followingCount ?? 0),
        label: UITextConstants.follow,
        type: 'following',
      ),
      _StatItem(
        value: _formatCount(subject?.likeCount ?? 0),
        label: UITextConstants.circleLikes,
        type: 'likes',
      ),
      _StatItem(
        value: _formatCount(subject?.circleCount ?? 0),
        label: UITextConstants.contactsTabCircles,
        type: 'circles',
      ),
    ];

    return Wrap(
      key: const ValueKey<String>('profile-stats-inline-row'),
      spacing: AppSpacing.intraGroupXs,
      runSpacing: AppSpacing.intraGroupXs,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: <Widget>[
        for (var i = 0; i < items.length; i += 1) ...<Widget>[
          _buildInlineStat(items[i], fg, fgSecondary),
          if (i != items.length - 1)
            Text(
              '·',
              style: TextStyle(
                fontSize: AppTypography.iosSubheadline,
                fontWeight: AppTypography.regular,
                color: fg.withValues(alpha: 0.86),
              ),
            ),
        ],
      ],
    );
  }
}

extension on ProfileStatsRow {
  Widget _buildInlineStat(_StatItem item, Color fg, Color fgSecondary) {
    final content = Row(
      mainAxisSize: MainAxisSize.min,
      children: <Widget>[
        Text(
          item.value,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosSubheadline,
            fontWeight: AppTypography.regular,
            color: fg.withValues(alpha: 0.9),
            letterSpacing: -0.08,
          ),
        ),
        SizedBox(width: AppSpacing.intraGroupXs / 2),
        Text(
          item.label,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: TextStyle(
            fontSize: AppTypography.iosFootnote,
            fontWeight: AppTypography.regular,
            color: fgSecondary,
          ),
        ),
      ],
    );
    if (onStatTap == null || item.type.isEmpty) {
      return content;
    }
    return CupertinoButton(
      padding: EdgeInsets.zero,
      minimumSize: Size.square(AppSpacing.minInteractiveSize),
      onPressed: () => onStatTap!(item.type),
      child: content,
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
