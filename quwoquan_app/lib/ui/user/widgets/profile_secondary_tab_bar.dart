import 'package:flutter/cupertino.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 我的主页二级页签（记录 / 互动共用）的单项数据。
class ProfileSecondaryTabItem {
  const ProfileSecondaryTabItem({required this.id, required this.label});

  final String id;
  final String label;
}

/// 我的主页「记录」「互动」两个一级 Tab 共用的二级页签。
///
/// 视觉：横滑轻量胶囊。二级筛选只用很轻的主题色薄 tint 建立层级，
/// 避免与一级 Tab / 方向 switch 同时抢主视觉。
class ProfileSecondaryTabBar extends StatelessWidget {
  const ProfileSecondaryTabBar({
    super.key,
    required this.tabs,
    required this.selectedId,
    required this.onSelected,
    required this.isDark,
    this.scrollKey,
    this.onHorizontalDragEnd,
    this.trailing,
  });

  final List<ProfileSecondaryTabItem> tabs;
  final String selectedId;
  final ValueChanged<String> onSelected;
  final bool isDark;

  /// 供壳层测量二级页签可视区与横滑切换的 key（贴在可滚动行上）。
  final Key? scrollKey;

  /// 横向拖拽手势：用于在二级页签条上左右滑动切换一级/二级 Tab。
  final GestureDragEndCallback? onHorizontalDragEnd;

  /// 行尾插槽（互动页用于放「收到/发起」切换开关）。
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
