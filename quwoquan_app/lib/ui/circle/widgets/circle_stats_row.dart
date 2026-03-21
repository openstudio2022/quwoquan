import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';
import 'package:quwoquan_app/core/utils/compact_count_formatter.dart';

class CircleStatsRow extends StatelessWidget {
  const CircleStatsRow({
    super.key,
    required this.isDark,
    required this.stats,
    this.onStatTap,
  });

  final bool isDark;
  final Map<String, dynamic> stats;
  final void Function(String type)? onStatTap;

  String _formatCount(dynamic count) {
    if (count == null) return '0';
    if (count is String) {
      final raw = count.trim();
      final parsed = int.tryParse(raw);
      if (parsed == null) {
        return raw.isEmpty ? '0' : raw;
      }
      return formatCompactActionCount(parsed);
    }
    final n = count is int ? count : int.tryParse(count.toString()) ?? 0;
    return formatCompactActionCount(n);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    final items = [
      _StatItem(
        value: _formatCount(stats['members'] ?? stats['totalMembers']),
        label: UITextConstants.circleMembers,
        type: 'members',
      ),
      _StatItem(
        value: _formatCount(stats['posts'] ?? stats['totalPosts']),
        label: UITextConstants.circlePosts,
        type: 'posts',
      ),
      _StatItem(
        value: _formatCount(stats['weeklyActive'] ?? stats['active']),
        label: UITextConstants.circleWeeklyActive,
        type: 'weeklyActive',
      ),
      _StatItem(
        value: _formatCount(stats['likes'] ?? stats['totalLikes']),
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
