import 'package:flutter/cupertino.dart';
import 'package:flutter/services.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:fluentui_system_icons/fluentui_system_icons.dart';
import 'package:quwoquan_app/design_system/colors/app_colors.dart';
import 'package:quwoquan_app/design_system/icons/app_custom_icons.dart';
import 'package:quwoquan_app/design_system/providers/theme_provider.dart';
import 'package:quwoquan_app/design_system/semantics/settings_semantic_constants.dart';
import 'package:quwoquan_app/design_system/spacing/app_spacing.dart';
import 'package:quwoquan_app/design_system/typography/app_typography.dart';
import 'package:quwoquan_app/l10n/copy/app_concept_constants.dart';
import 'package:quwoquan_app/l10n/copy/chat_text_constants.dart';
import 'package:quwoquan_app/l10n/copy/ui_text_constants.dart';
import 'package:quwoquan_app/runtime/auth/auth_session.dart';
import 'package:quwoquan_app/runtime/shell/shell_immersive_providers.dart';
import 'package:quwoquan_app/runtime/testing/test_keys.dart';

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
        ? FoundationText.bottomNavGuestProfile
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
        iconBuilder: (color, selected, size) => AppVideoBookIcon(
          size: size,
          color: color,
          state: selected
              ? AppVideoBookIconState.selected
              : AppVideoBookIconState.unselected,
        ),
      ),
      _BottomDestination(
        label: '',
        semanticLabel: AppConceptConstants.create,
        icon: CupertinoIcons.plus,
        selectedIcon: CupertinoIcons.plus,
        isPrimaryAction: true,
      ),
      _BottomDestination(
        label: ChatText.chatPrimaryContacts,
        icon: FluentIcons.chat_multiple_24_regular,
        selectedIcon: FluentIcons.chat_multiple_24_regular,
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
                final selected = currentIndex == index;
                final destination = destinations[index];
                return Expanded(
                  child: Semantics(
                    selected: destination.isPrimaryAction ? null : selected,
                    label: destination.semanticLabel ?? destination.label,
                    child: CupertinoButton(
                      key: index == 1 ? TestKeys.mainTabVideoBook : null,
                      padding: EdgeInsets.zero,
                      minimumSize: Size.square(
                        destination.isPrimaryAction
                            ? AppSpacing.bottomNavPrimaryActionHitSize
                            : AppSpacing.minInteractiveSize,
                      ),
                      onPressed: () {
                        if (selected && !destination.isPrimaryAction) return;
                        HapticFeedback.selectionClick();
                        onTap(index);
                      },
                      child: ExcludeSemantics(
                        child: _BottomNavItem(
                          destination: destination,
                          selected: selected,
                          activeColor: activeColor,
                          inactiveColor: inactiveColor,
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
    );
  }
}

typedef _BottomIconBuilder = Widget Function(
  Color color,
  bool selected,
  double size,
);

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

    if (destination.isPrimaryAction) {
      return Container(
        width: AppSpacing.primaryActionPillWidth,
        height: AppSpacing.primaryActionPillHeight,
        decoration: BoxDecoration(
          color: AppColors.primaryColor,
          borderRadius: BorderRadius.circular(
            AppSpacing.primaryActionPillRadius,
          ),
        ),
        child: Icon(
          destination.selectedIcon,
          size: AppSpacing.bottomNavPrimaryActionIconSize,
          color: AppColors.white,
        ),
      );
    }

    // 只缩放普通图文内容以适配放大文字；点击热区由外层按钮完整保留。
    // 中央操作独立布局，不随文字缩放而变回小方块。
    return FittedBox(
      fit: BoxFit.scaleDown,
      child: Column(
        mainAxisSize: MainAxisSize.min,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
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
      ),
    );
  }
}
