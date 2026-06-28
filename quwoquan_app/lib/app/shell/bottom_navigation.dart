import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
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
    final auth = ref.watch(authSessionControllerProvider);
    final profileLabel = auth.status == AuthSessionStatus.guest
        ? UITextConstants.bottomNavGuestProfile
        : AppConceptConstants.profile;
    final bottomInset = MediaQuery.viewPaddingOf(context).bottom;
    // 与 [MainAppShell] 主壳底同色，避免 glassSurface + BackdropFilter 的半透明毛玻璃感。
    final navBackground = forceDark
        ? AppColors.worksBackground
        : SettingsSemanticConstants.conversationSheetCardSurface(isDark);
    final activeColor = forceDark
        ? CupertinoColors.white
        : AppColors.primaryColor;
    final inactiveColor = forceDark
        ? CupertinoColors.systemGrey
        : AppColors.iosSecondaryLabel(context);
    final destinations = <_BottomDestination>[
      _BottomDestination(
        label: AppConceptConstants.discovery,
        icon: FluentIcons.home_24_regular,
        selectedIcon: FluentIcons.home_24_filled,
      ),
      _BottomDestination(
        label: AppConceptConstants.premium,
        iconBuilder: (color, selected, size) =>
            AppOpenWindowIcon(size: size, color: color, filled: selected),
      ),
      _BottomDestination(
        label: '',
        semanticLabel: AppConceptConstants.create,
        icon: CupertinoIcons.plus,
        selectedIcon: CupertinoIcons.plus,
        isPrimaryAction: true,
      ),
      _BottomDestination(
        label: UITextConstants.chatPrimaryContacts,
        icon: FluentIcons.chat_multiple_24_regular,
        selectedIcon: FluentIcons.chat_multiple_24_regular,
      ),
      _BottomDestination(
        label: AppConceptConstants.plaza,
        icon: FluentIcons.people_community_24_regular,
        selectedIcon: FluentIcons.people_community_24_filled,
      ),
      _BottomDestination(
        label: profileLabel,
        semanticLabel: profileLabel,
        iconBuilder: (color, selected, size) =>
            AppProfilePersonIcon(size: size, color: color, filled: selected),
      ),
    ];

    final sideInset = AppSpacing.bottomNavContentSideInset(
      context,
      bottomInset,
    );
    final navHeight = AppSpacing.bottomNavBarHeight(context);
    return DecoratedBox(
      decoration: BoxDecoration(color: navBackground),
      child: Padding(
        padding: EdgeInsets.symmetric(horizontal: sideInset),
        child: SizedBox(
          height: navHeight + bottomInset,
          child: Padding(
            padding: EdgeInsets.only(bottom: bottomInset),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: List<Widget>.generate(destinations.length, (index) {
                final selected = (currentIndex < 0 ? 0 : currentIndex) == index;
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

typedef _BottomIconBuilder =
    Widget Function(Color color, bool selected, double size);

class _BottomDestination {
  const _BottomDestination({
    required this.label,
    this.icon,
    this.selectedIcon,
    this.iconBuilder,
    this.semanticLabel,
    this.isPrimaryAction = false,
  });

  final String label;
  final IconData? icon;
  final IconData? selectedIcon;
  final _BottomIconBuilder? iconBuilder;
  final String? semanticLabel;
  final bool isPrimaryAction;
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
    final iconSize = AppSpacing.bottomNavBarItemIconSize(context);
    final labelStyle = TextStyle(
      fontSize: AppTypography.iosCaption2,
      fontWeight: AppTypography.bottomNavLabelWeight,
      color: selected ? activeColor : inactiveColor,
      height: AppTypography.lineHeightTight,
      letterSpacing: AppSpacing.bottomNavLabelLetterSpacing,
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
              width: AppSpacing.primaryActionPillWidth,
              height: AppSpacing.primaryActionPillHeight,
              decoration: BoxDecoration(
                color: AppColors.primaryColor,
                borderRadius: BorderRadius.circular(AppSpacing.radiusTen),
                boxShadow: [
                  BoxShadow(
                    color: AppColors.primaryColor.withValues(alpha: 0.28),
                    blurRadius: AppSpacing.sm,
                    offset: const Offset(
                      AppSpacing.zero,
                      AppSpacing.bottomNavPrimaryActionShadowOffsetDy,
                    ),
                  ),
                ],
              ),
              child: Icon(
                destination.selectedIcon,
                size: AppSpacing.bottomNavPrimaryActionIconSize,
                color: AppColors.white,
              ),
            )
          else ...[
            if (destination.iconBuilder != null)
              destination.iconBuilder!(
                selected ? activeColor : inactiveColor,
                selected,
                iconSize,
              )
            else
              Icon(
                selected ? destination.selectedIcon : destination.icon,
                size: iconSize,
                color: selected ? activeColor : inactiveColor,
              ),
            SizedBox(height: AppSpacing.bottomNavIconLabelGap),
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
