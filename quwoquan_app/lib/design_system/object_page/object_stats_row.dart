import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 单条统计项（值 + 标签 + 点击分发 type）。
///
/// 各主页统计维度不同（实体=关注/记录/讨论，圈子=成员/记录/讨论，
/// 用户=粉丝/关注/赞/圈子），但渲染与点击语义统一由 [ObjectStatsRow] 承载。
class ObjectStatItem {
  const ObjectStatItem({
    required this.value,
    required this.label,
    this.type = '',
  });

  /// 已格式化的统计值文本（调用方负责紧凑化）。
  final String value;
  final String label;

  /// 点击分发标识；为空表示该项不可点击。
  final String type;
}

/// 全宽单行统计行（对象/圈子/用户主页共享）。
///
/// 单一真相源：用户主页 `ProfileStatsRow` 泛化而来，解除对具体 ViewData 的绑定，
/// 改吃 [ObjectStatItem] 列表；保留 `·` 分隔、`iosSubheadline` 值 + `iosFootnote` 标签、
/// 以及 `onStatTap` 点击分发。
class ObjectStatsRow extends StatelessWidget {
  const ObjectStatsRow({
    super.key,
    required this.isDark,
    required this.items,
    this.onStatTap,
    this.rowKey = const ValueKey<String>('object-stats-inline-row'),
  });

  final bool isDark;
  final List<ObjectStatItem> items;
  final void Function(String type)? onStatTap;

  /// 统计行根节点 key（用户主页沿用 `profile-stats-inline-row` 以保持既有断言）。
  final Key rowKey;

  @override
  Widget build(BuildContext context) {
    final fg = AppColors.iosLabel(context);
    final fgSecondary = AppColors.iosSecondaryLabel(context);
    final visible = items
        .where((item) => item.value.trim().isNotEmpty)
        .toList(growable: false);

    return Wrap(
      key: rowKey,
      spacing: AppSpacing.intraGroupXs,
      runSpacing: AppSpacing.intraGroupXs,
      crossAxisAlignment: WrapCrossAlignment.center,
      children: <Widget>[
        for (var i = 0; i < visible.length; i += 1) ...<Widget>[
          _buildInlineStat(visible[i], fg, fgSecondary),
          if (i != visible.length - 1)
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

  Widget _buildInlineStat(ObjectStatItem item, Color fg, Color fgSecondary) {
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
