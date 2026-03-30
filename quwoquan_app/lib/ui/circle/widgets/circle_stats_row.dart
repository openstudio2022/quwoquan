import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';
import 'package:quwoquan_app/ui/circle/models/circle_stats_view_data.dart';

class CircleStatsRow extends StatelessWidget {
  const CircleStatsRow({
    super.key,
    required this.isDark,
    required this.stats,
    this.onStatTap,
  });

  final bool isDark;
  final CircleStatsViewData stats;
  final void Function(String type)? onStatTap;

  String _formatCount(int count) {
    return formatCompactActionCount(count);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    final items = [
      _StatItem(
        value: _formatCount(stats.members),
        label: UITextConstants.circleMembers,
        type: 'members',
      ),
      _StatItem(
        value: _formatCount(stats.posts),
        label: UITextConstants.circlePosts,
        type: 'posts',
      ),
      _StatItem(
        value: _formatCount(stats.weeklyActive),
        label: UITextConstants.circleWeeklyActive,
        type: 'weeklyActive',
      ),
      _StatItem(
        value: _formatCount(stats.likes),
        label: UITextConstants.circleLikes,
        type: 'likes',
      ),
    ];

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: items.map((item) {
        return Expanded(
          child: GestureDetector(
            onTap: onStatTap != null ? () => onStatTap!(item.type) : null,
            behavior: HitTestBehavior.opaque,
            child: Container(
              margin: EdgeInsets.symmetric(horizontal: AppSpacing.intraGroupXs / 2),
              padding: EdgeInsets.symmetric(
                vertical: AppSpacing.sm,
                horizontal: AppSpacing.xs,
              ),
              decoration: BoxDecoration(
                color: fgSecondary.withValues(alpha: 0.06),
                borderRadius: BorderRadius.circular(AppSpacing.borderRadius),
              ),
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
