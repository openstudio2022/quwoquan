import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:quwoquan_app/core/constants/ui_text_constants.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

enum HomePrimaryTabStripStyle { regular, immersive }

class HomePrimaryTabStrip extends StatelessWidget {
  const HomePrimaryTabStrip({
    super.key,
    required this.activeTab,
    required this.onTabChange,
    required this.isDark,
    this.style = HomePrimaryTabStripStyle.regular,
    this.featuredIndicatorVisible = false,
    this.featuredExpanded = false,
    this.onHorizontalDragEnd,
  });

  static const String followingTabId = 'following';
  static const String featuredTabId = 'featured';
  static const String circlesTabId = 'circles';
  static const Key stripKey = ValueKey<String>('home-primary-tab-strip');

  static Key tabKey(String tabId) =>
      ValueKey<String>('home-primary-tab-$tabId');

  final String activeTab;
  final ValueChanged<String> onTabChange;
  final bool isDark;
  final HomePrimaryTabStripStyle style;
  final bool featuredIndicatorVisible;
  final bool featuredExpanded;
  final GestureDragEndCallback? onHorizontalDragEnd;

  static double _measureLabelWidth(BuildContext context, String label) {
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(
          fontSize: AppTypography.primaryTabLabelResponsive(context),
          fontWeight: AppTypography.primaryTabSelectedWeight,
        ),
      ),
      maxLines: 1,
      textDirection: Directionality.of(context),
      textScaler: MediaQuery.textScalerOf(context),
    )..layout();
    return painter.width;
  }

  static double _slotWidth(
    BuildContext context,
    String label, {
    bool reserveAccessorySlot = false,
  }) {
    final labelWidth = _measureLabelWidth(context, label);
    final edgeReserve = reserveAccessorySlot
        ? AppSpacing.primaryTabAccessoryReserve(context)
        : AppSpacing.primaryTabSlotSidePadding(context);
    return (labelWidth + (edgeReserve * 2)).clamp(
      AppSpacing.minInteractiveSize,
      double.infinity,
    );
  }

  @override
  Widget build(BuildContext context) {
    final gap = AppSpacing.primaryTabGroupGap(context);
    final followingWidth = _slotWidth(
      context,
      UITextConstants.homeTabFollowing,
    );
    final featuredWidth = _slotWidth(
      context,
      UITextConstants.homeTabFeatured,
      reserveAccessorySlot: true,
    );
    final circlesWidth = _slotWidth(context, UITextConstants.homeTabCircles);
    return GestureDetector(
      behavior: HitTestBehavior.translucent,
      onHorizontalDragEnd: onHorizontalDragEnd,
      child: SizedBox(
        key: stripKey,
        height: AppSpacing.tabNavigationHeight,
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            _HomePrimaryTabStripItem(
              key: tabKey(followingTabId),
              tabId: followingTabId,
              label: UITextConstants.homeTabFollowing,
              selected: activeTab == followingTabId,
              slotWidth: followingWidth,
              isDark: isDark,
              style: style,
              onTap: () => _handleTabTap(followingTabId),
            ),
            SizedBox(width: gap),
            _HomePrimaryTabStripItem(
              key: tabKey(featuredTabId),
              tabId: featuredTabId,
              label: UITextConstants.homeTabFeatured,
              selected: activeTab == featuredTabId,
              slotWidth: featuredWidth,
              isDark: isDark,
              style: style,
              reserveIndicatorSlot: true,
              showIndicator: featuredIndicatorVisible,
              indicatorExpanded: featuredExpanded,
              onTap: () => _handleTabTap(featuredTabId),
            ),
            SizedBox(width: gap),
            _HomePrimaryTabStripItem(
              key: tabKey(circlesTabId),
              tabId: circlesTabId,
              label: UITextConstants.homeTabCircles,
              selected: activeTab == circlesTabId,
              slotWidth: circlesWidth,
              isDark: isDark,
              style: style,
              onTap: () => _handleTabTap(circlesTabId),
            ),
          ],
        ),
      ),
    );
  }

  void _handleTabTap(String tabId) {
    if (tabId != activeTab) {
      HapticFeedback.selectionClick();
    }
    onTabChange(tabId);
  }
}

class _HomePrimaryTabStripItem extends StatelessWidget {
  const _HomePrimaryTabStripItem({
    super.key,
    required this.tabId,
    required this.label,
    required this.selected,
    required this.slotWidth,
    required this.isDark,
    required this.style,
    required this.onTap,
    this.reserveIndicatorSlot = false,
    this.showIndicator = false,
    this.indicatorExpanded = false,
  });

