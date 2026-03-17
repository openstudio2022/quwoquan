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
    final n = count is int ? count : int.tryParse(count.toString()) ?? 0;
    return formatCompactActionCount(n);
  }

  @override
  Widget build(BuildContext context) {
    final fg = AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary);
    final fgSecondary = AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);

    final items = [
      _StatItem(value: _formatCount(stats['members']), label: UITextConstants.circleMembers, type: 'members'),
      _StatItem(value: _formatCount(stats['groups']), label: UITextConstants.circleGroups, type: 'groups'),
      _StatItem(value: _formatCount(stats['fans']), label: UITextConstants.circleFans, type: 'fans'),
      _StatItem(value: _formatCount(stats['likes']), label: UITextConstants.circleLikes, type: 'likes'),
    ];

    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: items.map((item) {
        return GestureDetector(
          onTap: onStatTap != null ? () => onStatTap!(item.type) : null,
          behavior: HitTestBehavior.opaque,
          child: Padding(
            padding: EdgeInsets.symmetric(vertical: AppSpacing.intraGroupSm),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  item.value,
                  style: TextStyle(
                    fontSize: AppTypography.xl,
                    fontWeight: AppTypography.bold,
                    color: fg,
                  ),
                ),
                SizedBox(height: AppSpacing.intraGroupXs),
                Text(
                  item.label,
                  style: TextStyle(
                    fontSize: AppTypography.sm,
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
