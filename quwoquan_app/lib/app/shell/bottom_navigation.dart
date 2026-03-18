import 'package:flutter/cupertino.dart';
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
        ? AppColors.worksBackground
        : AppColorsFunctional.getColor(isDark, ColorType.backgroundPrimary);

    final activeColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.foregroundPrimary,
    );
    final inactiveColor = AppColorsFunctional.getColor(
      isDark,
      ColorType.tabUnselected,
    );
    final labels = <String>[
      AppConceptConstants.discovery,
      AppConceptConstants.assistantTabLabel,
      AppConceptConstants.chat,
      AppConceptConstants.profile,
    ];

    return DecoratedBox(
      decoration: BoxDecoration(
        color: navBackground.withValues(alpha: 0.94),
        border: Border(
          top: BorderSide(
            color: inactiveColor.withValues(alpha: 0.16),
            width: AppSpacing.hairline,
          ),
        ),
      ),
      child: SizedBox(
        height: AppSpacing.bottomNavHeight + AppSpacing.xs,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: List<Widget>.generate(labels.length, (index) {
            final selected = (currentIndex < 0 ? 0 : currentIndex) == index;
            final fontSize = AppTypography.responsive(
              context,
              compact: selected ? AppTypography.lg : AppTypography.base,
              regular: selected
                  ? AppTypography.bottomNavLabelSelected
                  : AppTypography.bottomNavLabelUnselected,
              expanded: selected ? AppTypography.xxl : AppTypography.xl,
            );
            return Expanded(
              child: CupertinoButton(
                padding: EdgeInsets.zero,
                minimumSize: const Size.fromHeight(
                  AppSpacing.bottomNavHeight + AppSpacing.xs,
                ),
                onPressed: () => onTap(index),
                child: Center(
                  child: AnimatedDefaultTextStyle(
                    duration: const Duration(milliseconds: 180),
                    curve: Curves.easeOut,
                    style: TextStyle(
                      fontSize: fontSize,
                      fontWeight: AppTypography.bottomNavLabelWeight,
                      color: selected ? activeColor : inactiveColor,
                      height: AppSpacing.one,
                    ),
                    child: Text(
                      labels[index],
                      textAlign: TextAlign.center,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
