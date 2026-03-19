import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum SecondaryCapsuleTabBarVariant { defaultSurface, inlineMuted }

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
    this.numberBadges,
    this.dotBadges,
    this.variant = SecondaryCapsuleTabBarVariant.defaultSurface,
    this.onHorizontalDragEnd,
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
  final Map<int, int>? numberBadges;
  final Map<int, bool>? dotBadges;
  final SecondaryCapsuleTabBarVariant variant;
  final GestureDragEndCallback? onHorizontalDragEnd;

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
        switch (variant) {
          SecondaryCapsuleTabBarVariant.inlineMuted => Colors.transparent,
          SecondaryCapsuleTabBarVariant.defaultSurface =>
            isDark
                ? Colors.white.withValues(alpha: 0.04)
                : Colors.black.withValues(alpha: 0.03),
        };
    final contentHorizontal =
        horizontalPadding ?? AppSpacing.feedContentHorizontal(context);
    final verticalPadding = variant == SecondaryCapsuleTabBarVariant.inlineMuted
        ? AppSpacing.intraGroupXs
        : AppSpacing.intraGroupSm;
    final selectedLightFill =
        variant == SecondaryCapsuleTabBarVariant.inlineMuted ? 0.08 : 0.12;
    final selectedDarkFill =
        variant == SecondaryCapsuleTabBarVariant.inlineMuted ? 0.1 : 0.15;
    final selectedLightBorder =
        variant == SecondaryCapsuleTabBarVariant.inlineMuted ? 0.18 : 0.25;
    final selectedDarkBorder =
        variant == SecondaryCapsuleTabBarVariant.inlineMuted ? 0.16 : 0.2;
    final unselectedBorder =
        variant == SecondaryCapsuleTabBarVariant.inlineMuted ? 0.12 : 0.2;
    final dividerAlpha = variant == SecondaryCapsuleTabBarVariant.inlineMuted
        ? 0.08
        : 0.12;

    return SizedBox(
      height: AppSpacing.subTabNavigationHeight,
      child: Container(
        color: bgPrimary,
        child: Container(
          decoration: BoxDecoration(color: barColor, border: border),
          child: Row(
            children: [
              Expanded(
                child: GestureDetector(
                  behavior: HitTestBehavior.translucent,
                  onHorizontalDragEnd: onHorizontalDragEnd,
                  child: ListView.separated(
                    scrollDirection: Axis.horizontal,
                    physics: const BouncingScrollPhysics(),
                    padding: EdgeInsets.fromLTRB(
                      contentHorizontal,
                      verticalPadding,
                      AppSpacing.sm,
                      verticalPadding,
                    ),
                    itemCount: tabs.length,
                    separatorBuilder: (context, index) =>
                        SizedBox(width: AppSpacing.intraGroupSm),
                    itemBuilder: (context, index) {
                      final selected = activeIndex == index;
                      final hasNumberBadge =
                          numberBadges != null &&
                          numberBadges![index] != null &&
                          numberBadges![index]! > 0;
                      final hasDotBadge =
                          dotBadges != null && dotBadges![index] == true;
                      final badgeNumber = hasNumberBadge
                          ? numberBadges![index]!
                          : 0;
                      final badgeText = badgeNumber > 99
                          ? '99+'
                          : badgeNumber.toString();

                      return CupertinoButton(
                        padding: EdgeInsets.zero,
                        minimumSize: const Size(
                          AppSpacing.minInteractiveSize,
                          AppSpacing.minInteractiveSize,
                        ),
                        onPressed: () => onTap(index),
                        child: Stack(
                          clipBehavior: Clip.none,
                          children: [
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 200),
                              alignment: Alignment.center,
                              padding: EdgeInsets.symmetric(
                                horizontal:
                                    AppSpacing.intraGroupMd + AppSpacing.xs,
                                vertical: AppSpacing.intraGroupXs,
                              ),
                              decoration: BoxDecoration(
                                color: selected
                                    ? (isDark
                                          ? Colors.white.withValues(
                                              alpha: selectedDarkFill,
                                            )
                                          : AppColors.primaryColor.withValues(
                                              alpha: selectedLightFill,
                                            ))
                                    : Colors.transparent,
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.circularBorderRadius,
                                ),
                                border: Border.all(
                                  color: selected
                                      ? (isDark
                                            ? Colors.white.withValues(
                                                alpha: selectedDarkBorder,
                                              )
                                            : AppColors.primaryColor.withValues(
                                                alpha: selectedLightBorder,
                                              ))
                                      : fgSecondary.withValues(
                                          alpha: unselectedBorder,
                                        ),
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
                            if (hasNumberBadge)
                              Positioned(
                                right: -4,
                                top: -4,
                                child: Container(
                                  padding: EdgeInsets.symmetric(
                                    horizontal: badgeNumber > 9
                                        ? AppSpacing.xs
                                        : AppSpacing.three,
                                    vertical: AppSpacing.one,
                                  ),
                                  decoration: BoxDecoration(
                                    color: AppColors.error,
                                    borderRadius: BorderRadius.circular(
                                      AppSpacing.radiusTen,
                                    ),
                                    border: Border.all(
                                      color: bgPrimary,
                                      width: AppSpacing.oneHalf,
                                    ),
                                  ),
                                  child: Text(
                                    badgeText,
                                    style: const TextStyle(
                                      fontSize: AppTypography.xs,
                                      color: Colors.white,
                                      fontWeight: FontWeight.w600,
                                      height: AppTypography.lineHeightTight,
                                    ),
                                  ),
                                ),
                              )
                            else if (hasDotBadge)
                              Positioned(
                                right: 0,
                                top: 0,
                                child: Container(
                                  width: AppSpacing.sm,
                                  height: AppSpacing.sm,
                                  decoration: BoxDecoration(
                                    color: AppColors.error,
                                    shape: BoxShape.circle,
                                    border: Border.all(
                                      color: bgPrimary,
                                      width: AppSpacing.oneHalf,
                                    ),
                                  ),
                                ),
                              ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
              ),
              if (showTrailingDivider && trailing != null)
                Container(
                  width: AppSpacing.intraGroupXs / 4,
                  margin: EdgeInsets.symmetric(
                    vertical: AppSpacing.intraGroupSm,
                  ),
                  color: fgSecondary.withValues(alpha: dividerAlpha),
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
