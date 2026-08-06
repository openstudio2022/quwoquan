import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 对象页「Tab 内容区」二级筛选项（id + 展示文案）。
class ObjectSecondaryFilterItem {
  const ObjectSecondaryFilterItem({required this.id, required this.label});

  final String id;
  final String label;
}

/// 对象页二级内容筛选胶囊条（实体 / 圈子主页共享）。
///
/// 高保口径：一级 Tab（记录 / 讨论 / …）正下方横向胶囊「全部 图片 视频 …」，
/// 选中态淡蓝底 + 深色字、未选中灰字透明底；横向可滚动，短列表左对齐。
/// 单一真相源，替换实体 / 圈子各自的「漏斗 + 弹层」二级过滤（消除重复，R24/R25）；
/// 颜色 / 间距 / 字号复用我的主页二级 Tab token。
class ObjectSecondaryFilterBar extends StatelessWidget {
  const ObjectSecondaryFilterBar({
    super.key,
    required this.items,
    required this.activeId,
    required this.onSelect,
    this.barKey,
    this.optionKeyPrefix,
  });

  final List<ObjectSecondaryFilterItem> items;
  final String activeId;
  final ValueChanged<String> onSelect;

  /// 滚动容器根 key（供 widget 测试定位整条筛选条）。
  final Key? barKey;

  /// 单个胶囊 key 前缀；非空时各胶囊 key 为 `$optionKeyPrefix$id`。
  final String? optionKeyPrefix;

  @override
  Widget build(BuildContext context) {
    if (items.length < 2) {
      return const SizedBox.shrink();
    }
    final chipGap = AppSpacing.secondaryTabGap(context);
    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.secondaryTabBarVerticalPadding(context) / 2.2,
      ),
      child: SingleChildScrollView(
        key: barKey,
        scrollDirection: Axis.horizontal,
        physics: const BouncingScrollPhysics(),
        child: Row(
          children: List<Widget>.generate(items.length, (index) {
            final item = items[index];
            return Padding(
              padding: EdgeInsets.only(
                right: index == items.length - 1 ? AppSpacing.zero : chipGap,
              ),
              child: _ObjectFilterChip(
                label: item.label,
                selected: item.id == activeId,
                onTap: () => onSelect(item.id),
                chipKey: optionKeyPrefix == null
                    ? null
                    : ValueKey<String>('$optionKeyPrefix${item.id}'),
              ),
            );
          }),
        ),
      ),
    );
  }
}

class _ObjectFilterChip extends StatelessWidget {
  const _ObjectFilterChip({
    required this.label,
    required this.selected,
    required this.onTap,
    this.chipKey,
  });

  final String label;
  final bool selected;
  final VoidCallback onTap;
  final Key? chipKey;

  @override
  Widget build(BuildContext context) {
    final isDark = CupertinoTheme.of(context).brightness == Brightness.dark;
    final background = selected
        ? AppColors.iosAccent(context).withValues(alpha: isDark ? 0.18 : 0.08)
        : AppColors.transparent;
    final border = selected
        ? AppColors.iosAccent(context).withValues(alpha: isDark ? 0.22 : 0.12)
        : AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorSubtle,
          ).withValues(alpha: isDark ? 0.18 : 0.10);
    final foreground = selected
        ? AppColorsFunctional.getColor(isDark, ColorType.selectionForeground)
        : AppColorsFunctional.getColor(isDark, ColorType.foregroundSecondary);
    return CupertinoButton(
      key: chipKey,
      padding: EdgeInsets.zero,
      minimumSize: const Size(
        AppSpacing.minInteractiveSize,
        AppSpacing.buttonHeightSmCompact,
      ),
      onPressed: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        curve: Curves.easeOutCubic,
        padding: EdgeInsets.symmetric(
          horizontal: AppSpacing.secondaryTabChipHorizontalPadding(context),
          vertical: AppSpacing.secondaryTabChipVerticalPadding(context) / 3,
        ),
        decoration: BoxDecoration(
          color: background,
          borderRadius: BorderRadius.circular(AppSpacing.radiusNinetyNine),
          border: Border.all(color: border, width: AppSpacing.hairline),
        ),
        child: Text(
          label,
          style: TextStyle(
            fontSize: AppTypography.secondaryTabLabelResponsive(context),
            fontWeight: selected
                ? AppTypography.secondaryTabSelectedWeight
                : AppTypography.secondaryTabUnselectedWeight,
            color: foreground,
            letterSpacing: 0,
          ),
        ),
      ),
    );
  }
}
