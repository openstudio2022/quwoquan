import 'package:flutter/material.dart';
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
  final ProfileSubjectViewData? profile;
  final void Function(String type)? onStatTap;

  String _formatCount(dynamic count) {
    if (count == null) return '0';
    final n = count is int ? count : int.tryParse(count.toString()) ?? 0;
    return formatCompactActionCount(n);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    final subject = profile;

    final items = [
      _StatItem(value: _formatCount(subject?.circleCount), label: UITextConstants.contactsTabCircles, type: 'circles'),
      _StatItem(value: _formatCount(subject?.followingCount), label: UITextConstants.follow, type: 'following'),
      _StatItem(value: _formatCount(subject?.followerCount), label: UITextConstants.circleFans, type: 'fans'),
    ];

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: items.map((item) {
        return GestureDetector(
          onTap: onStatTap != null ? () => onStatTap!(item.type) : null,
          behavior: HitTestBehavior.opaque,
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupXs),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  item.value,
                  style: TextStyle(
                    fontSize: AppTypography.lg,
                    fontWeight: AppTypography.bold,
                    color: fg,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs / 2),
                Text(
                  item.label,
                  style: TextStyle(
                    fontSize: AppTypography.xs,
                    fontWeight: AppTypography.medium,
                    color: fgSecondary,
                  ),
                ),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }
}

class _StatItem {
  const _StatItem({required this.value, required this.label, required this.type});
  final String value;
  final String label;
  final String type;
}
