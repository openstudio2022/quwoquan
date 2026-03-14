import 'package:flutter/material.dart';
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

    final items = [
      {'label': AppConceptConstants.discovery, 'isCenter': false},
      {'label': AppConceptConstants.circles, 'isCenter': false},
      {'label': AppConceptConstants.assistantTabLabel, 'isCenter': false},
      {'label': AppConceptConstants.chat, 'isCenter': false},
      {'label': AppConceptConstants.profile, 'isCenter': false},
    ];

    return Container(
      height: AppSpacing.bottomNavHeight,
      decoration: BoxDecoration(
        color: navBackground,
      ),
      child: Row(
        children: items.asMap().entries.map((entry) {
          final index = entry.key;
          final item = entry.value;
          final isSelected = index == this.currentIndex;

          return Expanded(
            child: GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () => this.onTap(index),
              child: Container(
                alignment: Alignment.center,
                padding: EdgeInsets.symmetric(
                  horizontal: context.safeGetContainerSpacing(SpacingSize.sm),
                  vertical: context.safeGetIntraGroupSpacing(SpacingSize.sm),
                ),
                constraints: BoxConstraints(
                  minHeight: AppSpacing.minInteractiveSize,
                ),
                child: _buildTextLabel(
                  label: item['label'] as String,
                  isSelected: isSelected,
                  isDark: isDark,
                ),
              ),
            ),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildTextLabel({
    required String label,
    required bool isSelected,
    required bool isDark,
  }) {
    final color = isSelected
        ? (isDark
            ? AppColorsFunctional.getColor(isDark, ColorType.foregroundPrimary)
            : Colors.black)
        : AppColorsFunctional.getColor(isDark, ColorType.tabUnselected);
    return Center(
      child: Text(
        label,
        style: TextStyle(
          fontSize: (isSelected
                  ? AppTypography.bottomNavLabelSelected
                  : AppTypography.bottomNavLabelUnselected),
          fontWeight: AppTypography.bottomNavLabelWeight,
          color: color,
        ),
      ),
    );
  }
}