  final String tabId;
  final String label;
  final bool selected;
  final double slotWidth;
  final bool isDark;
  final HomePrimaryTabStripStyle style;
  final VoidCallback onTap;
  final bool reserveIndicatorSlot;
  final bool showIndicator;
  final bool indicatorExpanded;

  @override
  Widget build(BuildContext context) {
    final selectedColor = switch (style) {
      HomePrimaryTabStripStyle.immersive => AppColors.worksTitle,
      HomePrimaryTabStripStyle.regular => AppColorsFunctional.getColor(
        isDark,
        ColorType.foregroundPrimary,
      ),
    };
    final unselectedColor = switch (style) {
      HomePrimaryTabStripStyle.immersive => AppColors.worksBodyText.withValues(
        alpha: 0.74,
      ),
      HomePrimaryTabStripStyle.regular => AppColorsFunctional.getColor(
        isDark,
        ColorType.tabUnselected,
      ),
    };
    final underlineColor = isDark
        ? AppColors.iosAccentDark
        : AppColors.primaryColor;
    final fontSize = AppTypography.primaryTabLabelResponsive(context);
    final selectedWeight = AppTypography.primaryTabSelectedWeight;
    final unselectedWeight = AppTypography.primaryTabUnselectedWeight;
    final textStyle = TextStyle(
      fontSize: fontSize,
      fontWeight: selected ? selectedWeight : unselectedWeight,
      color: selected ? selectedColor : unselectedColor,
    );
    final underlineWidth = _measureLabelWidth(
      context,
      fontSize,
      selectedWeight,
    );
    final indicatorColor = selected
        ? selectedColor
        : unselectedColor.withValues(alpha: 0.88);
    final indicatorReserve = reserveIndicatorSlot
        ? AppSpacing.primaryTabAccessoryReserve(context)
        : 0.0;
    final showUnderline =
        selected &&
        style == HomePrimaryTabStripStyle.regular &&
        tabId != HomePrimaryTabStrip.featuredTabId;

    return SizedBox(
      width: slotWidth,
      child: CupertinoButton(
        padding: EdgeInsets.zero,
        minimumSize: Size.square(AppSpacing.minInteractiveSize),
        borderRadius: BorderRadius.circular(AppSpacing.circularBorderRadius),
        onPressed: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(
            minWidth: AppSpacing.minInteractiveSize,
            minHeight: AppSpacing.minInteractiveSize,
          ),
          child: Stack(
            clipBehavior: Clip.none,
            children: [
              Align(
                alignment: Alignment.center,
                child: Text(
                  label,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: textStyle,
                ),
              ),
              if (reserveIndicatorSlot)
                Positioned.fill(
                  child: Align(
                    alignment: Alignment.centerRight,
                    child: SizedBox(
                      width: indicatorReserve,
                      child: AnimatedOpacity(
                        duration: const Duration(milliseconds: 180),
                        opacity: showIndicator ? 1 : 0,
                        child: AnimatedRotation(
                          duration: const Duration(milliseconds: 220),
                          turns: indicatorExpanded ? 0.5 : 0,
                          curve: Curves.easeOutCubic,
                          child: Icon(
                            Icons.keyboard_arrow_down,
                            color: indicatorColor,
                            size: AppSpacing.iconSmall,
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
              Positioned(
                left: 0,
                right: 0,
                bottom: 0,
                child: Center(
                  child: SizedBox(
                    width: underlineWidth,
                    child: AnimatedContainer(
                      duration: const Duration(milliseconds: 200),
                      height: showUnderline
                          ? AppSpacing.primaryTabUnderlineHeight
                          : 0,
                      decoration: BoxDecoration(
                        color: underlineColor,
                        borderRadius: BorderRadius.circular(
                          AppSpacing.primaryTabUnderlineHeight / 2,
                        ),
                      ),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  double _measureLabelWidth(
    BuildContext context,
    double fontSize,
    FontWeight fontWeight,
  ) {
    final painter = TextPainter(
      text: TextSpan(
        text: label,
        style: TextStyle(fontSize: fontSize, fontWeight: fontWeight),
      ),
      maxLines: 1,
      textDirection: Directionality.of(context),
    )..layout();
    return painter.width;
  }
}
