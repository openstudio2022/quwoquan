import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';

/// 通用二级页签的单项数据。
class AppSecondaryTabItem {
  const AppSecondaryTabItem({required this.id, required this.label});

  final String id;
  final String label;
}

/// 跨业务页面共用的轻量二级胶囊页签。
class AppSecondaryTabBar extends StatelessWidget {
  const AppSecondaryTabBar({
    super.key,
    required this.tabs,
    required this.selectedId,
    required this.onSelected,
    required this.isDark,
    this.scrollKey,
    this.onHorizontalDragEnd,
    this.trailing,
  });

  final List<AppSecondaryTabItem> tabs;
  final String selectedId;
  final ValueChanged<String> onSelected;
  final bool isDark;

  /// 供壳层测量二级页签可视区与横滑切换的 key（贴在可滚动行上）。
  final Key? scrollKey;

  /// 横向拖拽手势：用于在二级页签条上左右滑动切换一级/二级 Tab。
  final GestureDragEndCallback? onHorizontalDragEnd;

  /// 行尾插槽。
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final selectedFill = AppColors.iosAccent(
      context,
    ).withValues(alpha: isDark ? 0.18 : 0.08);
    final selectedBorder = AppColors.iosAccent(
      context,
    ).withValues(alpha: isDark ? 0.22 : 0.12);
    final selectedForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionForeground,
    );
    final unselectedBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.separatorSubtle,
    ).withValues(alpha: isDark ? 0.18 : 0.10);
    final chipHorizontalPadding = AppSpacing.secondaryTabChipHorizontalPadding(
      context,
    );
    final chipVerticalPadding = AppSpacing.secondaryTabChipVerticalPadding(
      context,
    );
    final chipGap = AppSpacing.secondaryTabGap(context);

    return Padding(
      padding: EdgeInsets.symmetric(
        horizontal: AppSpacing.containerMd,
        vertical: AppSpacing.secondaryTabBarVerticalPadding(context) / 2.2,
      ),
      child: Row(
        children: <Widget>[
          Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.translucent,
              onHorizontalDragEnd: onHorizontalDragEnd,
              child: SingleChildScrollView(
                key: scrollKey,
                scrollDirection: Axis.horizontal,
                physics: const BouncingScrollPhysics(),
                child: Row(
                  children: List<Widget>.generate(tabs.length, (index) {
                    final tab = tabs[index];
                    final selected = tab.id == selectedId;
                    return Padding(
                      padding: EdgeInsets.only(
                        right: index == tabs.length - 1
                            ? AppSpacing.zero
                            : chipGap,
                      ),
                      child: CupertinoButton(
                        minimumSize: const Size(
                          AppSpacing.minInteractiveSize,
                          AppSpacing.buttonHeightSmCompact,
                        ),
                        padding: EdgeInsets.zero,
                        onPressed: () => onSelected(tab.id),
                        child: AnimatedContainer(
                          duration: const Duration(milliseconds: 180),
                          curve: Curves.easeOutCubic,
                          padding: EdgeInsets.symmetric(
                            horizontal: chipHorizontalPadding,
                            vertical: chipVerticalPadding / 3,
                          ),
                          decoration: BoxDecoration(
                            color: selected
                                ? selectedFill
                                : AppColors.transparent,
                            borderRadius: BorderRadius.circular(
                              AppSpacing.radiusNinetyNine,
                            ),
                            border: Border.all(
                              color: selected
                                  ? selectedBorder
                                  : unselectedBorder,
                              width: AppSpacing.hairline,
                            ),
                          ),
                          child: Text(
                            tab.label,
                            style: TextStyle(
                              fontSize:
                                  AppTypography.secondaryTabLabelResponsive(
                                    context,
                                  ),
                              fontWeight: selected
                                  ? AppTypography.secondaryTabSelectedWeight
                                  : AppTypography.secondaryTabUnselectedWeight,
                              color: selected
                                  ? selectedForeground
                                  : fgSecondary,
                              letterSpacing: 0,
                            ),
                          ),
                        ),
                      ),
                    );
                  }),
                ),
              ),
            ),
          ),
          if (trailing != null) ...<Widget>[
            SizedBox(width: AppSpacing.containerSm),
            trailing!,
          ],
        ],
      ),
    );
  }
}
