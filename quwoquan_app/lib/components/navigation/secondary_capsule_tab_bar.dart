import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum SecondaryCapsuleTabBarVariant { defaultSurface, inlineMuted, iosProfile }

double _secondaryCapsuleTabBarHeight(BuildContext context, double fontSize) {
  final resolvedFontSize = fontSize == AppTypography.secondaryTabLabel
      ? AppTypography.secondaryTabLabelResponsive(context)
      : fontSize;
  final verticalPadding = AppSpacing.secondaryTabBarVerticalPadding(context);
  final painter = TextPainter(
    text: TextSpan(
      text: 'Hg',
      style: TextStyle(
        fontSize: resolvedFontSize,
        fontWeight: AppTypography.secondaryTabSelectedWeight,
      ),
    ),
    textDirection: Directionality.of(context),
    textScaler: MediaQuery.textScalerOf(context),
    maxLines: 1,
  )..layout();
  final measuredHeight =
      painter.height +
      (verticalPadding * 2) +
      (AppSpacing.secondaryTabChipVerticalPadding(context) * 2);
  return measuredHeight > AppSpacing.subTabNavigationHeight
      ? measuredHeight
      : AppSpacing.subTabNavigationHeight;
}

/// 统一二级胶囊 Tab：趣信、作者主页及其他筛选统一使用同一套间距、字号与选中语义。
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
    this.fontSize = AppTypography.secondaryTabLabel,
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
      ColorType.pageBackground,
    );
    final fgSecondary = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundSecondary,
    );
    final barColor =
        backgroundColor ??
        switch (variant) {
          SecondaryCapsuleTabBarVariant.inlineMuted => AppColors.transparent,
          SecondaryCapsuleTabBarVariant.iosProfile => AppColors.transparent,
          SecondaryCapsuleTabBarVariant.defaultSurface =>
            AppColorsFunctional.getColor(
              isDark,
              ColorType.secondaryCapsuleTrack,
            ),
        };
    final outerBackground = switch (variant) {
      SecondaryCapsuleTabBarVariant.inlineMuted => AppColors.transparent,
      SecondaryCapsuleTabBarVariant.iosProfile => AppColors.transparent,
      _ => bgPrimary,
    };
    final contentHorizontal =
        horizontalPadding ?? AppSpacing.feedContentHorizontal(context);
    final verticalPadding = AppSpacing.secondaryTabBarVerticalPadding(context);
    final chipHorizontalPadding = AppSpacing.secondaryTabChipHorizontalPadding(
      context,
    );
    final chipVerticalPadding = AppSpacing.secondaryTabChipVerticalPadding(
      context,
    );
    final chipGap = AppSpacing.secondaryTabGap(context);
    final resolvedFontSize = fontSize == AppTypography.secondaryTabLabel
        ? AppTypography.secondaryTabLabelResponsive(context)
        : fontSize;
    final barHeight = _secondaryCapsuleTabBarHeight(context, fontSize);
    final selectedBackground = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionBackground,
    );
    final selectedBorder = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionBorder,
    );
    final selectedForeground = AppColorsFunctional.getColor(
      isDark,
      ColorType.selectionForeground,
    );
    final unselectedBorderColor =
        AppColorsFunctional.getColor(
          isDark,
          ColorType.separatorSubtle,
        ).withValues(
          alpha: variant == SecondaryCapsuleTabBarVariant.inlineMuted
              ? 0.2
              : 0.28,
        );
    final dividerAlpha = switch (variant) {
      SecondaryCapsuleTabBarVariant.inlineMuted => 0.08,
      SecondaryCapsuleTabBarVariant.iosProfile => 0.08,
      SecondaryCapsuleTabBarVariant.defaultSurface => 0.12,
    };

    return SizedBox(
      height: barHeight,
      child: Container(
        color: outerBackground,
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
                      trailing == null
                          ? contentHorizontal
                          : AppSpacing.containerXs,
                      verticalPadding,
                    ),
                    itemCount: tabs.length,
                    separatorBuilder: (context, index) =>
                        SizedBox(width: chipGap),
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
                        onPressed: () {
                          if (index != activeIndex) {
                            HapticFeedback.selectionClick();
                          }
                          onTap(index);
                        },
                        child: Stack(
                          clipBehavior: Clip.none,
                          children: [
                            AnimatedContainer(
                              duration: const Duration(milliseconds: 200),
                              alignment: Alignment.center,
                              padding: EdgeInsets.symmetric(
                                horizontal: chipHorizontalPadding,
                                vertical: chipVerticalPadding,
                              ),
                              decoration: BoxDecoration(
                                color: selected
                                    ? selectedBackground
                                    : AppColors.transparent,
                                borderRadius: BorderRadius.circular(
                                  AppSpacing.largeBorderRadius,
                                ),
                                border: Border.all(
                                  color: selected
                                      ? selectedBorder
                                      : unselectedBorderColor,
                                  width: AppSpacing.intraGroupXs / 4,
                                ),
                              ),
                              child: Text(
                                tabs[index],
                                style: TextStyle(
                                  fontSize: resolvedFontSize,
                                  fontWeight: selected
                                      ? AppTypography.secondaryTabSelectedWeight
                                      : AppTypography
                                            .secondaryTabUnselectedWeight,
                                  color: selected
                                      ? selectedForeground
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
                                    style: TextStyle(
                                      fontSize: AppTypography.xs,
                                      color: AppColorsFunctional.getColor(
                                        isDark,
                                        ColorType.badgeForeground,
                                      ),
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
