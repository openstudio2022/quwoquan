import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

/// 统一二级胶囊 Tab：趣信与圈子首页共用同一套间距、圆角、背景与选中语义。
class SecondaryCapsuleTabBar extends StatelessWidget {
  const SecondaryCapsuleTabBar({
    super.key,
    required this.isDark,
    required this.tabs,
    required this.activeIndex,
    required this.onTap,
    this.horizontalPadding,
    this.backgroundColor,
    this.border,
    this.trailing,
    this.showTrailingDivider = false,
    this.fontSize = AppTypography.smPlus,
  });

  final bool isDark;
  final List<String> tabs;
  final int activeIndex;
  final ValueChanged<int> onTap;
  final double? horizontalPadding;
  final Color? backgroundColor;
  final BoxBorder? border;
  final Widget? trailing;
  final bool showTrailingDivider;
  final double fontSize;

  @override
  Widget build(BuildContext context) {
    final bgPrimary = AppColorsFunctional.getColor(
      isDark,
      ColorType.backgroundPrimary,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final barColor =
        backgroundColor ??
        (isDark
            ? Colors.white.withValues(alpha: 0.04)
            : Colors.black.withValues(alpha: 0.03));
    final contentHorizontal =
        horizontalPadding ?? AppSpacing.feedContentHorizontal(context);

    return SizedBox(
      height: AppSpacing.subTabNavigationHeight,
      child: Container(
        color: bgPrimary,
        child: Container(
          decoration: BoxDecoration(color: barColor, border: border),
          child: Row(
            children: [
              Expanded(
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  physics: const BouncingScrollPhysics(),
                  padding: EdgeInsets.fromLTRB(
                    contentHorizontal,
                    AppSpacing.intraGroupSm,
                    AppSpacing.sm,
                    AppSpacing.intraGroupSm,
                  ),
                  itemCount: tabs.length,
                  separatorBuilder: (context, index) =>
                      SizedBox(width: AppSpacing.intraGroupSm),
                  itemBuilder: (context, index) {
                    final selected = activeIndex == index;
                    return CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(
                        AppSpacing.minInteractiveSize,
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () => onTap(index),
                      child: AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        alignment: Alignment.center,
                        padding: EdgeInsets.symmetric(
                          horizontal: AppSpacing.intraGroupMd + AppSpacing.xs,
                          vertical: AppSpacing.intraGroupXs,
                        ),
                        decoration: BoxDecoration(
                          color: selected
                              ? (isDark
                                    ? Colors.white.withValues(alpha: 0.15)
                                    : AppColors.primaryColor.withValues(
                                        alpha: 0.12,
                                      ))
                              : Colors.transparent,
                          borderRadius: BorderRadius.circular(
                            AppSpacing.circularBorderRadius,
                          ),
                          border: Border.all(
                            color: selected
                                ? (isDark
                                      ? Colors.white.withValues(alpha: 0.2)
                                      : AppColors.primaryColor.withValues(
                                          alpha: 0.25,
                                        ))
                                : fgSecondary.withValues(alpha: 0.2),
                            width: AppSpacing.intraGroupXs / 4,
                          ),
                        ),
                        child: Text(
                          tabs[index],
                          style: TextStyle(
                            fontSize: fontSize,
                            fontWeight: selected
                                ? AppTypography.semiBold
                                : AppTypography.medium,
                            color: selected
                                ? (isDark
                                      ? Colors.white
                                      : AppColors.primaryColor)
                                : fgSecondary,
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
              if (showTrailingDivider && trailing != null)
                Container(
                  width: AppSpacing.intraGroupXs / 4,
                  margin: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupSm,
                  ),
                  color: fgSecondary.withValues(alpha: 0.12),
                ),
              ...switch (trailing) {
                final Widget trailingWidget => <Widget>[trailingWidget],
                null => const <Widget>[],
              },
            ],
          ),
        ),
      ),
    );
  }
}
