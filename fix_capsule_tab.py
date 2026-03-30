import re

with open('quwoquan_app/lib/components/navigation/secondary_capsule_tab_bar.dart', 'r') as f:
    content = f.read()

old_constructor = '''class SecondaryCapsuleTabBar extends StatelessWidget {
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
  final double fontSize;'''

new_constructor = '''class SecondaryCapsuleTabBar extends StatelessWidget {
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
  final Map<int, bool>? dotBadges;'''

content = content.replace(old_constructor, new_constructor)

old_item = '''                    return CupertinoButton(
                      padding: EdgeInsets.zero,
                      minimumSize: const Size(
                        AppSpacing.minInteractiveSize,
                        AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () => onTap(index),
                      child: AnimatedContainer('''

new_item = '''                    final hasNumberBadge = numberBadges != null && numberBadges![index] != null && numberBadges![index]! > 0;
                    final hasDotBadge = dotBadges != null && dotBadges![index] == true;
                    final badgeNumber = hasNumberBadge ? numberBadges![index]! : 0;
                    final badgeText = badgeNumber > 99 ? '99+' : badgeNumber.toString();

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
                          AnimatedContainer('''

content = content.replace(old_item, new_item)

old_text = '''                        child: Text(
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
                    );'''

new_text = '''                        child: Text(
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
                                  horizontal: badgeNumber > 9 ? 4 : 3,
                                  vertical: 1,
                                ),
                                decoration: BoxDecoration(
                                  color: AppColors.error,
                                  borderRadius: BorderRadius.circular(10),
                                  border: Border.all(
                                    color: bgPrimary,
                                    width: 1.5,
                                  ),
                                ),
                                child: Text(
                                  badgeText,
                                  style: const TextStyle(
                                    fontSize: 10,
                                    color: Colors.white,
                                    fontWeight: FontWeight.w600,
                                    height: 1.1,
                                  ),
                                ),
                              ),
                            )
                          else if (hasDotBadge)
                            Positioned(
                              right: 0,
                              top: 0,
                              child: Container(
                                width: 8,
                                height: 8,
                                decoration: BoxDecoration(
                                  color: AppColors.error,
                                  shape: BoxShape.circle,
                                  border: Border.all(
                                    color: bgPrimary,
                                    width: 1.5,
                                  ),
                                ),
                              ),
                            ),
                        ],
                      ),
                    );'''

content = content.replace(old_text, new_text)

with open('quwoquan_app/lib/components/navigation/secondary_capsule_tab_bar.dart', 'w') as f:
    f.write(content)

