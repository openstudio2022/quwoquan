import 'dart:ui';

import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';
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
    final navBackground = forceDark
        ? AppColors.worksBackground.withValues(alpha: 0.9)
        : AppColorsFunctional.getColor(isDark, ColorType.glassSurface);
    final activeColor = forceDark
        ? AppColors.worksAccent
        : AppColors.iosAccent(context);
    final inactiveColor = forceDark
        ? AppColors.worksBodyText
        : AppColors.iosSecondaryLabel(context);
    final borderColor = forceDark
        ? AppColors.worksAccent.withValues(alpha: 0.24)
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
        label: AppConceptConstants.assistantTabLabel,
        icon: CupertinoIcons.sparkles,
        selectedIcon: CupertinoIcons.sparkles,
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

    return ClipRect(
      child: BackdropFilter(
        filter: ImageFilter.blur(
          sigmaX: forceDark ? 0 : AppSpacing.eighteen,
          sigmaY: forceDark ? 0 : AppSpacing.eighteen,
        ),
        child: DecoratedBox(
          decoration: BoxDecoration(
            color: navBackground,
            border: Border(
              top: BorderSide(color: borderColor, width: AppSpacing.hairline),
            ),
          ),
          child: SizedBox(
            height: AppSpacing.bottomNavHeight + AppSpacing.sm,
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: List<Widget>.generate(destinations.length, (index) {
                final selected = (currentIndex < 0 ? 0 : currentIndex) == index;
                final destination = destinations[index];
                return Expanded(
                  child: CupertinoButton(
                    padding: EdgeInsets.zero,
                    minimumSize: const Size.fromHeight(
                      AppSpacing.bottomNavHeight + AppSpacing.sm,
                    ),
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
                    ),
                  ),
                );
              }),
            ),
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
  });

  final String label;
  final IconData icon;
  final IconData selectedIcon;
}

class _BottomNavItem extends StatelessWidget {
  const _BottomNavItem({
    required this.destination,
    required this.selected,
    required this.activeColor,
    required this.inactiveColor,
  });

  final _BottomDestination destination;
  final bool selected;
  final Color activeColor;
  final Color inactiveColor;

  @override
  Widget build(BuildContext context) {
    final labelStyle = TextStyle(
      fontSize: AppTypography.iosCaption2,
      fontWeight: selected ? AppTypography.semiBold : AppTypography.medium,
      color: selected ? activeColor : inactiveColor,
      height: AppTypography.lineHeightTight,
      letterSpacing: -0.08,
    );

    return Semantics(
      button: true,
      selected: selected,
      label: destination.label,
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          AnimatedScale(
            scale: selected ? 1 : 0.94,
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
            child: Icon(
              selected ? destination.selectedIcon : destination.icon,
              size: selected ? AppSpacing.iconMedium : AppSpacing.iconSmall + 6,
              color: selected ? activeColor : inactiveColor,
            ),
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
          SizedBox(height: AppSpacing.oneHalf),
          AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            curve: Curves.easeOutCubic,
            width: selected ? AppSpacing.eighteen : AppSpacing.one,
            height: AppSpacing.oneHalf,
            decoration: BoxDecoration(
              color: selected ? activeColor : Colors.transparent,
              borderRadius: BorderRadius.circular(
                AppSpacing.circularBorderRadius,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
