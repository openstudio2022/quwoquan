import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:quwoquan_app/core/quwoquan_core.dart';

class BottomNavigationWidget extends ConsumerWidget {
  final int currentIndex;
  final Function(int) onTap;

  const BottomNavigationWidget({
    super.key,
    required this.currentIndex,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final themeDark = ref.watch(isDarkProvider);
    final forceDark = ref.watch(videoForceDarkProvider).forceDark;
    final isDark = themeDark || forceDark;
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    // 与 [MainAppShell] 主壳底同色，避免 glassSurface + BackdropFilter 的半透明毛玻璃感。
    final navBackground = forceDark
        ? AppColors.worksBackground
        : AppColorsFunctional.getColor(isDark, ColorType.pageBackground);
    final activeColor = forceDark
        ? CupertinoColors.white
        : AppColors.iosLabel(context);
    final inactiveColor = forceDark
        ? CupertinoColors.systemGrey
        : AppColors.iosSecondaryLabel(context);
    final borderColor = forceDark
        ? CupertinoColors.systemGrey.withValues(alpha: 0.28)
        : AppColorsFunctional.getColor(
            isDark,
            ColorType.separatorOpaque,
          ).withValues(alpha: 0.72);
    final destinations = const <_BottomDestination>[
      _BottomDestination(
        label: AppConceptConstants.discovery,
        icon: CupertinoIcons.house,
        selectedIcon: CupertinoIcons.house_fill,
      ),
      _BottomDestination(
        label: AppConceptConstants.circles,
        icon: CupertinoIcons.person_2,
        selectedIcon: CupertinoIcons.person_2_fill,
      ),
      _BottomDestination(
        label: '',
        semanticLabel: AppConceptConstants.create,
        icon: CupertinoIcons.plus,
        selectedIcon: CupertinoIcons.plus,
        isPrimaryAction: true,
      ),
      _BottomDestination(
        label: AppConceptConstants.chat,
        icon: CupertinoIcons.chat_bubble_2,
        selectedIcon: CupertinoIcons.chat_bubble_2_fill,
      ),
      _BottomDestination(
        label: AppConceptConstants.profile,
        icon: CupertinoIcons.person_crop_circle,
        selectedIcon: CupertinoIcons.person_crop_circle_fill,
      ),
    ];

    final sideInset = AppSpacing.bottomNavContentSideInset(context, bottomInset);
    final vPad = AppSpacing.toolbarVerticalPadding(context);
    final navHeight = AppSpacing.bottomNavBarHeight(context);
    return DecoratedBox(
      decoration: BoxDecoration(
        color: navBackground,
        border: Border(
          top: BorderSide(color: borderColor, width: AppSpacing.hairline),
        ),
      ),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: sideInset),
        child: SizedBox(
          height: navHeight + bottomInset,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: List<Widget>.generate(destinations.length, (index) {
              final selected =
                  (currentIndex < 0 ? 0 : currentIndex) == index;
              final destination = destinations[index];
              return Expanded(
                child: CupertinoButton(
                  padding: EdgeInsets.zero,
                  minimumSize: Size.zero,
                  onPressed: () {
                    if (selected) return;
                    HapticFeedback.selectionClick();
                    onTap(index);
                  },
                  child: _BottomNavItem(
                    destination: destination,
                    selected: selected,
                    activeColor: activeColor,
                    inactiveColor: inactiveColor,
                    contentHeight: navHeight + bottomInset,
                  ),
                ),
              );
            }),
          ),
        ),
      ),
    );
  }
}

class _BottomDestination {
  const _BottomDestination({
    required this.label,
    required this.icon,
    required this.selectedIcon,
    this.semanticLabel,
    this.isPrimaryAction = false,
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
  final String? semanticLabel;
  final bool isPrimaryAction;
}

class _BottomNavItem extends StatelessWidget {
  const _BottomNavItem({
    required this.destination,
    required this.selected,
    required this.activeColor,
    required this.inactiveColor,
    required this.contentHeight,
  });

  final _BottomDestination destination;
  final bool selected;
  final Color activeColor;
  final Color inactiveColor;
  final double contentHeight;

  @override
  Widget build(BuildContext context) {
    final labelStyle = TextStyle(
      fontSize: AppTypography.iosCaption2,
      fontWeight: AppTypography.bottomNavLabelWeight,
      color: selected ? activeColor : inactiveColor,
      height: AppTypography.lineHeightTight,
      letterSpacing: -0.08,
    );

    return Semantics(
      button: true,
      selected: selected,
      label: destination.semanticLabel ?? destination.label,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          if (destination.isPrimaryAction)
            Container(
              width: AppSpacing.primaryActionCircleSize,
              height: AppSpacing.primaryActionCircleSize,
              decoration: BoxDecoration(
                color: AppColors.primaryColor,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primaryColor.withValues(alpha: 0.28),
                    blurRadius: AppSpacing.sm,
                    offset: const Offset(0, 4),
                  ),
                ],
              ),
              child: Icon(
                destination.selectedIcon,
                size: AppSpacing.iconSmall + 4,
                color: AppColors.white,
              ),
            )
          else ...[
            Icon(
              selected ? destination.selectedIcon : destination.icon,
              size: AppSpacing.iconSmall + 6,
              color: selected ? activeColor : inactiveColor,
            ),
            SizedBox(height: AppSpacing.oneHalf),
            AnimatedDefaultTextStyle(
              duration: const Duration(milliseconds: 180),
              curve: Curves.easeOutCubic,
              style: labelStyle,
              child: Text(
                destination.label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ],
      ),
    );
  }
}
